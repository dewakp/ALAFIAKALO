"""Add subscriptions + subscription_events tables (billing / entitlement)."""

from alembic import op
import sqlalchemy as sa

revision = 'bb002_add_subscriptions'
# Sits after the (now re-parented) medication-source migration, so the chain is
# linear: ll001 → aa001_add_medication_source → bb002. Subscription tables are
# independent (subscriptions / subscription_events).
down_revision = 'aa001_add_medication_source'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='none'),
        sa.Column('provider', sa.String(20), nullable=False, server_default='none'),
        sa.Column('plan', sa.String(40), nullable=False, server_default='plus_monthly'),
        sa.Column('price_usd', sa.Float(), nullable=True),
        sa.Column('current_period_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancel_at_period_end', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('canceled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('paypal_subscription_id', sa.String(255), nullable=True),
        sa.Column('google_purchase_token', sa.Text(), nullable=True),
        sa.Column('google_order_id', sa.String(255), nullable=True),
        sa.Column('apple_original_transaction_id', sa.String(255), nullable=True),
        sa.Column('apple_transaction_id', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_subscriptions_id', 'subscriptions', ['id'])
    op.create_index('ix_subscriptions_user_id', 'subscriptions', ['user_id'], unique=True)
    op.create_index('ix_subscriptions_stripe_customer_id', 'subscriptions', ['stripe_customer_id'])
    op.create_index('ix_subscriptions_stripe_subscription_id', 'subscriptions', ['stripe_subscription_id'])
    op.create_index('ix_subscriptions_paypal_subscription_id', 'subscriptions', ['paypal_subscription_id'])
    op.create_index('ix_subscriptions_apple_original_transaction_id', 'subscriptions',
                    ['apple_original_transaction_id'])

    op.create_table(
        'subscription_events',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('provider', sa.String(20), nullable=False),
        sa.Column('event_id', sa.String(255), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=True),
        sa.Column('payload', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_subscription_events_id', 'subscription_events', ['id'])
    op.create_index('ix_subscription_events_user_id', 'subscription_events', ['user_id'])
    op.create_index('ix_subscription_events_event_id', 'subscription_events', ['event_id'])
    # One-time application per provider event (idempotency).
    op.create_index('ux_subscription_events_provider_event', 'subscription_events',
                    ['provider', 'event_id'], unique=True)


def downgrade():
    op.drop_table('subscription_events')
    op.drop_table('subscriptions')
