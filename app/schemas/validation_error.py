from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ValidationErrorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    import_id: Optional[int]
    invoice_id: Optional[int]
    staging_invoice_id: Optional[int]
    row_number: Optional[int]
    field_name: Optional[str]
    error_code: Optional[str]
    error_message: str
    severity: str
    is_resolved: bool
    created_at: datetime


class ValidationErrorResolve(BaseModel):
    """Oznaczenie błędu jako rozwiązanego."""

    is_resolved: bool = True
