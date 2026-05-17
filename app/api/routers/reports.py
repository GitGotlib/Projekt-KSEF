"""
Raport miesięczny importów i faktur dla danego klienta i miesiąca.

GET /reports/monthly?client_id=1&import_month=2024-01
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.import_ import Import
from app.models.invoice import Invoice
from app.models.user import User
from app.models.validation_error import ValidationError

router = APIRouter(prefix="/reports", tags=["Reports"])


# ---------------------------------------------------------------------------
# Schematy odpowiedzi
# ---------------------------------------------------------------------------


class ImportSummary(BaseModel):
    import_id: int
    filename: str
    status: str
    row_count: int
    error_count: int


class InvoiceTypeSummary(BaseModel):
    invoice_type: str
    count: int
    total_net: float
    total_vat: float
    total_gross: float


class MonthlyReport(BaseModel):
    client_id: int
    import_month: str
    total_imports: int
    imports: List[ImportSummary]
    total_invoices: int
    exported_invoices: int
    draft_invoices: int
    error_invoices: int
    total_net_amount: float
    total_vat_amount: float
    total_gross_amount: float
    total_validation_errors: int
    unresolved_validation_errors: int
    by_invoice_type: List[InvoiceTypeSummary]


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/monthly",
    response_model=MonthlyReport,
    summary="Raport miesięczny dla klienta i miesiąca",
)
def monthly_report(
    client_id: int = Query(..., description="ID klienta"),
    import_month: str = Query(..., description="Miesiąc (YYYY-MM)"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Podsumowanie dla wybranego klienta i miesiąca rozliczeniowego:
    - Lista importów z ich statusami
    - Sumy kwot faktur docelowych
    - Liczba faktur wg statusu
    - Podział kwot wg typów faktur
    - Statystyki błędów walidacji
    """
    # ---- Importy ----
    imports: List[Import] = (
        db.query(Import)
        .filter(Import.client_id == client_id, Import.import_month == import_month)
        .order_by(Import.imported_at)
        .all()
    )

    if not imports:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brak importów dla klienta {client_id} w miesiącu {import_month}",
        )

    import_ids = [i.id for i in imports]

    # ---- Faktury docelowe ----
    invoices: List[Invoice] = (
        db.query(Invoice)
        .filter(Invoice.import_id.in_(import_ids))
        .all()
    )

    total_net = float(sum(i.net_amount or 0 for i in invoices))
    total_vat = float(sum(i.vat_amount or 0 for i in invoices))
    total_gross = float(sum(i.gross_amount or 0 for i in invoices))

    status_counts = {"DRAFT": 0, "VALIDATED": 0, "EXPORTED": 0, "ERROR": 0}
    for inv in invoices:
        status_counts[inv.status] = status_counts.get(inv.status, 0) + 1

    # ---- Podział wg typów ----
    type_map: dict[str, dict] = {}
    for inv in invoices:
        t = inv.invoice_type
        if t not in type_map:
            type_map[t] = {"count": 0, "net": 0.0, "vat": 0.0, "gross": 0.0}
        type_map[t]["count"] += 1
        type_map[t]["net"] += float(inv.net_amount or 0)
        type_map[t]["vat"] += float(inv.vat_amount or 0)
        type_map[t]["gross"] += float(inv.gross_amount or 0)

    by_type = [
        InvoiceTypeSummary(
            invoice_type=t,
            count=v["count"],
            total_net=round(v["net"], 2),
            total_vat=round(v["vat"], 2),
            total_gross=round(v["gross"], 2),
        )
        for t, v in sorted(type_map.items())
    ]

    # ---- Błędy walidacji ----
    total_val_errors = (
        db.query(func.count(ValidationError.id))
        .filter(ValidationError.import_id.in_(import_ids))
        .scalar()
        or 0
    )
    unresolved_val_errors = (
        db.query(func.count(ValidationError.id))
        .filter(
            ValidationError.import_id.in_(import_ids),
            ValidationError.is_resolved == False,  # noqa: E712
        )
        .scalar()
        or 0
    )

    return MonthlyReport(
        client_id=client_id,
        import_month=import_month,
        total_imports=len(imports),
        imports=[
            ImportSummary(
                import_id=i.id,
                filename=i.filename,
                status=i.status,
                row_count=i.row_count,
                error_count=i.error_count,
            )
            for i in imports
        ],
        total_invoices=len(invoices),
        exported_invoices=status_counts.get("EXPORTED", 0),
        draft_invoices=status_counts.get("DRAFT", 0),
        error_invoices=status_counts.get("ERROR", 0),
        total_net_amount=round(total_net, 2),
        total_vat_amount=round(total_vat, 2),
        total_gross_amount=round(total_gross, 2),
        total_validation_errors=total_val_errors,
        unresolved_validation_errors=unresolved_val_errors,
        by_invoice_type=by_type,
    )
