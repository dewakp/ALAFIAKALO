"""Subscription / billing models.

ALAFIA has a single paid tier ("ALAFIA Plus"). Entitlement is owned by the
backend — whichever rail a user pays through (Stripe on the web, Google Play on
Android, Apple StoreKit on iOS) reports a *verified* purchase and the backend
records the resulting active period on the user's one ``Subscription`` row.
Reads never trust the client; ``is_entitled`` derives access purely from
``status`` + ``current_period_end`` (+ a small grace window).

``SubscriptionEvent`` is an append-only audit / idempotency log: every provider
webhook or verify call is recorded by its provider event id so the same event is
never applied twice (webhooks retry, and users can re-submit a receipt).
"""

from datetime import datetime, timezone, timedelta
from enum import Enum as PyEnum

from sqlalchemy import String, Float, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SubscriptionStatus(str, PyEnum):
    """Lifecycle of a subscription. Stored as a plain string column."""

    NONE = "none"            # never subscribed / fully lapsed
    INCOMPLETE = "incomplete"  # checkout started, first payment never succeeded (NOT entitled)
    TRIALING = "trialing"    # in a free trial (entitled)
    ACTIVE = "active"        # paid and current (entitled)
    PAST_DUE = "past_due"    # renewal failed, retrying (entitled during grace)
    CANCELED = "canceled"    # will not renew; entitled until period end
    EXPIRED = "expired"      # period ended, not renewed (not entitled)


# Statuses that grant access while the current period (or grace) is still valid.
#
# ``INCOMPLETE`` is deliberately absent, and the distinction from ``PAST_DUE`` is
# the whole point of having it: Stripe puts a period on a subscription the moment
# it is created, *before* the first invoice is paid. Treating a first-payment
# failure as PAST_DUE would therefore hand out a full period of free access to
# anyone who reaches the card form with a card that declines. PAST_DUE means "was
# paying, a RENEWAL failed" — access already earned. INCOMPLETE means "never paid".
_ENTITLING_STATUSES = {
    SubscriptionStatus.TRIALING.value,
    SubscriptionStatus.ACTIVE.value,
    SubscriptionStatus.PAST_DUE.value,
    SubscriptionStatus.CANCELED.value,
}


class SubscriptionProvider(str, PyEnum):
    """Which billing rail the current subscription was purchased through."""

    NONE = "none"
    STRIPE = "stripe"
    # PAYPAL is a WITHDRAWN rail: it can no longer be selected, and nothing
    # writes it. It stays here (with `paypal_subscription_id` below) because the
    # value is still part of the deployed column's domain — dropping it from the
    # model while the column exists is drift, not cleanup.
    PAYPAL = "paypal"
    GOOGLE_PLAY = "google_play"
    APPLE = "apple"


# The two billing intervals of the single membership tier. Kept as constants so
# pricing/labels live in one place; the per-rail USD price is resolved from
# settings at request time. (Names keep the historical "plus_" prefix so existing
# subscription rows / store product ids stay valid.)
PLAN_PLUS_MONTHLY = "plus_monthly"
PLAN_PLUS_ANNUAL = "plus_annual"


def plan_for_interval(interval: str) -> str:
    """Map a billing interval ('month'|'year') to the plan constant."""
    return PLAN_PLUS_ANNUAL if str(interval).lower() in ("year", "annual", "yearly") else PLAN_PLUS_MONTHLY


class Subscription(Base):
    """A user's current subscription state (one row per user)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SubscriptionStatus.NONE.value
    )
    provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SubscriptionProvider.NONE.value
    )
    plan: Mapped[str] = mapped_column(String(40), nullable=False, default=PLAN_PLUS_MONTHLY)
    price_usd: Mapped[float | None] = mapped_column(Float)

    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Provider reconciliation ids (only the active rail's are populated) ──
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(255), index=True)
    paypal_subscription_id: Mapped[str | None] = mapped_column(String(255), index=True)
    google_purchase_token: Mapped[str | None] = mapped_column(Text)  # tokens are long
    google_order_id: Mapped[str | None] = mapped_column(String(255))
    apple_original_transaction_id: Mapped[str | None] = mapped_column(String(255), index=True)
    apple_transaction_id: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def is_entitled(self, grace_days: int = 0, at: datetime | None = None) -> bool:
        """True when this subscription grants Plus access right now.

        Access requires an entitling status AND a period end that is still in the
        future (extended by ``grace_days`` to absorb webhook/renewal lag). A
        missing ``current_period_end`` on an entitling status is treated as open
        (e.g. a freshly recorded purchase awaiting its first renewal event).
        """
        if self.status not in _ENTITLING_STATUSES:
            return False
        now = at or datetime.now(timezone.utc)
        end = self.current_period_end
        if end is None:
            return True
        if end.tzinfo is None:  # defensively normalise naive timestamps
            end = end.replace(tzinfo=timezone.utc)
        return now <= end + timedelta(days=max(0, grace_days))


class SubscriptionEvent(Base):
    """Append-only log of processed provider events (idempotency + audit)."""

    __tablename__ = "subscription_events"
    # One-time application per provider event (matches the migration's index).
    __table_args__ = (
        Index("ux_subscription_events_provider_event", "provider", "event_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # Provider's own event id (Stripe event id, purchase token,
    # transaction id …). Unique per provider so the same event applies once.
    event_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str | None] = mapped_column(String(100))
    payload: Mapped[str | None] = mapped_column(Text)  # raw JSON, for debugging
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
