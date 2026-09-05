"""WebSocket signaling server for real-time WebRTC negotiation and session chat.

Two WebSocket endpoints:
  /ws/telehealth/{session_code}?token=<jwt>   — WebRTC signaling + presence
  /ws/telehealth/{session_code}/chat?token=<jwt> — In-session text chat + transcripts
"""

import asyncio
import json
from datetime import datetime, timezone
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import jwt  # PyJWT
from sqlalchemy import select, or_, func

from app.core.config import settings
from app.core.database import async_session
from app.models.user import User
from app.models.telehealth import TelehealthSession, SessionParticipant, SessionTranscript

router = APIRouter()


# ── Redis-backed Connection Manager ──────────────────────────────────

class ConnectionManager:
    """Manages active WebSocket connections per session room with Redis pub/sub."""

    def __init__(self, channel_prefix: str):
        # session_code -> {user_id: WebSocket}
        self.rooms: dict[str, dict[int, WebSocket]] = defaultdict(dict)
        self._channel_prefix = channel_prefix
        self._pubsub = None
        self._listener_task: asyncio.Task | None = None

    async def startup(self) -> None:
        try:
            from app.core.redis import get_redis
            redis = await get_redis()
            self._pubsub = redis.pubsub()
            self._listener_task = asyncio.create_task(self._redis_listener())
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Redis unavailable — telehealth WS in single-node mode: %s", exc
            )

    async def shutdown(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.aclose()

    async def _redis_listener(self) -> None:
        async for msg in self._pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                channel: str = msg["channel"]
                data = json.loads(msg["data"])
                exclude = data.pop("__exclude__", None)
                prefix = f"{self._channel_prefix}:"
                if channel.startswith(prefix):
                    session_code = channel[len(prefix):]
                    await self._local_broadcast(session_code, data, exclude)
            except Exception:
                pass

    async def connect(self, session_code: str, user_id: int, ws: WebSocket):
        await ws.accept()
        self.rooms[session_code][user_id] = ws
        if self._pubsub:
            await self._pubsub.subscribe(f"{self._channel_prefix}:{session_code}")
        # Notify others
        await self.broadcast(session_code, {
            "type": "peer_joined",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, exclude=user_id)

    def disconnect(self, session_code: str, user_id: int):
        self.rooms[session_code].pop(user_id, None)
        if not self.rooms[session_code]:
            del self.rooms[session_code]

    async def send_to(self, session_code: str, user_id: int, data: dict):
        ws = self.rooms.get(session_code, {}).get(user_id)
        if ws:
            await ws.send_json(data)

    async def broadcast(self, session_code: str, data: dict, exclude: int | None = None):
        if self._pubsub:
            try:
                from app.core.redis import get_redis
                redis = await get_redis()
                payload = {**data, "__exclude__": exclude}
                await redis.publish(f"{self._channel_prefix}:{session_code}", json.dumps(payload))
                return
            except Exception:
                pass
        await self._local_broadcast(session_code, data, exclude)

    async def _local_broadcast(self, session_code: str, data: dict, exclude: int | None = None):
        for uid, ws in list(self.rooms.get(session_code, {}).items()):
            if uid != exclude:
                try:
                    await ws.send_json(data)
                except Exception:
                    pass

    def get_peers(self, session_code: str, exclude: int | None = None) -> list[int]:
        return [uid for uid in self.rooms.get(session_code, {}) if uid != exclude]


signaling_manager = ConnectionManager(channel_prefix="alafia:telehealth:sig")
chat_manager = ConnectionManager(channel_prefix="alafia:telehealth:chat")


# ── Auth helper ──────────────────────────────────────────────────────

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
    """Return user_id from a hybrid PQC identity token or legacy HS512 token."""
    from app.services.identity_client import verify_identity_token
    claims = await verify_identity_token(token)
    if claims is not None:
        return await _resolve_identity_user_id(claims)
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        return int(user_id) if user_id else None
    except (jwt.PyJWTError, ValueError, TypeError):
        return None


async def _verify_session_access(session_code: str, user_id: int) -> bool:
    """Check that the session exists and the user is a participant."""
    async with async_session() as db:
        result = await db.execute(
            select(TelehealthSession).where(TelehealthSession.session_code == session_code)
        )
        session = result.scalar_one_or_none()
        if not session:
            return False

        if session.created_by_id == user_id or session.provider_id == user_id:
            return True

        result = await db.execute(
            select(SessionParticipant).where(
                SessionParticipant.session_id == session.id,
                SessionParticipant.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None


# ═══════════════════════════════════════════════════════════════════════
# WebRTC Signaling WebSocket
# ═══════════════════════════════════════════════════════════════════════

@router.websocket("/ws/telehealth/{session_code}")
async def ws_signaling(
    ws: WebSocket,
    session_code: str,
    token: str = Query(...),
):
    """WebRTC signaling channel.

    Client sends JSON messages:
      {"type": "offer",  "to": user_id, "sdp": "..."}
      {"type": "answer", "to": user_id, "sdp": "..."}
      {"type": "ice_candidate", "to": user_id, "candidate": {...}}
      {"type": "renegotiate", "to": user_id, "sdp": "..."}

    Server broadcasts:
      {"type": "peer_joined",  "user_id": int}
      {"type": "peer_left",    "user_id": int}
      {"type": "peers",        "user_ids": [...]}  — sent on connect
    """
    user_id = await _authenticate_ws(token)
    if not user_id:
        await ws.close(code=4001, reason="Invalid token")
        return

    # Paywall. `require_active_subscription` is a Request dependency and cannot
    # be applied to a WebSocket route, so these sockets were mounted with no
    # gate at all — an unpaid account with a valid token could use real-time
    # telehealth while every HTTP path returned 402. Close code 4402 mirrors the
    # HTTP 402 so a client can tell "not paid" from "not allowed" (4003).
    from app.core.entitlement import is_user_entitled
    if not await is_user_entitled(user_id):
        await ws.close(code=4402, reason="Membership required")
        return

    if not await _verify_session_access(session_code, user_id):
        await ws.close(code=4003, reason="Access denied")
        return

    await signaling_manager.connect(session_code, user_id, ws)

    # Send list of already-connected peers
    peers = signaling_manager.get_peers(session_code, exclude=user_id)
    await ws.send_json({"type": "peers", "user_ids": peers})

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")
            to_user = msg.get("to")

            if msg_type in ("offer", "answer", "ice_candidate", "renegotiate"):
                payload = {**msg, "from": user_id}
                if to_user:
                    await signaling_manager.send_to(session_code, to_user, payload)
                else:
                    await signaling_manager.broadcast(session_code, payload, exclude=user_id)
    except WebSocketDisconnect:
        pass
    finally:
        signaling_manager.disconnect(session_code, user_id)
        await signaling_manager.broadcast(session_code, {
            "type": "peer_left",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })


# ═══════════════════════════════════════════════════════════════════════
# In-Session Chat & Transcription WebSocket
# ═══════════════════════════════════════════════════════════════════════

@router.websocket("/ws/telehealth/{session_code}/chat")
async def ws_chat(
    ws: WebSocket,
    session_code: str,
    token: str = Query(...),
):
    """In-session text chat and live transcription relay.

    Client sends:
      {"type": "chat",       "content": "Hello..."}
      {"type": "transcript", "content": "...", "language": "en", "confidence": 0.95,
       "start_offset_ms": 12000, "end_offset_ms": 14000, "sequence_number": 5}

    Server broadcasts:
      {"type": "chat",       "from": user_id, "content": "...", "timestamp": "..."}
      {"type": "transcript", "from": user_id, "content": "...", ...}
    """
    user_id = await _authenticate_ws(token)
    if not user_id:
        await ws.close(code=4001, reason="Invalid token")
        return

    # Paywall. `require_active_subscription` is a Request dependency and cannot
    # be applied to a WebSocket route, so these sockets were mounted with no
    # gate at all — an unpaid account with a valid token could use real-time
    # telehealth while every HTTP path returned 402. Close code 4402 mirrors the
    # HTTP 402 so a client can tell "not paid" from "not allowed" (4003).
    from app.core.entitlement import is_user_entitled
    if not await is_user_entitled(user_id):
        await ws.close(code=4402, reason="Membership required")
        return

    if not await _verify_session_access(session_code, user_id):
        await ws.close(code=4003, reason="Access denied")
        return

    await chat_manager.connect(session_code, user_id, ws)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type", "")
            now = datetime.now(timezone.utc)

            if msg_type == "chat":
                await chat_manager.broadcast(session_code, {
                    "type": "chat",
                    "from": user_id,
                    "content": msg.get("content", ""),
                    "timestamp": now.isoformat(),
                })

            elif msg_type == "transcript":
                content = msg.get("content", "")
                # Persist to database
                async with async_session() as db:
                    result = await db.execute(
                        select(TelehealthSession).where(
                            TelehealthSession.session_code == session_code
                        )
                    )
                    session = result.scalar_one_or_none()
                    if session and session.transcription_enabled:
                        transcript = SessionTranscript(
                            session_id=session.id,
                            speaker_id=user_id,
                            content=content,
                            language=msg.get("language", "en"),
                            confidence=msg.get("confidence"),
                            start_offset_ms=msg.get("start_offset_ms"),
                            end_offset_ms=msg.get("end_offset_ms"),
                            sequence_number=msg.get("sequence_number", 0),
                        )
                        db.add(transcript)
                        await db.commit()

                # Relay to all peers
                await chat_manager.broadcast(session_code, {
                    "type": "transcript",
                    "from": user_id,
                    "content": content,
                    "language": msg.get("language", "en"),
                    "confidence": msg.get("confidence"),
                    "sequence_number": msg.get("sequence_number", 0),
                    "timestamp": now.isoformat(),
                })

    except WebSocketDisconnect:
        pass
    finally:
        chat_manager.disconnect(session_code, user_id)
