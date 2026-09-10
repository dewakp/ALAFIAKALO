"""Names in parts, and a face to go with them.

`full_name` was one required string. A single field cannot be sorted, greeted,
or matched on properly — "Dr Ngozi Adaeze Okafor Jr" is five facts in one box —
and a clinician list cannot show "Okafor, N." from it without guessing which
word is the surname.

`profile_picture_url` has existed since the first migration and NOTHING ever
wrote to it: no endpoint set it and no screen read it. So every avatar in the
app is initials on a coloured circle.

Additive only, no drops (§3ao):

  first_name / last_name    the parts. Nullable HERE because 85 existing rows
                            have only `full_name`; the API requires both on new
                            input, and `full_name` stays authoritative for
                            display until a row is split.
  middle_name               optional, profile-only
  name_prefix / name_suffix Dr, Prof / Jr, III — profile-only
  profile_picture_data      the image itself, base64. S3 is NOT configured in
                            production (zero S3_ env vars), so media already
                            falls back to base64 in the database; an avatar is
                            small enough that this is the honest storage rather
                            than a dependency nobody has provisioned.

Revision ID: ab001_name_parts_and_avatar
Revises: zz001_record_shared_notification
"""

from alembic import op
import sqlalchemy as sa

revision = "ab001_name_parts_and_avatar"
down_revision = "zz001_record_shared_notification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("first_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("middle_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("name_prefix", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("name_suffix", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("profile_picture_data", sa.Text(), nullable=True))

    # Backfill from what exists. First word is the given name, LAST word is the
    # family name, anything between is the middle name — which is why
    # middle_name is filled here too rather than left for the patient.
    #
    # This is right for most and wrong for some (a two-word surname becomes a
    # middle name). It is a starting point the patient can correct in Profile,
    # not a claim about their name. A single-word name keeps it as first_name
    # and leaves last_name NULL rather than inventing a surname.
    op.execute("""
        UPDATE users
           SET first_name = NULLIF(split_part(trim(full_name), ' ', 1), ''),
               last_name = CASE
                   WHEN array_length(string_to_array(trim(full_name), ' '), 1) > 1
                   THEN (string_to_array(trim(full_name), ' '))[
                            array_length(string_to_array(trim(full_name), ' '), 1)]
                   ELSE NULL END,
               middle_name = CASE
                   WHEN array_length(string_to_array(trim(full_name), ' '), 1) > 2
                   THEN array_to_string(
                            (string_to_array(trim(full_name), ' '))[
                                2 : array_length(string_to_array(trim(full_name), ' '), 1) - 1],
                            ' ')
                   ELSE NULL END
         WHERE full_name IS NOT NULL AND first_name IS NULL
    """)


def downgrade() -> None:
    for col in ("profile_picture_data", "name_suffix", "name_prefix",
                "middle_name", "last_name", "first_name"):
        op.drop_column("users", col)
