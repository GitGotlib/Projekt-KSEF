import re
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import ImportStatus


class ImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    user_id: int
    import_month: str
    filename: str
    file_size_bytes: Optional[int]
    row_count: int
    error_count: int
    status: str
    notes: Optional[str]
    imported_at: datetime
    updated_at: Optional[datetime]


class ImportListItem(BaseModel):
    """Lżejsza wersja importu do użycia w listach."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    import_month: str
    filename: str
    row_count: int
    error_count: int
    status: str
    imported_at: datetime


class ImportStatusUpdate(BaseModel):
    """Ręczna zmiana statusu importu przez admina."""

    status: ImportStatus
    notes: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {s.value for s in ImportStatus}
        if v not in allowed:
            raise ValueError(f"Status musi być jednym z: {', '.join(allowed)}")
        return v


_MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")


def validate_import_month(value: str) -> str:
    """Sprawdza format YYYY-MM i zakres miesiąca."""
    if not _MONTH_RE.match(value):
        raise ValueError("import_month musi mieć format YYYY-MM (np. 2024-01)")
    return value
