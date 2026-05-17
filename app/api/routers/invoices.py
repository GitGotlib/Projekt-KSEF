from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.invoice import (
    InvoiceCreate,
    InvoiceListItem,
    InvoiceResponse,
    InvoiceUpdate,
)
from app.services.client_service import get_client_by_id
from app.services.invoice_service import (
    create_invoice,
    delete_invoice,
    get_invoice_by_id,
    get_invoices,
    update_invoice,
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])


@router.get(
    "",
    response_model=PaginatedResponse[InvoiceListItem],
    summary="Lista faktur",
)
def list_invoices(
    page: int = Query(1, ge=1, description="Numer strony"),
    page_size: int = Query(20, ge=1, le=100, description="Elementów na stronę"),
    client_id: Optional[int] = Query(None, description="Filtruj po kliencie"),
    status: Optional[str] = Query(None, description="Filtruj po statusie (DRAFT, VALIDATED, EXPORTED, ERROR)"),
    invoice_type: Optional[str] = Query(None, description="Filtruj po typie (VAT, CORRECTION, ADVANCE, PROFORMA)"),
    month: Optional[str] = Query(None, description="Filtruj po miesiącu (format YYYY-MM)"),
    search: Optional[str] = Query(None, description="Szukaj po numerze, nazwie lub NIP nabywcy"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    skip = (page - 1) * page_size
    total, items = get_invoices(
        db,
        skip=skip,
        limit=page_size,
        client_id=client_id,
        status=status,
        invoice_type=invoice_type,
        month=month,
        search=search,
    )
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.get(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Szczegóły faktury (z pozycjami)",
)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    invoice = get_invoice_by_id(db, invoice_id)
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Faktura nie istnieje"
        )
    return invoice


@router.post(
    "",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Dodaj fakturę",
)
def create_new_invoice(
    invoice_data: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    client = get_client_by_id(db, invoice_data.client_id)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Klient o id={invoice_data.client_id} nie istnieje",
        )
    if not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nie można dodać faktury do nieaktywnego klienta",
        )

    # Sprawdź unikalność numeru faktury dla danego klienta
    from app.models.invoice import Invoice

    duplicate = (
        db.query(Invoice)
        .filter(
            Invoice.client_id == invoice_data.client_id,
            Invoice.invoice_number == invoice_data.invoice_number,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Faktura o numerze '{invoice_data.invoice_number}' już istnieje dla tego klienta",
        )

    return create_invoice(db, invoice_data, user_id=current_user.id)


@router.put(
    "/{invoice_id}",
    response_model=InvoiceResponse,
    summary="Zaktualizuj fakturę (tylko DRAFT lub ERROR)",
)
def update_existing_invoice(
    invoice_id: int,
    invoice_data: InvoiceUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    try:
        invoice = update_invoice(db, invoice_id, invoice_data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Faktura nie istnieje"
        )
    return invoice


@router.delete(
    "/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Usuń fakturę (tylko DRAFT lub ERROR, tylko admin)",
)
def remove_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Fizyczne usunięcie faktury wraz z pozycjami (CASCADE).
    Dozwolone wyłącznie dla faktur o statusie DRAFT lub ERROR.
    """
    try:
        deleted = delete_invoice(db, invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Faktura nie istnieje"
        )
