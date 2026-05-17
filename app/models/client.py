from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    CheckConstraint, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database.base import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        # NIP must be exactly 10 digits
        CheckConstraint(r"nip ~ '^\d{10}$'", name="ck_clients_nip_format"),
        Index("ix_clients_company_id", "company_id"),
        Index("ix_clients_nip", "nip"),
        Index("ix_clients_company_name", "company_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # ID_FIRMY – internal business identifier used in TSV files
    company_id = Column(String(50), unique=True, nullable=False)
    # NIP – Polish Tax Identification Number (10 digits)
    nip = Column(String(10), unique=True, nullable=False)
    company_name = Column(String(255), nullable=False)
    address_street = Column(String(255))
    address_city = Column(String(100))
    address_postal_code = Column(String(10))
    address_country = Column(String(3), nullable=False, server_default="PL")
    email = Column(String(255))
    phone = Column(String(20))
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    imports = relationship("Import", back_populates="client")
    invoices = relationship("Invoice", back_populates="client")
    logs = relationship("Log", back_populates="client")
