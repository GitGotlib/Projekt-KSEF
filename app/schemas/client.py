from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

from app.validators.nip import validate_nip


class ClientCreate(BaseModel):
    company_id: str
    nip: str
    company_name: str
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_postal_code: Optional[str] = None
    address_country: str = "PL"
    email: Optional[EmailStr] = None
    phone: Optional[str] = None

    @field_validator("nip")
    @classmethod
    def validate_nip_field(cls, v: str) -> str:
        return validate_nip(v)

    @field_validator("company_id")
    @classmethod
    def validate_company_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("company_id nie może być pusty")
        return v

    @field_validator("address_country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        v = v.strip().upper()
        if len(v) != 2 and len(v) != 3:
            raise ValueError("Kod kraju musi mieć 2 lub 3 znaki (np. PL)")
        return v


class ClientUpdate(BaseModel):
    company_name: Optional[str] = None
    address_street: Optional[str] = None
    address_city: Optional[str] = None
    address_postal_code: Optional[str] = None
    address_country: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None


class ClientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: str
    nip: str
    company_name: str
    address_street: Optional[str]
    address_city: Optional[str]
    address_postal_code: Optional[str]
    address_country: str
    email: Optional[str]
    phone: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]


class ClientListItem(BaseModel):
    """Lżejsza wersja klienta do użycia w listach."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: str
    nip: str
    company_name: str
    address_city: Optional[str]
    is_active: bool
