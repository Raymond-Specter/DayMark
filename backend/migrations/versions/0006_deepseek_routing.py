"""Add AI provider mode and request-level action metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("ai_settings") as batch:
        batch.add_column(sa.Column("mode", sa.String(20), nullable=False, server_default="auto"))
    with op.batch_alter_table("agent_action_logs") as batch:
        batch.add_column(sa.Column("request_id", sa.String(36)))
        batch.add_column(sa.Column("provider", sa.String(30)))
        batch.add_column(sa.Column("model", sa.String(200)))
        batch.add_column(sa.Column("fingerprint", sa.String(64)))
        batch.create_index("ix_agent_action_logs_request_id", ["request_id"])
        batch.create_unique_constraint("uq_agent_action_fingerprint", ["fingerprint"])
    with op.batch_alter_table("pending_agent_actions") as batch:
        batch.add_column(sa.Column("request_id", sa.String(36)))
        batch.add_column(sa.Column("provider", sa.String(30)))
        batch.add_column(sa.Column("model", sa.String(200)))


def downgrade():
    with op.batch_alter_table("pending_agent_actions") as batch:
        batch.drop_column("model")
        batch.drop_column("provider")
        batch.drop_column("request_id")
    with op.batch_alter_table("agent_action_logs") as batch:
        batch.drop_constraint("uq_agent_action_fingerprint", type_="unique")
        batch.drop_index("ix_agent_action_logs_request_id")
        batch.drop_column("fingerprint")
        batch.drop_column("model")
        batch.drop_column("provider")
        batch.drop_column("request_id")
    with op.batch_alter_table("ai_settings") as batch:
        batch.drop_column("mode")
