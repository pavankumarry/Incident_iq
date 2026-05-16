import os
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import engine, Base
from telemetry import TelemetryMiddleware, read_recent_metrics
from routes import products, orders, users, sessions

# ---------------------------------------------------------------------------
# Create all tables on startup
# ---------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="ShopApp API",
    description="Sample e-commerce backend for IncidentIQ demo",
    version="1.0.0",
)

# CORS — allow the React dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenTelemetry request tracing middleware
app.add_middleware(TelemetryMiddleware)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(users.router)
app.include_router(sessions.router)


# ---------------------------------------------------------------------------
# Core endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["health"])
def health_check():
    return {"status": "healthy", "service": "shopapp", "version": "1.0.0"}


@app.get("/metrics", tags=["telemetry"])
def get_metrics():
    """Return the last 100 telemetry metric entries (read by IncidentIQ)."""
    return read_recent_metrics(100)
