from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    CheckConstraint, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="ck_users_role"),
        Index("ix_users_username", "username"),
        Index("ix_users_email", "email"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    role = Column(String(20), nullable=False, server_default="user")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    imports = relationship("Import", back_populates="user")
    invoices = relationship("Invoice", back_populates="user")
    logs = relationship("Log", back_populates="user")
    comments = relationship("Comment", back_populates="user")
