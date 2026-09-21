"""Add isolated conversation storage; preserve all planning tables."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False))
    op.create_table("chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.CheckConstraint("role IN ('system','user','assistant','tool')", name="ck_chat_role"),
        sa.CheckConstraint("status IN ('generating','completed','stopped','error')", name="ck_chat_status"))
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])
    op.create_table("ai_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("num_ctx", sa.Integer(), nullable=False),
        sa.Column("temperature", sa.String(), nullable=False),
        sa.Column("think", sa.Boolean(), nullable=False))


def downgrade():
    op.drop_table("ai_settings")
    op.drop_index("ix_chat_messages_conversation_id", "chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("conversations")
