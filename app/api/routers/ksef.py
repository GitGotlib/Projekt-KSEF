import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.database import get_db
from app.models.invoice import Invoice
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.invoice import InvoiceResponse
from app.services.import_service import get_import_by_id
from app.services.ksef_xml_service import (
    build_invoice_xml,
    build_xml_zip,
    generate_xml_for_import,
)
from app.services.transform_service import TransformResult, get_invoices_for_import, transform_import

router = APIRouter(prefix="/ksef", tags=["KSeF"])


# ---------------------------------------------------------------------------
# Schematy odpowiedzi
# ---------------------------------------------------------------------------


class TransformResponse(BaseModel):
    import_id: int
    created: int
    skipped: int
    failed: int
    message: str


class GenerateResponse(BaseModel):
    import_id: int
    generated: int
    message: str


# ---------------------------------------------------------------------------
# Krok 1: Transformacja staging → Invoice
# ---------------------------------------------------------------------------


@router.post(
    "/transform/{import_id}",
    response_model=TransformResponse,
    status_code=status.HTTP_200_OK,
    summary="Transformuj zwalidowane dane staging → faktury docelowe",
)
def transform(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Przekształca rekordy staging z is_valid=True w faktury docelowe (Invoice + InvoiceItem).

    - Import musi mieć status VALIDATED lub ERROR (aby umożliwić ponowne uruchomienie).
    - Faktury już istniejące (client_id + invoice_number) są pomijane.
    """
    import_record = get_import_by_id(db, import_id)
    if not import_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")

    if import_record.status not in ("VALIDATED", "ERROR", "EXPORTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Transformacja możliwa tylko dla importów ze statusem VALIDATED, ERROR lub EXPORTED. "
                f"Aktualny status: {import_record.status}"
            ),
        )

    try:
        result: TransformResult = transform_import(db, import_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return TransformResponse(
        import_id=result.import_id,
        created=result.created,
        skipped=result.skipped,
        failed=result.failed,
        message=(
            f"Transformacja zakończona: {result.created} nowych faktur, "
            f"{result.skipped} pominiętych (duplikaty), {result.failed} błędów."
        ),
    )


# ---------------------------------------------------------------------------
# Krok 2: Generowanie XML KSeF
# ---------------------------------------------------------------------------


@router.post(
    "/generate/{import_id}",
    response_model=GenerateResponse,
    status_code=status.HTTP_200_OK,
    summary="Generuj XML KSeF FA(2) dla faktur z importu",
)
def generate(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Generuje dokumenty XML zgodne ze schematem KSeF FA(2) dla wszystkich faktur
    z danego importu (status DRAFT lub VALIDATED).

    - Wynik zapisywany jest w Invoice.xml_content.
    - Status faktur zmienia się na EXPORTED.
    - Status importu zmienia się na EXPORTED.
    """
    import_record = get_import_by_id(db, import_id)
    if not import_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")

    count = generate_xml_for_import(db, import_id)

    return GenerateResponse(
        import_id=import_id,
        generated=count,
        message=f"Wygenerowano {count} dokumentów XML KSeF.",
    )


# ---------------------------------------------------------------------------
# Pobranie XML – archiwum ZIP (wszystkie faktury importu)
# ---------------------------------------------------------------------------


@router.get(
    "/download/{import_id}",
    summary="Pobierz wszystkie XML-e importu jako archiwum ZIP",
    responses={200: {"content": {"application/zip": {}}}},
)
def download_zip(
    import_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    import_record = get_import_by_id(db, import_id)
    if not import_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")

    invoices = (
        db.query(Invoice)
        .filter(Invoice.import_id == import_id, Invoice.xml_content.isnot(None))
        .all()
    )

    if not invoices:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brak wygenerowanych XML-i dla tego importu. Uruchom najpierw /ksef/generate/{import_id}.",
        )

    zip_bytes = build_xml_zip(invoices)
    filename = f"ksef_{import_record.client_id}_{import_record.import_month}.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Pobranie XML – pojedyncza faktura
# ---------------------------------------------------------------------------


@router.get(
    "/download/invoice/{invoice_id}",
    summary="Pobierz XML jednej faktury",
    responses={200: {"content": {"application/xml": {}}}},
)
def download_single(
    invoice_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    invoice = (
        db.query(Invoice)
        .options(joinedload(Invoice.items))
        .filter(Invoice.id == invoice_id)
        .first()
    )
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Faktura nie istnieje")

    # Jeśli XML nie wygenerowany – wygeneruj na żądanie
    if not invoice.xml_content:
        try:
            xml_str = build_invoice_xml(invoice)
            invoice.xml_content = xml_str
            from datetime import datetime, timezone
            invoice.xml_generated_at = datetime.now(timezone.utc)
            db.commit()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Błąd generacji XML: {exc}",
            )
    else:
        xml_str = invoice.xml_content

    import re
    safe_name = re.sub(r'[\\/:*?"<>|]', "_", invoice.invoice_number)
    return Response(
        content=xml_str.encode("utf-8"),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.xml"'},
    )


# ---------------------------------------------------------------------------
# Podgląd faktur docelowych dla importu
# ---------------------------------------------------------------------------


@router.get(
    "/invoices/{import_id}",
    response_model=PaginatedResponse[InvoiceResponse],
    summary="Lista faktur docelowych dla importu",
)
def list_invoices_for_import(
    import_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    if not get_import_by_id(db, import_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import nie istnieje")

    skip = (page - 1) * page_size
    query = (
        db.query(Invoice)
        .options(joinedload(Invoice.items))
        .filter(Invoice.import_id == import_id)
    )
    total = query.count()
    items = query.offset(skip).limit(page_size).all()
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)
