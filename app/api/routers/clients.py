from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.client import ClientCreate, ClientListItem, ClientResponse, ClientUpdate
from app.schemas.common import PaginatedResponse
from app.services.client_service import (
    create_client,
    deactivate_client,
    get_client_by_company_id,
    get_client_by_id,
    get_client_by_nip,
    get_clients,
    update_client,
)

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.get(
    "",
    response_model=PaginatedResponse[ClientListItem],
    summary="Lista klientów",
)
def list_clients(
    page: int = Query(1, ge=1, description="Numer strony"),
    page_size: int = Query(20, ge=1, le=100, description="Elementów na stronę"),
    search: Optional[str] = Query(None, description="Szukaj po nazwie, NIP lub ID firmy"),
    is_active: Optional[bool] = Query(None, description="Filtruj po statusie aktywności"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    skip = (page - 1) * page_size
    total, items = get_clients(db, skip=skip, limit=page_size, search=search, is_active=is_active)
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.get(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Szczegóły klienta",
)
def get_client(
    client_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    client = get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Klient nie istnieje")
    return client


@router.post(
    "",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dodaj klienta (tylko admin)",
)
def create_new_client(
    client_data: ClientCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if get_client_by_nip(db, client_data.nip):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Klient z NIP '{client_data.nip}' już istnieje",
        )
    if get_client_by_company_id(db, client_data.company_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Klient z ID firmy '{client_data.company_id}' już istnieje",
        )
    return create_client(db, client_data)


@router.put(
    "/{client_id}",
    response_model=ClientResponse,
    summary="Zaktualizuj klienta (tylko admin)",
)
def update_existing_client(
    client_id: int,
    client_data: ClientUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    client = update_client(db, client_id, client_data)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Klient nie istnieje")
    return client


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Dezaktywuj klienta (tylko admin)",
)
def delete_client(
    client_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Dezaktywacja klienta (soft-delete).
    Klient z fakturami nie może być fizycznie usunięty ze względu na integralność danych.
    """
    client = get_client_by_id(db, client_id)
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Klient nie istnieje")
    deactivate_client(db, client_id)
