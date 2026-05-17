from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: Optional[int]
    client_id: Optional[int]
    import_id: Optional[int]
    operation: str
    entity_type: Optional[str]
    entity_id: Optional[int]
    details: Optional[str]
    ip_address: Optional[str]
    status: str
    created_at: datetime
