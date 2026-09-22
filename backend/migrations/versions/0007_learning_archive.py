"""Add learning archive and knowledge document foundation."""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


ENTRY_TYPES = "'study','assignment','project','output','reading','research','internship','exam','reflection','other'"
DOCUMENT_TYPES = "'note','slides','assignment','solution','code','paper','output','reflection','reference','exam','other'"


def timestamps():
    return [sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("created_at", sa.String(), nullable=False),
            sa.Column("updated_at", sa.String(), nullable=False)]


def upgrade():
    op.add_column("tasks", sa.Column("track_learning", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "learning_entries",
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="RESTRICT")),
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.id", ondelete="SET NULL")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Integer()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reflection", sa.Text(), nullable=False),
        sa.Column("problems", sa.Text(), nullable=False),
        sa.Column("next_action", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("concepts", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String()),
        *timestamps(),
        sa.CheckConstraint("duration_minutes >= 0"),
        sa.CheckConstraint("progress IS NULL OR progress BETWEEN 0 AND 100"),
        sa.CheckConstraint(f"entry_type IN ({ENTRY_TYPES})"),
        sa.CheckConstraint("status IN ('in_progress','completed','partial','abandoned')"),
    )
    op.create_index("ix_learning_entries_date", "learning_entries", ["date"])
    op.create_index("ix_learning_entries_project_id", "learning_entries", ["project_id"])
    op.create_index("ix_learning_entries_task_id", "learning_entries", ["task_id"])
    op.create_index("ix_learning_entries_entry_type", "learning_entries", ["entry_type"])
    op.create_index("ix_learning_entries_status", "learning_entries", ["status"])
    op.create_index("ix_learning_project_date", "learning_entries", ["project_id", "date"])

    op.create_table(
        "knowledge_documents",
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("original_filename", sa.String(255)),
        sa.Column("storage_path", sa.Text()),
        sa.Column("file_type", sa.String(30), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="RESTRICT")),
        sa.Column("knowledge_date", sa.String(10), nullable=False),
        sa.Column("upload_date", sa.String(10), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("is_output", sa.Boolean(), nullable=False),
        sa.Column("processing_status", sa.String(20), nullable=False),
        sa.Column("parser_name", sa.String(100)),
        sa.Column("parser_version", sa.String(30)),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("extracted_at", sa.String()),
        sa.Column("extraction_error", sa.Text()),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("deleted_at", sa.String()),
        *timestamps(),
        sa.CheckConstraint("source_type IN ('file','text')"),
        sa.CheckConstraint("file_size >= 0"),
        sa.CheckConstraint(f"document_type IN ({DOCUMENT_TYPES})"),
        sa.CheckConstraint("processing_status IN ('stored','parsing','ready','failed')"),
    )
    for name in ("sha256", "project_id", "knowledge_date", "upload_date", "document_type", "is_output", "processing_status"):
        op.create_index(f"ix_knowledge_documents_{name}", "knowledge_documents", [name], unique=name == "sha256")
    op.create_index("ix_document_project_date", "knowledge_documents", ["project_id", "knowledge_date"])

    op.create_table(
        "learning_entry_documents",
        sa.Column("learning_entry_id", sa.String(36), sa.ForeignKey("learning_entries.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("relationship", sa.String(20), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.CheckConstraint("relationship IN ('evidence','output','reference')"),
    )
    op.create_table(
        "document_insights",
        sa.Column("document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("key_takeaways", sa.JSON(), nullable=False),
        sa.Column("concepts", sa.JSON(), nullable=False),
        sa.Column("open_questions", sa.JSON(), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("suggested_tags", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(30)), sa.Column("model", sa.String(200)),
        sa.Column("prompt_version", sa.String(30)), sa.Column("generated_at", sa.String(), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_document_insights_document_id", "document_insights", ["document_id"], unique=True)
    op.create_table(
        "daily_summaries",
        sa.Column("date", sa.String(10), nullable=False, unique=True),
        sa.Column("summary", sa.Text(), nullable=False), sa.Column("learning_summary", sa.Text(), nullable=False),
        sa.Column("completed_items", sa.JSON(), nullable=False), sa.Column("key_takeaways", sa.JSON(), nullable=False),
        sa.Column("open_questions", sa.JSON(), nullable=False), sa.Column("outputs", sa.JSON(), nullable=False),
        sa.Column("time_summary", sa.JSON(), nullable=False), sa.Column("next_actions", sa.JSON(), nullable=False),
        sa.Column("source_fingerprint", sa.String(64)), sa.Column("generation_type", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(30)), sa.Column("model", sa.String(200)),
        sa.Column("prompt_version", sa.String(30)), sa.Column("generated_at", sa.String()),
        *timestamps(), sa.CheckConstraint("generation_type IN ('manual','ai')"),
    )
    op.create_index("ix_daily_summaries_date", "daily_summaries", ["date"], unique=True)


def downgrade():
    op.drop_table("daily_summaries")
    op.drop_table("document_insights")
    op.drop_table("learning_entry_documents")
    op.drop_table("knowledge_documents")
    op.drop_table("learning_entries")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("track_learning")
