"""initial schema: streams and analysis_results

Revision ID: 0001
Revises:
Create Date: 2026-06-17

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "streams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("kvs_stream_arn", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CREATED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_streams_name", "streams", ["name"])

    op.create_table(
        "analysis_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "stream_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("streams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("analysis_type", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("analysis_results")
    op.drop_index("ix_streams_name", table_name="streams")
    op.drop_table("streams")
