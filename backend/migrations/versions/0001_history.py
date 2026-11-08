"""Immutable completed comparison snapshots."""

from alembic import op
import sqlalchemy as sa

revision = "0001_history"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "comparison_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.String(27), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("old_title", sa.String(160), nullable=False),
        sa.Column("new_title", sa.String(160), nullable=False),
        sa.Column("old_version", sa.String(80), nullable=False),
        sa.Column("new_version", sa.String(80), nullable=False),
        sa.Column("old_sha256", sa.String(64), nullable=False),
        sa.Column("new_sha256", sa.String(64), nullable=False),
        sa.Column("engine_version", sa.String(80), nullable=False),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("verdict", sa.String(64), nullable=False),
        sa.Column("coverage_status", sa.String(32), nullable=False),
        sa.Column("summary_json", sa.Text, nullable=False),
        sa.Column("result_json", sa.Text, nullable=False),
        sa.Column("result_bytes", sa.Integer, nullable=False),
        sa.CheckConstraint("status = 'completed'", name="ck_completed_only"),
        sa.CheckConstraint("result_bytes > 0 AND result_bytes <= 8388608", name="ck_result_size"),
        sa.CheckConstraint("result_bytes = length(CAST(result_json AS BLOB))", name="ck_result_byte_count"),
    )
    op.create_index("ix_comparison_runs_created_at", "comparison_runs", ["created_at"])


def downgrade():
    op.drop_index("ix_comparison_runs_created_at", table_name="comparison_runs")
    op.drop_table("comparison_runs")
