from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin
from app.database import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.validation_error import ValidationErrorResponse, ValidationErrorResolve
from app.services.import_service import get_import_by_id
from app.services.validation_service import (
    get_validation_errors,
    resolve_validation_error,
    validate_import,
)

router = APIRouter(prefix="/validation", tags=["Validation"])


# ---------------------------------------------------------------------------
# Uruchomienie walidacji
# ---------------------------------------------------------------------------


class ValidationRunResponse(BaseModel):
    import_id: int
    total_invoices: int
    invalid_invoices: int
    total_errors: int
    total_warnings: int
    new_status: str
    message: str


@router.post(
    "/run/{import_id}",
    response_model=ValidationRunResponse,
    summary="Uruchom walidację dla importu",
)
def run_validation(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Waliduje wszystkie faktury w strefie staging dla danego importu.

    - Usuwa poprzednie wyniki walidacji.
    - Sprawdza: pola wymagane, NIP (suma kontrolna), formaty dat,
      poprawność kwot, zgodność netto+VAT=brutto, walutę, typ faktury.
    - Aktualizuje flagi `is_valid` na rekordach staging.
    - Zmienia status importu na `VALIDATED` (brak ERRORów) lub `ERROR`.
    """
    import_record = get_import_by_id(db, import_id)
    if not import_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")

    if import_record.status not in ("LOADED", "VALIDATED", "ERROR"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Walidacja możliwa tylko dla importów ze statusem LOADED, VALIDATED lub ERROR. "
                f"Aktualny status: {import_record.status}"
            ),
        )

    result = validate_import(db, import_id)

    if result.total_errors == 0 and result.total_warnings == 0:
        message = f"Walidacja zakończona pomyślnie. Sprawdzono {result.total_invoices} faktur."
    elif result.total_errors == 0:
        message = (
            f"Walidacja zakończona z ostrzeżeniami ({result.total_warnings}). "
            f"Sprawdzono {result.total_invoices} faktur."
        )
    else:
        message = (
            f"Walidacja wykryła {result.total_errors} błęd(ów) "
            f"i {result.total_warnings} ostrzeżeń "
            f"w {result.invalid_invoices}/{result.total_invoices} fakturach."
        )

    return ValidationRunResponse(
        import_id=result.import_id,
        total_invoices=result.total_invoices,
        invalid_invoices=result.invalid_invoices,
        total_errors=result.total_errors,
        total_warnings=result.total_warnings,
        new_status=result.new_status,
        message=message,
    )


# ---------------------------------------------------------------------------
# Przeglądanie błędów walidacji
# ---------------------------------------------------------------------------


@router.get(
    "/errors/{import_id}",
    response_model=PaginatedResponse[ValidationErrorResponse],
    summary="Lista błędów walidacji dla importu",
)
def list_validation_errors(
    import_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    severity: Optional[str] = Query(None, description="Filtruj po ważności: ERROR lub WARNING"),
    is_resolved: Optional[bool] = Query(None, description="Filtruj po statusie rozwiązania"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not get_import_by_id(db, import_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")

    skip = (page - 1) * page_size
    total, items = get_validation_errors(
        db,
        import_id=import_id,
        severity=severity,
        is_resolved=is_resolved,
        skip=skip,
        limit=page_size,
    )
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


# ---------------------------------------------------------------------------
# Oznaczanie błędów jako rozwiązanych
# ---------------------------------------------------------------------------


@router.patch(
    "/errors/{error_id}/resolve",
    response_model=ValidationErrorResponse,
    summary="Oznacz błąd walidacji jako rozwiązany",
)
def resolve_error(
    error_id: int,
    body: ValidationErrorResolve,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    err = resolve_validation_error(db, error_id, body.is_resolved)
    if not err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Błąd walidacji nie istnieje"
        )
    return err


# ---------------------------------------------------------------------------
# Reset walidacji (admin) – czyści błędy i cofa status do LOADED
# ---------------------------------------------------------------------------


@router.delete(
    "/errors/{import_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Usuń wszystkie błędy walidacji dla importu (admin)",
)
def clear_validation_errors(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    from app.models.validation_error import ValidationError
    from app.models.staging import StagingInvoice

    import_record = get_import_by_id(db, import_id)
    if not import_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")

    db.query(ValidationError).filter(
        ValidationError.import_id == import_id
    ).delete(synchronize_session=False)

    # Zresetuj flagi is_valid w staging
    db.query(StagingInvoice).filter(
        StagingInvoice.import_id == import_id
    ).update({"is_valid": None}, synchronize_session=False)

    import_record.status = "LOADED"
    import_record.error_count = 0
    db.commit()
