"""Add missing Firebase field columns to nutrition_logs and bowel_movements

Revision ID: v001_add_firebase_field_columns
Revises: u001_media_s3_storage
Create Date: 2026-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = 'v001_add_firebase_field_columns'
down_revision = 'u001_media_s3_storage'
branch_labels = None
depends_on = None


def upgrade():
    # nutrition_logs: meal timing and pre/post weight (from Firebase startTime/endTime/preMealWeightKg/postMealWeightKg)
    op.add_column('nutrition_logs', sa.Column('start_time', sa.Time(), nullable=True))
    op.add_column('nutrition_logs', sa.Column('end_time', sa.Time(), nullable=True))
    op.add_column('nutrition_logs', sa.Column('pre_meal_weight_kg', sa.Float(), nullable=True))
    op.add_column('nutrition_logs', sa.Column('post_meal_weight_kg', sa.Float(), nullable=True))
    op.add_column('nutrition_logs', sa.Column('food_image_uris', sa.Text(), nullable=True))
    op.add_column('nutrition_logs', sa.Column('recipe_url', sa.Text(), nullable=True))

    # bowel_movements: pre/post event weights (from Firebase preEventWeightKg/postEventWeightKg)
    op.add_column('bowel_movements', sa.Column('pre_event_weight_kg', sa.Float(), nullable=True))
    op.add_column('bowel_movements', sa.Column('post_event_weight_kg', sa.Float(), nullable=True))
    op.add_column('bowel_movements', sa.Column('event_type', sa.String(50), nullable=True))
    op.add_column('bowel_movements', sa.Column('image_uri', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('nutrition_logs', 'recipe_url')
    op.drop_column('nutrition_logs', 'food_image_uris')
    op.drop_column('nutrition_logs', 'post_meal_weight_kg')
    op.drop_column('nutrition_logs', 'pre_meal_weight_kg')
    op.drop_column('nutrition_logs', 'end_time')
    op.drop_column('nutrition_logs', 'start_time')

    op.drop_column('bowel_movements', 'image_uri')
    op.drop_column('bowel_movements', 'event_type')
    op.drop_column('bowel_movements', 'post_event_weight_kg')
    op.drop_column('bowel_movements', 'pre_event_weight_kg')
