# Copyright © 2026 Wole Akpose / 6igma Health Inc.
# All rights reserved. ALAFIA — proprietary and confidential.

"""allergy_term_resolutions — a misspelled allergy, resolved once and remembered

Revision ID: am001_allergy_terms
Revises: al001_import_judgments
Create Date: 2026-10-03

WHY THIS TABLE EXISTS. The reference profile declares `Penicilin, Latex,
Heparine, Raw Apples, Raw Berries`. A dose logged as the correctly-spelled
`Penicillin` did not match `Penicilin`, because the matcher compares words and
neither spelling is a prefix of the other — so the one guard that exists to stop
a patient being given a drug they declared an allergy to was defeated by a
single missing letter.

WHY IT IS NOT FIXED IN `users.allergies`. Rewriting what a patient declared
about their own body invents a clinical fact. The declared text stays verbatim
— it is how the patient recognises their own record — and the resolution is
stored BESIDE it, additively, so both spellings match.

WHY RXNORM IS CONSULTED HERE AND NEVER ON A WRITE PATH. §3aj: RxNorm is the
authority on whether a name is a drug, and `approximateTerm` is the right
instrument for a misspelling where string similarity is the wrong one. It is
also a network call, so it cannot sit where a patient waits for a save. This is
the `learned_food_nutrients` / `condition_nutrition_facts` shape (§3an): look it
up once, remember it after.

WHY THERE IS NO `user_id`. "Penicilin" means "Penicillin" for everybody. The
row holds a TERM and its clinical identity — never whose profile it came from,
never a measurement — which is what lets one patient's typo help the next
patient's guard without either seeing the other's record. Same privacy shape as
`document_row_judgments` (al001), which stores a row's shape and not its value.

WRITTEN BY HAND. `alembic revision --autogenerate` on this schema emits ~200
lines that DROP five live tables and rewrite indexes across the database (§3ao),
because the models in code do not describe the deployed schema exactly. Every
upgrade() in this project's history is additive. This one adds a table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "am001_allergy_terms"
down_revision: Union[str, None] = "al001_import_judgments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "allergy_term_resolutions",
        sa.Column("id", sa.Integer(), nullable=False),
        # The normalised declared term — `food_safety._normalise` output, which
        # is what the matcher actually compares. UNIQUE: one verdict per term.
        sa.Column("declared_term", sa.String(length=200), nullable=False),
        # One verbatim example of how a patient wrote it, for audit. A guard
        # that cannot explain itself gets blamed for what it did not do (§3aj).
        sa.Column("declared_sample", sa.String(length=200), nullable=True),
        # What RxNorm says it is. NULL when nothing was accepted.
        sa.Column("resolved_name", sa.String(length=200), nullable=True),
        sa.Column("resolved_term", sa.String(length=200), nullable=True),
        sa.Column("rxcui", sa.String(length=20), nullable=True),
        # exact     — RxNorm knew the term as typed; no alias needed
        # spelling  — accepted as a misspelling of `resolved_name`
        # refused   — RxNorm proposed something that is NOT a spelling variant
        #             ("Raw Apples" -> "raw sugar", measured 2026-10-03)
        # unknown   — RxNorm had no candidate
        # unreachable — RxNav could not be consulted; ask again later
        sa.Column("verdict", sa.String(length=16), nullable=False),
        # Why a proposal was refused, in words. Kept because the refusals are
        # the interesting half: they are where a confident wrong answer was
        # stopped, and reviewing them is how the thresholds get checked.
        sa.Column("refused_reason", sa.String(length=300), nullable=True),
        sa.Column("edit_distance", sa.Integer(), nullable=True),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("provenance", sa.String(length=32), nullable=False,
                  server_default="rxnorm"),
        sa.Column("times_confirmed", sa.Integer(), nullable=False, server_default="1"),
        # Retire a bad resolution without deleting it, so it stays auditable
        # and cannot be silently re-learned.
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("declared_term", name="uq_allergy_term_declared"),
    )
    op.create_index("ix_allergy_term_resolutions_declared_term",
                    "allergy_term_resolutions", ["declared_term"])


def downgrade() -> None:
    op.drop_index("ix_allergy_term_resolutions_declared_term",
                  table_name="allergy_term_resolutions")
    op.drop_table("allergy_term_resolutions")
