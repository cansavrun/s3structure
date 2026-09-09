"""Initial tenant, API key and audit schema. Explicit schema keeps migration history stable."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("bucket", sa.String(63), nullable=False),
        sa.Column("prefix", sa.String(512), nullable=False),
        sa.Column("role_arn", sa.String(256)),
        sa.Column("external_id", sa.String(128)),
        sa.Column("kms_key_arn", sa.String(256)),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("customer_id", sa.String(64), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_api_keys_customer_id", "api_keys", ["customer_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_id", sa.String(64)),
        sa.Column("key_id", sa.String(32)),
        sa.Column("action", sa.String(48), nullable=False),
        sa.Column("object_path", sa.String(1024)),
        sa.Column("request_id", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
    )
    op.create_index("ix_audit_customer_created", "audit_events", ["customer_id", "created_at"])


def downgrade():
    op.drop_table("audit_events")
    op.drop_table("api_keys")
    op.drop_table("customers")
