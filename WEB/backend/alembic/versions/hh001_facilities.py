"""separate facility directory — facilities + physician_facilities tables

Physicians are humans; facilities are places they practice from. Move any
facility rows that were temporarily stored in `physicians` into `facilities`.

Revision ID: hh001_facilities
Revises: gg001_entity_type
Create Date: 2026-06-29
"""
import sqlalchemy as sa
from alembic import op

revision = "hh001_facilities"
down_revision = "gg001_entity_type"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "facilities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("facility_type", sa.String(60), nullable=False, server_default="facility"),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state_province", sa.String(100), nullable=True),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("location_precision", sa.String(20), nullable=True),
        sa.Column("source", sa.String(40), nullable=True),
        sa.Column("source_uid", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source", "source_uid", name="uq_facility_source_uid"),
    )
    op.create_index("ix_facilities_name", "facilities", ["name"])
    op.create_index("ix_facilities_type", "facilities", ["facility_type"])
    op.create_index("ix_facilities_city", "facilities", ["city"])
    op.create_index("ix_facilities_country", "facilities", ["country"])
    op.create_index("ix_facilities_geo", "facilities", ["latitude", "longitude"])

    op.create_table(
        "physician_facilities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("physician_id", sa.Integer(), sa.ForeignKey("physicians.id", ondelete="CASCADE"), nullable=False),
        sa.Column("facility_id", sa.Integer(), sa.ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(40), nullable=False, server_default="practices_at"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("source", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("physician_id", "facility_id", name="uq_physician_facility"),
    )
    op.create_index("ix_physician_facilities_physician", "physician_facilities", ["physician_id"])
    op.create_index("ix_physician_facilities_facility", "physician_facilities", ["facility_id"])

    # Move facility rows that had been parked in `physicians` into `facilities`.
    op.execute("""
        INSERT INTO facilities
            (name, facility_type, phone, address_line1, city, state_province,
             postal_code, country, latitude, longitude, location_precision,
             source, source_uid, is_active, created_at, updated_at)
        SELECT full_name, COALESCE(LOWER(specialty), 'facility'), phone, address_line1,
               city, state_province, postal_code, country, latitude, longitude,
               location_precision, COALESCE(primary_source, 'osm'), source_id,
               TRUE, NOW(), NOW()
        FROM physicians
        WHERE entity_type = 'facility'
        ON CONFLICT (source, source_uid) DO NOTHING
    """)
    op.execute("DELETE FROM physicians WHERE entity_type = 'facility'")
    # `physicians` is now clinicians-only; entity_type stays as a defensive guard.


def downgrade():
    op.drop_table("physician_facilities")
    op.drop_table("facilities")
