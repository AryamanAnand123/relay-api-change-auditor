"""Immutable comparison snapshots; the first version needs a single payload table."""

import sqlalchemy as sa

metadata = sa.MetaData()
runs = sa.Table(
    "comparison_runs", metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("created_at", sa.String(27), nullable=False, index=True),
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
