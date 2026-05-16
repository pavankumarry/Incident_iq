from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from database import get_db
from models import Order, OrderItem, Product

router = APIRouter(prefix="/orders", tags=["orders"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int


class OrderCreate(BaseModel):
    user_id: int
    items: List[OrderItemCreate]


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    price: float

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    user_id: int
    total_amount: float
    status: str
    created_at: datetime
    items: List[OrderItemResponse]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Routes — CLEAN version: proper transaction + error handling
# ---------------------------------------------------------------------------
@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(order_data: OrderCreate, db: DBSession = Depends(get_db)):
    """
    Create a new order.
    - Validates all products exist and have sufficient stock.
    - Wraps everything in a single transaction; rolls back on any error.
    """
    if not order_data.items:
        raise HTTPException(status_code=400, detail="Order must contain at least one item")

    total = 0.0
    resolved_items: list[tuple[Product, int]] = []

    for item in order_data.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(
                status_code=404,
                detail=f"Product {item.product_id} not found",
            )
        if product.stock < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for product '{product.name}' "
                       f"(requested {item.quantity}, available {product.stock})",
            )
        total += product.price * item.quantity
        resolved_items.append((product, item.quantity))

    try:
        order = Order(
            user_id=order_data.user_id,
            total_amount=round(total, 2),
            status="pending",
        )
        db.add(order)
        db.flush()  # get order.id without committing

        for product, qty in resolved_items:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=qty,
                    price=product.price,
                )
            )
            product.stock -= qty  # decrement stock

        db.commit()
        db.refresh(order)
        return order
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create order")


@router.get("", response_model=List[OrderResponse])
def list_orders(user_id: Optional[int] = None, db: DBSession = Depends(get_db)):
    """Return all orders, optionally filtered by user_id."""
    query = db.query(Order)
    if user_id is not None:
        query = query.filter(Order.user_id == user_id)
    return query.order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: DBSession = Depends(get_db)):
    """Return a single order by ID."""
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
