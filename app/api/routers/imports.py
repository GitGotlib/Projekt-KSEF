from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.import_ import ImportListItem, ImportResponse, ImportStatusUpdate, validate_import_month
from app.schemas.staging import StagingInvoiceItemResponse, StagingInvoiceResponse
from app.services.client_service import get_client_by_company_id
from app.services.import_service import (
    create_import_record,
    get_import_by_id,
    get_imports,
    get_staging_invoices,
    get_staging_items,
    load_invoices_to_staging,
    load_items_to_staging,
    update_import_status,
)
from app.utils.tsv_parser import parse_and_validate_tsv

router = APIRouter(prefix="/imports", tags=["Imports"])

_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post(
    "/upload",
    response_model=ImportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Prześlij plik TSV do importu",
)
async def upload_tsv(
    file: UploadFile = File(..., description="Plik TSV (separator TAB, UTF-8)"),
    import_month: str = Form(..., description="Miesiąc rozliczeniowy (YYYY-MM)"),
    file_type: str = Form(
        default="invoices",
        description="Typ pliku: 'invoices' (faktury) lub 'items' (pozycje faktur)",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Workflow importu:
    1. Wczytaj i sparsuj plik TSV.
    2. Waliduj nagłówki i spójność ID_FIRMY.
    3. Znajdź klienta po ID_FIRMY.
    4. Utwórz rekord importu (status NEW).
    5. Załaduj dane do staging via PostgreSQL COPY (status → LOADED).
    6. W razie błędu – ustaw status ERROR i zwróć szczegóły.
    """
    # -- Walidacja parametrów wejściowych --
    try:
        validate_import_month(import_month)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if file_type not in ("invoices", "items"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="file_type musi być 'invoices' lub 'items'",
        )

    if not file.filename or not file.filename.lower().endswith((".tsv", ".txt", ".tab")):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Przesłany plik musi mieć rozszerzenie .tsv, .txt lub .tab",
        )

    # -- Odczyt pliku --
    raw_bytes = await file.read()
    if len(raw_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Plik przekracza maksymalny rozmiar {_MAX_FILE_SIZE // (1024*1024)} MB",
        )

    try:
        content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nie można odczytać pliku. Upewnij się, że kodowanie to UTF-8.",
        )

    # -- Parsowanie i walidacja TSV --
    parse_result = parse_and_validate_tsv(content, file_type)
    if not parse_result.is_valid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Plik TSV nie przeszedł walidacji",
                "errors": parse_result.errors,
            },
        )

    # -- Identyfikacja klienta po ID_FIRMY --
    client = get_client_by_company_id(db, parse_result.id_firmy)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nie znaleziono klienta z ID_FIRMY='{parse_result.id_firmy}'",
        )
    if not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Klient '{parse_result.id_firmy}' jest nieaktywny",
        )

    # -- Tworzenie rekordu importu --
    import_record = create_import_record(
        db=db,
        client_id=client.id,
        user_id=current_user.id,
        import_month=import_month,
        filename=file.filename,
        file_size_bytes=len(raw_bytes),
    )

    # -- Ładowanie do staging via COPY --
    try:
        if file_type == "invoices":
            load_invoices_to_staging(db, import_record, parse_result)
        else:
            load_items_to_staging(db, import_record, parse_result)
    except Exception as exc:
        # import_record.status jest już ERROR (ustawiony w serwisie)
        db.refresh(import_record)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Błąd podczas ładowania danych do staging: {exc}",
        )

    db.refresh(import_record)
    return import_record


# ---------------------------------------------------------------------------
# Lista importów
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedResponse[ImportListItem],
    summary="Lista importów",
)
def list_imports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    client_id: Optional[int] = Query(None, description="Filtruj po kliencie"),
    status: Optional[str] = Query(None, description="Filtruj po statusie"),
    import_month: Optional[str] = Query(None, description="Filtruj po miesiącu (YYYY-MM)"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    skip = (page - 1) * page_size
    total, items = get_imports(
        db,
        skip=skip,
        limit=page_size,
        client_id=client_id,
        status=status,
        import_month=import_month,
    )
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.get(
    "/{import_id}",
    response_model=ImportResponse,
    summary="Szczegóły importu",
)
def get_import(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    record = get_import_by_id(db, import_id)
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")
    return record


# ---------------------------------------------------------------------------
# Zmiana statusu (admin)
# ---------------------------------------------------------------------------


@router.patch(
    "/{import_id}/status",
    response_model=ImportResponse,
    summary="Zmień status importu (tylko admin)",
)
def change_import_status(
    import_id: int,
    body: ImportStatusUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    record = update_import_status(
        db,
        import_id,
        status=body.status.value,
        notes=body.notes,
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")
    return record


# ---------------------------------------------------------------------------
# Podgląd danych staging (audyt / debugowanie)
# ---------------------------------------------------------------------------


@router.get(
    "/{import_id}/staging-invoices",
    response_model=PaginatedResponse[StagingInvoiceResponse],
    summary="Podgląd danych staging – faktury",
)
def list_staging_invoices(
    import_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not get_import_by_id(db, import_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")
    skip = (page - 1) * page_size
    total, items = get_staging_invoices(db, import_id, skip=skip, limit=page_size)
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.get(
    "/{import_id}/staging-items",
    response_model=PaginatedResponse[StagingInvoiceItemResponse],
    summary="Podgląd danych staging – pozycje faktur",
)
def list_staging_items(
    import_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not get_import_by_id(db, import_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")
    skip = (page - 1) * page_size
    total, items = get_staging_items(db, import_id, skip=skip, limit=page_size)
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)
