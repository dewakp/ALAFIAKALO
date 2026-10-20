# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""A complimentary membership offered to someone who has no account yet.

Operator, 2026-10-20: *"move sending to backend. All this must be automated not
sender triggered."* and *"system knows what actions invitees/subscribers perform
and responds accordingly."*

The row exists so the offer is a FACT the system holds, not an email that has
already left. Before it, `send_comp_invitation.py` wrote nothing: the letter to
`bass797@aol.com` lived in Resend's logs, so nothing could remind him, nothing
could activate him when he verified, and no admin screen could show him.

**This table holds only what nothing else can answer.** Every later stage is
read from the tables that already own it — `pending_registrations` knows who
started and who verified, `users` knows who exists and who has signed in,
`subscriptions` knows what they hold. Duplicating those here would be two
computations of one fact that can disagree (§3ai).

`claimed_at` and `activated_at` are the exception, and they are not stage
mirrors: they record the moments WE ACTED. A reminder pass has to know whether
it has already responded, and a second activation must never run against an
account that has one.
"""

from datetime import date, datetime, timezone

from sqlalchemy import DateTime, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompInvitation(Base):
    """One complimentary offer, and what has become of it."""

    __tablename__ = "comp_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    #: The address the membership is attached to. The letter tells the reader to
    #: use it EXACTLY, because this is the key everything else joins on. Always
    #: compared case-insensitively — `lower(email)` is what the indexes cover.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255))
    months: Mapped[int] = mapped_column(Integer, nullable=False, default=12,
                                        server_default="12")

    #: Granted ON TOP of the patient account, and set only when it will really
    #: be granted. An honorific is not a role: "Dr." can be a PhD, and promising
    #: a clinician board to an account that will never open one is a letter the
    #: product cannot honour.
    clinical_role: Mapped[str | None] = mapped_column(String(64))
    practice: Mapped[str | None] = mapped_column(String(255))

    #: NOT NULL deliberately. Two letters have gone out carrying a deadline
    #: ("22 September 2026", "27 October 2026") and neither was written down —
    #: so nobody could tell a lapsed offer from a pending one, which is the
    #: first question anyone asks about an invitation.
    deadline: Mapped[date] = mapped_column(Date, nullable=False)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Why a send failed, kept rather than raised away: a row with no `sent_at`
    #: and no reason is indistinguishable from one never attempted (§3aa).
    send_error: Mapped[str | None] = mapped_column(Text)

    reminders_sent: Mapped[int] = mapped_column(Integer, nullable=False, default=0,
                                                server_default="0")
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: When we noticed they began, and when we activated them.
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"))

    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc))

    @property
    def is_live(self) -> bool:
        """Still an open offer — neither activated nor withdrawn.

        Expiry is NOT part of this. A lapsed invitation is still the record of
        an offer we made, and an operator deciding whether to extend it needs
        to see it; hiding it behind a date would answer a question nobody asked.
        """
        return self.activated_at is None and self.revoked_at is None
