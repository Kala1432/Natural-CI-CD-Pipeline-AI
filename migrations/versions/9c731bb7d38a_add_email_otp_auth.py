"""Add verified email and OTP authentication

Revision ID: 9c731bb7d38a
Revises: 4d4215a87fae
"""

from alembic import op
import sqlalchemy as sa


revision = "9c731bb7d38a"
down_revision = "4d4215a87fae"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "email_otps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_otps_user_id", "email_otps", ["user_id"])
    op.alter_column("users", "email_verified", server_default=None)


def downgrade():
    op.drop_index("ix_email_otps_user_id", table_name="email_otps")
    op.drop_table("email_otps")
    op.drop_column("users", "email_verified")
