from typing import List, Optional, Tuple

from sqlalchemy import extract, or_
from sqlalchemy.orm import Session, joinedload

from app.models.invoice import Invoice, InvoiceItem
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate

# Statusy, które pozwalają na edycję/usunięcie
_EDITABLE_STATUSES = {"DRAFT", "ERROR"}


def get_invoices(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    invoice_type: Optional[str] = None,
    month: Optional[str] = None,
    search: Optional[str] = None,
) -> Tuple[int, List[Invoice]]:
    query = db.query(Invoice)

    if client_id is not None:
        query = query.filter(Invoice.client_id == client_id)
    if status:
        query = query.filter(Invoice.status == status)
    if invoice_type:
        query = query.filter(Invoice.invoice_type == invoice_type)
    if month:
        year_str, mon_str = month.split("-")
        query = query.filter(
            extract("year", Invoice.invoice_date) == int(year_str),
            extract("month", Invoice.invoice_date) == int(mon_str),
        )
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Invoice.invoice_number.ilike(pattern),
                Invoice.buyer_name.ilike(pattern),
                Invoice.buyer_nip.ilike(pattern),
            )
        )

    total = query.count()
    items = (
        query.order_by(Invoice.invoice_date.desc(), Invoice.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, items


def get_invoice_by_id(db: Session, invoice_id: int) -> Optional[Invoice]:
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.items))
        .filter(Invoice.id == invoice_id)
        .first()
    )


def create_invoice(
    db: Session,
    invoice_data: InvoiceCreate,
    user_id: int,
) -> Invoice:
    items_data = invoice_data.items
    invoice_dict = invoice_data.model_dump(exclude={"items"})
    invoice_dict["user_id"] = user_id

    db_invoice = Invoice(**invoice_dict)
    db.add(db_invoice)
    db.flush()  # uzyskaj id przed commitem

    for item_data in items_data:
        db.add(InvoiceItem(invoice_id=db_invoice.id, **item_data.model_dump()))

    db.commit()
    db.refresh(db_invoice)
    return db_invoice


def update_invoice(
    db: Session, invoice_id: int, invoice_data: InvoiceUpdate
) -> Optional[Invoice]:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return None
    if invoice.status not in _EDITABLE_STATUSES:
        raise ValueError(
            f"Nie można edytować faktury o statusie '{invoice.status}'. "
            "Dozwolone: DRAFT, ERROR."
        )
    for field, value in invoice_data.model_dump(exclude_unset=True).items():
        setattr(invoice, field, value)
    db.commit()
    db.refresh(invoice)
    return invoice


def delete_invoice(db: Session, invoice_id: int) -> bool:
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not invoice:
        return False
    if invoice.status not in _EDITABLE_STATUSES:
        raise ValueError(
            f"Nie można usunąć faktury o statusie '{invoice.status}'. "
            "Dozwolone: DRAFT, ERROR."
        )
    db.delete(invoice)
    db.commit()
    return True
