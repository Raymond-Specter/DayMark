"""Stable message order even when the system clock has millisecond precision."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("chat_messages") as batch:
        batch.add_column(sa.Column("position", sa.Integer(), nullable=False, server_default="0"))
    op.execute("""WITH ordered AS (
        SELECT id, ROW_NUMBER() OVER (PARTITION BY conversation_id ORDER BY created_at, CASE role WHEN 'user' THEN 0 ELSE 1 END, id) AS ordinal
        FROM chat_messages)
        UPDATE chat_messages SET position = (SELECT ordinal FROM ordered WHERE ordered.id = chat_messages.id)""")
    with op.batch_alter_table("chat_messages") as batch:
        batch.alter_column("position", server_default=None)
        batch.create_unique_constraint("uq_chat_position", ["conversation_id", "position"])


def downgrade():
    with op.batch_alter_table("chat_messages") as batch:
        batch.drop_constraint("uq_chat_position", type_="unique")
        batch.drop_column("position")
