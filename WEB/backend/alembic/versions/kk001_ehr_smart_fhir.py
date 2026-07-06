"""SMART on FHIR patient-portal access (Epic MyChart: Kaiser, Trinity Health, …).

- ehr_endpoints: vendor directory of portal FHIR base URLs (Epic R4 list).
- ehr_oauth_states: short-lived PKCE state for in-flight authorizations.
- ehr_connections: + org_name, token endpoint, encrypted access/refresh tokens.
"""

from alembic import op
import sqlalchemy as sa

revision = "kk001_ehr_smart_fhir"
down_revision = "jj001_phone_number"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ehr_connections", sa.Column("org_name", sa.String(255), nullable=True))
    op.add_column("ehr_connections", sa.Column("token_endpoint", sa.Text(), nullable=True))
    op.add_column("ehr_connections", sa.Column("access_token_enc", sa.Text(), nullable=True))
    op.add_column("ehr_connections", sa.Column("refresh_token_enc", sa.Text(), nullable=True))
    op.add_column("ehr_connections", sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "ehr_endpoints",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("vendor", sa.String(50), nullable=False, server_default="epic", index=True),
        sa.Column("name", sa.String(255), nullable=False, index=True),
        sa.Column("fhir_base_url", sa.Text(), nullable=False, unique=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "ehr_oauth_states",
        sa.Column("state", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("endpoint_id", sa.Integer(), nullable=True),
        sa.Column("org_name", sa.String(255), nullable=True),
        sa.Column("fhir_base_url", sa.Text(), nullable=False),
        sa.Column("token_endpoint", sa.Text(), nullable=False),
        sa.Column("code_verifier", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("ehr_oauth_states")
    op.drop_table("ehr_endpoints")
    for col in ("token_expires_at", "refresh_token_enc", "access_token_enc", "token_endpoint", "org_name"):
        op.drop_column("ehr_connections", col)
