"""Reconcile model/migration drift (additive only).

The migration chain drifted from the ORM models: a few model tables/columns were
only ever created via ``create_all`` on dev DBs, so a clean ``alembic upgrade head``
from base (as on a fresh Cloud SQL instance) produced a schema the app couldn't use
(e.g. ``column users.firebase_uid does not exist`` on register/login).

This migration adds exactly what the models expect and the chain missed — tables
``food_nutrient_cache`` + ``system_id_log`` and 12 columns across users / block_records
/ therapy_sessions. It is strictly ADDITIVE: it drops nothing (autogenerate also wanted
to drop ``facilities``/``physician_facilities``, which are real migration-created tables
whose models aren't in the autogen scope — those are intentionally kept).
"""

from alembic import op
import sqlalchemy as sa

revision = "cc002_reconcile_drift"
down_revision = "bb002_add_subscriptions"
branch_labels = None
depends_on = None

_FLOWSHEET_STATUS = ("DRAFT", "SUBMITTED", "SIGNED", "COUNTERSIGNED", "REVIEWED", "LOCKED")


def upgrade() -> None:
    # ── Model-only tables ────────────────────────────────────────────────────
    op.create_table(
        "food_nutrient_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("food_name_normalized", sa.String(length=512), nullable=False),
        sa.Column("food_name_original", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("fdc_id", sa.Integer(), nullable=True),
        sa.Column("ai_model", sa.String(length=100), nullable=True),
        sa.Column("serving_size", sa.String(length=100), nullable=True),
        sa.Column("serving_weight_g", sa.Float(), nullable=True),
        sa.Column("nutrients", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_food_cache_source", "food_nutrient_cache", ["source"], unique=False)
    op.create_index(op.f("ix_food_nutrient_cache_food_name_normalized"),
                    "food_nutrient_cache", ["food_name_normalized"], unique=True)
    op.create_index(op.f("ix_food_nutrient_cache_id"), "food_nutrient_cache", ["id"], unique=False)

    op.create_table(
        "system_id_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("system_id", sa.String(length=255), nullable=False),
        sa.Column("seg_version", sa.String(length=4), nullable=False),
        sa.Column("seg_fn3", sa.String(length=3), nullable=False),
        sa.Column("seg_ln3", sa.String(length=3), nullable=False),
        sa.Column("seg_dob8", sa.String(length=8), nullable=False),
        sa.Column("seg_gen1", sa.String(length=1), nullable=False),
        sa.Column("seg_epoch10", sa.String(length=10), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("system_id"),
    )
    op.create_index(op.f("ix_system_id_log_id"), "system_id_log", ["id"], unique=False)
    op.create_index(op.f("ix_system_id_log_user_id"), "system_id_log", ["user_id"], unique=False)

    # ── Model-only columns ───────────────────────────────────────────────────
    op.add_column("users", sa.Column("firebase_uid", sa.String(length=128), nullable=True,
                                     comment="Firebase Auth UID for migrated users"))
    op.add_column("users", sa.Column("auth_provider", sa.String(length=50), nullable=True,
                                     comment="Auth provider: local, firebase, google, apple, phone"))

    op.add_column("block_records", sa.Column("blockchain_tx_hash", sa.String(length=66), nullable=True))
    op.add_column("block_records", sa.Column("blockchain_block_num", sa.Integer(), nullable=True))

    # op.add_column with an Enum does NOT auto-create the PG type (unlike create_table),
    # so create it explicitly, then reference it with create_type=False in the column.
    sa.Enum(*_FLOWSHEET_STATUS, name="flowsheetstatus").create(op.get_bind(), checkfirst=True)
    op.add_column("therapy_sessions", sa.Column(
        "flowsheet_status",
        sa.Enum(*_FLOWSHEET_STATUS, name="flowsheetstatus", create_type=False),
        nullable=True, comment="draft→submitted→signed→countersigned→reviewed→locked"))
    op.add_column("therapy_sessions", sa.Column("signature_image", sa.Text(), nullable=True))
    op.add_column("therapy_sessions", sa.Column("signed_at", sa.DateTime(), nullable=True))
    op.add_column("therapy_sessions", sa.Column("signed_by", sa.Integer(), nullable=True))
    op.add_column("therapy_sessions", sa.Column("countersigned_at", sa.DateTime(), nullable=True))
    op.add_column("therapy_sessions", sa.Column("countersigned_by", sa.Integer(), nullable=True))
    op.add_column("therapy_sessions", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    op.add_column("therapy_sessions", sa.Column("reviewed_by", sa.Integer(), nullable=True))


def downgrade() -> None:
    for col in ("reviewed_by", "reviewed_at", "countersigned_by", "countersigned_at",
                "signed_by", "signed_at", "signature_image", "flowsheet_status"):
        op.drop_column("therapy_sessions", col)
    sa.Enum(name="flowsheetstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_column("block_records", "blockchain_block_num")
    op.drop_column("block_records", "blockchain_tx_hash")
    op.drop_column("users", "auth_provider")
    op.drop_column("users", "firebase_uid")
    op.drop_table("system_id_log")
    op.drop_table("food_nutrient_cache")
