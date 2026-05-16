from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Product

router = APIRouter(prefix="/products", tags=["products"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    stock: int
    category: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes — CLEAN version: parameterized queries, no SQL injection
# ---------------------------------------------------------------------------
@router.get("", response_model=List[ProductResponse])
def list_products(
    category: Optional[str] = None,
    db: DBSession = Depends(get_db),
):
    """Return all products, optionally filtered by category."""
    query = db.query(Product)
    if category:
        # Parameterized — safe from SQL injection
        query = query.filter(Product.category == category)
    return query.all()


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: DBSession = Depends(get_db)):
    """Return a single product by ID."""
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
