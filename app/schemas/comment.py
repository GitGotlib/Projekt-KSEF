from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator


class CommentCreate(BaseModel):
    content: str
    invoice_id: Optional[int] = None
    import_id: Optional[int] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Treść komentarza nie może być pusta")
        return v

    @field_validator("import_id")
    @classmethod
    def validate_at_least_one_target(cls, v: Optional[int], info) -> Optional[int]:
        # Pydantic v2: sprawdzenie że jest przynajmniej jedno powiązanie
        if v is None and info.data.get("invoice_id") is None:
            raise ValueError(
                "Komentarz musi być powiązany z fakturą (invoice_id) lub importem (import_id)"
            )
        return v


class CommentUpdate(BaseModel):
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Treść komentarza nie może być pusta")
        return v


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    invoice_id: Optional[int]
    import_id: Optional[int]
    content: str
    created_at: datetime
    updated_at: Optional[datetime]
