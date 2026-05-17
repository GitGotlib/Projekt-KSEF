from fastapi import APIRouter

from app.api.routers import auth, clients, imports, invoices, ksef, validation

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(clients.router)
api_router.include_router(invoices.router)
api_router.include_router(imports.router)
api_router.include_router(validation.router)
api_router.include_router(ksef.router)
 