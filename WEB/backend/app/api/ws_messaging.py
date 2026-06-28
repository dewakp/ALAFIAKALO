"""
WebSocket endpoints for real-time messaging.

Endpoints
---------
- ``WS /ws/messaging/{conversation_id}?token=<jwt>``
    Real-time message relay for a conversation.  Broadcasts new messages,
    typing indicators, read receipts, and presence updates.

- ``WS /ws/feed?token=<jwt>``
    Real-time community feed notifications (new posts, likes, replies in
    topics the user follows).
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
import jwt  # PyJWT
from sqlalchemy import select, or_, func

from app.core.config import settings
from app.core.database import async_session
from app.models.user import User
from app.models.messaging import (
    Conversation,
    ConversationMember,
    Message,
    MessageType,
)

router = APIRouter()


# ─────────────────────────────────────────────
# Redis-backed Connection Manager
# ─────────────────────────────────────────────

class MessagingConnectionManager:
    """Manages WebSocket connections with Redis pub/sub for multi-instance support."""

    def __init__(self):
        # Local connections: conv_id -> {user_id: WebSocket}
        self.rooms: dict[int, dict[int, WebSocket]] = defaultdict(dict)
        # Feed subscribers: user_id -> WebSocket
        self.feed_subscribers: dict[int, WebSocket] = {}
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    async def startup(self) -> None:
        """Wire Redis pub/sub on app startup. Fails gracefully if Redis unavailable."""
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            self._pubsub = redis.pubsub()
            self._listener_task = asyncio.create_task(self._redis_listener())
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Redis unavailable — WebSocket running in single-node mode: %s", exc
            )

    async def shutdown(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.aclose()

    async def _redis_listener(self) -> None:
        """Background task: forward Redis pub/sub messages to local WS connections."""
        async for msg in self._pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                channel: str = msg["channel"]
                data = json.loads(msg["data"])
                exclude = data.pop("__exclude__", None)
                if channel.startswith("alafia:conv:"):
                    conv_id = int(channel.split(":")[-1])
                    await self._local_broadcast_room(conv_id, data, exclude)
                elif channel == "alafia:feed":
                    await self._local_broadcast_feed(data, exclude)
            except Exception:
                pass

    # ── Room management ──

    async def connect_room(self, conv_id: int, user_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms[conv_id][user_id] = ws
        if self._pubsub:
            await self._pubsub.subscribe(f"alafia:conv:{conv_id}")

    def disconnect_room(self, conv_id: int, user_id: int):
        self.rooms[conv_id].pop(user_id, None)
        if not self.rooms[conv_id]:
            del self.rooms[conv_id]

    async def broadcast_room(self, conv_id: int, message: dict, exclude_user: int | None = None):
        if self._pubsub:
            try:
                from app.core.redis import get_redis
                redis = await get_redis()
                payload = {**message, "__exclude__": exclude_user}
                await redis.publish(f"alafia:conv:{conv_id}", json.dumps(payload))
                return
            except Exception:
                pass
        # Fallback: local only
        await self._local_broadcast_room(conv_id, message, exclude_user)

    async def _local_broadcast_room(self, conv_id: int, message: dict, exclude_user: int | None = None):
        dead = []
        for uid, ws in list(self.rooms.get(conv_id, {}).items()):
            if uid == exclude_user:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect_room(conv_id, uid)

    # ── Feed management ──

    async def connect_feed(self, user_id: int, ws: WebSocket):
        await ws.accept()
        self.feed_subscribers[user_id] = ws
        if self._pubsub:
            await self._pubsub.subscribe("alafia:feed")

    def disconnect_feed(self, user_id: int):
        self.feed_subscribers.pop(user_id, None)

    async def broadcast_feed(self, message: dict, exclude_user: int | None = None):
        if self._pubsub:
            try:
                from app.core.redis import get_redis
                redis = await get_redis()
                payload = {**message, "__exclude__": exclude_user}
                await redis.publish("alafia:feed", json.dumps(payload))
                return
            except Exception:
                pass
        await self._local_broadcast_feed(message, exclude_user)

    async def _local_broadcast_feed(self, message: dict, exclude_user: int | None = None):
        dead = []
        for uid, ws in list(self.feed_subscribers.items()):
            if uid == exclude_user:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(uid)
        for uid in dead:
            self.disconnect_feed(uid)


manager = MessagingConnectionManager()


# ─────────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────────

async def _resolve_identity_user_id(claims: dict) -> int | None:
    """Map a verified identity (PQC) token to the local ALAFIA user id."""
    conds = [User.identity_uid == claims.get("sub")]
    sid = (claims.get("sid") or "").strip()
    email = (claims.get("email") or "").strip().lower()
    if sid:
        conds.append(User.system_id == sid)
    if email:
        conds.append(func.lower(User.email) == email)
    async with async_session() as db:
        row = (await db.execute(select(User.id).where(or_(*conds)))).first()
    return int(row[0]) if row else None


async def _authenticate_ws(token: str) -> int | None:
    # 1) Shared identity hybrid PQC token (cross-app SSO).
    from app.services.identity_client import verify_identity_token
    claims = await verify_identity_token(token)
    if claims is not None:
        return await _resolve_identity_user_id(claims)
    # 2) Legacy ALAFIA HS512 token (migration window).
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        return int(user_id) if user_id else None
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


async def _verify_conv_access(conv_id: int, user_id: int) -> bool:
    async with async_session() as db:
        r = await db.execute(
            select(ConversationMember).where(
                ConversationMember.conversation_id == conv_id,
                ConversationMember.user_id == user_id,
                ConversationMember.left_at.is_(None),
            )
        )
        return r.scalars().first() is not None


# ─────────────────────────────────────────────
# WS: Conversation messages
# ─────────────────────────────────────────────

@router.websocket("/ws/messaging/{conversation_id}")
async def ws_conversation(
    websocket: WebSocket,
    conversation_id: int,
    token: str = Query(...),
):
    user_id = await _authenticate_ws(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if not await _verify_conv_access(conversation_id, user_id):
        await websocket.close(code=4003, reason="Not a member")
        return

    await manager.connect_room(conversation_id, user_id, websocket)

    # Announce presence
    await manager.broadcast_room(conversation_id, {
        "type": "presence",
        "user_id": user_id,
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, exclude_user=user_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "message")

            if msg_type == "message":
                # Persist message to DB
                content = data.get("content", "")
                message_kind = data.get("message_type", "text")
                async with async_session() as db:
                    msg = Message(
                        conversation_id=conversation_id,
                        sender_id=user_id,
                        message_type=message_kind,
                        content=content,
                        file_url=data.get("file_url"),
                        file_name=data.get("file_name"),
                        reply_to_id=data.get("reply_to_id"),
                        is_clinical=data.get("is_clinical", False),
                        is_priority=data.get("is_priority", False),
                    )
                    db.add(msg)
                    await db.flush()

                    # Update conversation preview
                    r = await db.execute(
                        select(Conversation).where(Conversation.id == conversation_id)
                    )
                    conv = r.scalars().first()
                    if conv:
                        conv.last_message_at = datetime.now(timezone.utc)
                        conv.last_message_preview = content[:300] if content else ""

                    await db.commit()
                    msg_id = msg.id

                await manager.broadcast_room(conversation_id, {
                    "type": "message",
                    "id": msg_id,
                    "sender_id": user_id,
                    "message_type": message_kind,
                    "content": content,
                    "file_url": data.get("file_url"),
                    "file_name": data.get("file_name"),
                    "reply_to_id": data.get("reply_to_id"),
                    "is_clinical": data.get("is_clinical", False),
                    "is_priority": data.get("is_priority", False),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif msg_type == "typing":
                await manager.broadcast_room(conversation_id, {
                    "type": "typing",
                    "user_id": user_id,
                    "is_typing": data.get("is_typing", True),
                }, exclude_user=user_id)

            elif msg_type == "read":
                # Client signals they've read up to a message
                await manager.broadcast_room(conversation_id, {
                    "type": "read",
                    "user_id": user_id,
                    "message_id": data.get("message_id"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, exclude_user=user_id)

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        manager.disconnect_room(conversation_id, user_id)
        await manager.broadcast_room(conversation_id, {
            "type": "presence",
            "user_id": user_id,
            "status": "offline",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ─────────────────────────────────────────────
# WS: Community feed
# ─────────────────────────────────────────────

@router.websocket("/ws/feed")
async def ws_feed(
    websocket: WebSocket,
    token: str = Query(...),
):
    user_id = await _authenticate_ws(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect_feed(user_id, websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type")

            if msg_type == "new_post":
                await manager.broadcast_feed({
                    "type": "new_post",
                    "post_id": data.get("post_id"),
                    "author_id": user_id,
                    "preview": data.get("preview", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }, exclude_user=user_id)

            elif msg_type == "new_reply":
                await manager.broadcast_feed({
                    "type": "new_reply",
                    "post_id": data.get("post_id"),
                    "reply_id": data.get("reply_id"),
                    "author_id": user_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif msg_type == "new_like":
                await manager.broadcast_feed({
                    "type": "new_like",
                    "post_id": data.get("post_id"),
                    "user_id": user_id,
                    "reaction": data.get("reaction", "like"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

    except WebSocketDisconnect:
        manager.disconnect_feed(user_id)
