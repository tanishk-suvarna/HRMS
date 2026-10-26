"""Add organization communication and resume storage.

Revision ID: 002_messages_and_resumes
"""

from alembic import op
import sqlalchemy as sa


revision = "002_messages_and_resumes"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "messages" not in tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_messages_organization_id", "messages", ["organization_id"])
        op.create_index("ix_messages_sender_user_id", "messages", ["sender_user_id"])
    if "resumes" not in tables:
        op.create_table(
            "resumes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
            sa.Column("candidate_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("content_type", sa.String(length=120), nullable=False),
            sa.Column("text_content", sa.Text(), nullable=False),
            sa.Column("extracted_details", sa.JSON(), nullable=False),
            sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_resumes_organization_id", "resumes", ["organization_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "resumes" in tables:
        op.drop_index("ix_resumes_organization_id", table_name="resumes")
        op.drop_table("resumes")
    if "messages" in tables:
        op.drop_index("ix_messages_sender_user_id", table_name="messages")
        op.drop_index("ix_messages_organization_id", table_name="messages")
        op.drop_table("messages")
