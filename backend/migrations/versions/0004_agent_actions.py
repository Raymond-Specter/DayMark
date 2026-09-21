"""Agent action audit log and exact pending confirmations."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_action_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_arguments", sa.JSON(), nullable=False),
        sa.Column("permission_level", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("affected_entities", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("undone_at", sa.String()),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_agent_action_logs_conversation_id", "agent_action_logs", ["conversation_id"])
    op.create_index("ix_agent_action_logs_tool_name", "agent_action_logs", ["tool_name"])
    op.create_index("ix_agent_action_logs_status", "agent_action_logs", ["status"])
    op.create_table(
        "pending_agent_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_name", sa.String(100), nullable=False),
        sa.Column("tool_arguments", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("resolved_at", sa.String()),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index("ix_pending_agent_actions_conversation_id", "pending_agent_actions", ["conversation_id"])
    op.create_index("ix_pending_agent_actions_status", "pending_agent_actions", ["status"])


def downgrade():
    op.drop_table("pending_agent_actions")
    op.drop_table("agent_action_logs")
