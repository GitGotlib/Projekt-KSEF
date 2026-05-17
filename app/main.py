from fastapi import FastAPI

import app.models  # noqa: F401 – ensures all models are registered with SQLAlchemy
from app.api import api_router

app = FastAPI(
    title="KSeF Invoice Processing System",
    description="Backend system for importing, validating, and generating KSeF-compliant invoices.",
    version="0.1.0",
)

app.include_router(api_router)


@app.get("/")
def root():
    return {"message": "KSeF Invoice Processing System API"}


@app.get("/health")
def health():
    return {"status": "ok"}


