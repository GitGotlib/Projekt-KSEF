from sqlalchemy import (
    Column, Integer, DateTime, Text,
    ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Comment(Base):
    """
    Administrative comments that can be attached to an invoice or an import batch.
    """

    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_user_id", "user_id"),
        Index("ix_comments_invoice_id", "invoice_id"),
        Index("ix_comments_import_id", "import_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Comment can be attached to an invoice, an import batch, or both
    invoice_id = Column(Integer, ForeignKey("invoices.id", ondelete="CASCADE"))
    import_id = Column(Integer, ForeignKey("imports.id", ondelete="CASCADE"))

    content = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user = relationship("User", back_populates="comments")
    invoice = relationship("Invoice", back_populates="comments")
    import_record = relationship("Import", back_populates="comments")
