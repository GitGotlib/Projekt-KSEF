# Import all models here so that SQLAlchemy's metadata is populated
# and Alembic can detect all tables for autogenerate migrations.

from app.models.user import User
from app.models.client import Client
from app.models.import_ import Import
from app.models.staging import StagingInvoice, StagingInvoiceItem
from app.models.invoice import Invoice, InvoiceItem
from app.models.validation_error import ValidationError
from app.models.log import Log
from app.models.comment import Comment
from app.models.enums import (
    UserRole,
    ImportStatus,
    InvoiceType,
    InvoiceStatus,
    ValidationSeverity,
    LogStatus,
)

__all__ = [
    "User",
    "Client",
    "Import",
    "StagingInvoice",
    "StagingInvoiceItem",
    "Invoice",
    "InvoiceItem",
    "ValidationError",
    "Log",
    "Comment",
    "UserRole",
    "ImportStatus",
    "InvoiceType",
    "InvoiceStatus",
    "ValidationSeverity",
    "LogStatus",
]
 