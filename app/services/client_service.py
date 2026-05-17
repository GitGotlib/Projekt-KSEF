from typing import List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.client import Client
from app.schemas.client import ClientCreate, ClientUpdate


def get_clients(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> Tuple[int, List[Client]]:
    query = db.query(Client)

    if is_active is not None:
        query = query.filter(Client.is_active == is_active)

    if search:
        pattern = f"%{search}%"
        query = query.filter(
            or_(
                Client.company_name.ilike(pattern),
                Client.nip.ilike(pattern),
                Client.company_id.ilike(pattern),
            )
        )

    total = query.count()
    items = query.order_by(Client.company_name).offset(skip).limit(limit).all()
    return total, items


def get_client_by_id(db: Session, client_id: int) -> Optional[Client]:
    return db.query(Client).filter(Client.id == client_id).first()


def get_client_by_company_id(db: Session, company_id: str) -> Optional[Client]:
    return db.query(Client).filter(Client.company_id == company_id).first()


def get_client_by_nip(db: Session, nip: str) -> Optional[Client]:
    return db.query(Client).filter(Client.nip == nip).first()


def create_client(db: Session, client_data: ClientCreate) -> Client:
    db_client = Client(**client_data.model_dump())
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    return db_client


def update_client(
    db: Session, client_id: int, client_data: ClientUpdate
) -> Optional[Client]:
    client = get_client_by_id(db, client_id)
    if not client:
        return None
    for field, value in client_data.model_dump(exclude_unset=True).items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    return client


def deactivate_client(db: Session, client_id: int) -> Optional[Client]:
    client = get_client_by_id(db, client_id)
    if not client:
        return None
    client.is_active = False
    db.commit()
    db.refresh(client)
    return client
