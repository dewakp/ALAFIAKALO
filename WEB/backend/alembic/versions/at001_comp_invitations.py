# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""An invitation is a RECORD, not an email that already left.

Operator, 2026-10-20: *"move sending to backend. All this must be automated not
sender triggered."* and *"system knows what actions invitees/subscribers perform
and responds accordingly."*

`scripts/email/send_comp_invitation.py` touches no table. So the letter sent to
`bass797@aol.com` on 2026-10-20 — twelve months, deadline 27 October — exists in
Resend's logs and nowhere in ALAFIA. Nothing knows he was invited, nothing can
remind him, nothing can activate him when he verifies, and he cannot appear on
any admin screen because **there is no row to show**. The first stage of the
funnel did not exist in the database.

Every other stage already does, and is a fact we can read rather than a state we
must store:

    started signup     a pending_registrations row for that address
    verified email     pending_registrations.email_verified_at
    active             users + subscriptions
    first sign-in      users.last_login
    profile complete   the profile tables

So this table holds ONLY what nothing else can answer — that an offer was made,
on what terms, and what has happened to it since. `claimed_at` and
`activated_at` are stamped because they are the moments we ACTED, not because
the stage cannot be derived: a reminder must know whether we have already
responded, and "derivable" is not the same as "cheap to derive inside a job
that runs every hour".

⚠️ **`deadline` is NOT NULL.** The 2026-09-15 letter carried one ("22 September
2026") and the 2026-10-20 letter carries another, and neither was written down
anywhere. Without it nobody can tell a lapsed offer from a pending one, which
is exactly the question an operator asks first.

Additive only: one new table, no drops, no backfill (§3ao). The invitation
already sent to Dr. Bass is deliberately NOT backfilled here — a migration that
invents a `sent_at` it did not observe is a fabricated record. It is inserted
explicitly, from the known facts, in a separate visible step.
"""

import sqlalchemy as sa
from alembic import op

revision = "at001_comp_invitations"
down_revision = "as001_nutrients_excluded"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comp_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        # The address the membership is attached to. The letter tells the reader
        # to use it EXACTLY, so this is the join key to pending_registrations
        # and users, and it is matched case-insensitively everywhere.
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("months", sa.Integer(), nullable=False, server_default="12"),
        # Granted ON TOP of the patient account, and only when it will really be
        # granted — an honorific is not a role (§ email.is_clinical_role).
        sa.Column("clinical_role", sa.String(64), nullable=True),
        sa.Column("practice", sa.String(255), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("send_error", sa.Text(), nullable=True),
        sa.Column("reminders_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True),
        # The moments WE acted on what they did.
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    # Case-insensitive lookup is the only way this table is ever read: an
    # invitation is found BY the address someone typed at signup.
    op.create_index("ix_comp_invitations_email_lower", "comp_invitations",
                    [sa.text("lower(email)")])
    # One LIVE offer per address. A second invitation to the same person is a
    # re-send, not a second membership — and without this a duplicate row would
    # make the reminder job mail them twice.
    op.create_index(
        "ux_comp_invitations_live_email", "comp_invitations",
        [sa.text("lower(email)")], unique=True,
        postgresql_where=sa.text("revoked_at IS NULL AND activated_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_comp_invitations_live_email", table_name="comp_invitations")
    op.drop_index("ix_comp_invitations_email_lower", table_name="comp_invitations")
    op.drop_table("comp_invitations")
