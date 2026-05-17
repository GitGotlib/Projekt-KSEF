from fastapi import APIRouter

from app.api.routers import auth, clients, invoices

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(clients.router)
api_router.include_router(invoices.router)
 