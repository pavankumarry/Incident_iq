"""
introduce_bug.py — Introduce realistic bugs into the ShopApp backend.

Bugs introduced:
  1. routes/sessions.py  — raw connection leak (never released on exception)
  2. routes/products.py  — SQL injection via f-string query
  3. routes/orders.py    — missing timeout + connection never released on error

Run from the project root:
    python scripts/introduce_bug.py
"""

import os
import shutil

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")


def backup(rel_path: str):
    src = os.path.join(BACKEND, rel_path)
    dst = src + ".bak"
    shutil.copy2(src, dst)
    print(f"  [backup] {rel_path} -> {rel_path}.bak")


def write(rel_path: str, content: str):
    dst = os.path.join(BACKEND, rel_path)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"  [write]  {rel_path} (buggy version)")


# ---------------------------------------------------------------------------
# Bug 1 — Connection leak in sessions.py
# ---------------------------------------------------------------------------
BUGGY_SESSIONS = '''\
"""
routes/sessions.py — BUGGY VERSION (connection leak)
Introduced by introduce_bug.py for IncidentIQ demo.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from database import engine

router = APIRouter(prefix="/sessions", tags=["sessions"])


class SessionResponse(BaseModel):
    id: int
    user_id: int
    token: str
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


# BUG: raw connection acquired but never released when an exception is raised.
# Under load this exhausts the connection pool.
@router.get("/{user_id}")
def get_session(user_id: int):
    conn = engine.connect()          # raw connection — NOT managed by DI
    try:
        result = conn.execute(
            text(f"SELECT * FROM sessions WHERE user_id = {user_id}")
        )
        row = result.fetchone()
        if row is None:
            return None
        return dict(row._mapping)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        # BUG: conn.close() is never called — connection leaks on every error!


@router.post("", status_code=201)
def create_session(user_id: int, token: str, expires_at: datetime):
    conn = engine.connect()          # same leak pattern
    try:
        conn.execute(
            text(
                f"INSERT INTO sessions (user_id, token, expires_at) "
                f"VALUES ({user_id}, \'{token}\', \'{expires_at}\')"
            )
        )
        conn.commit()
        return {"status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        # BUG: conn.close() never called
'''

# ---------------------------------------------------------------------------
# Bug 2 — SQL injection in products.py
# ---------------------------------------------------------------------------
BUGGY_PRODUCTS = '''\
"""
routes/products.py — BUGGY VERSION (SQL injection)
Introduced by introduce_bug.py for IncidentIQ demo.
"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession
from sqlalchemy import text
from pydantic import BaseModel
from datetime import datetime

from database import get_db
from models import Product

router = APIRouter(prefix="/products", tags=["products"])


class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: float
    stock: int
    category: str
    created_at: datetime

    model_config = {"from_attributes": True"}


# BUG: category is interpolated directly into the SQL string — SQL injection!
@router.get("")
def list_products(
    category: Optional[str] = None,
    q: Optional[str] = None,
    db: DBSession = Depends(get_db),
):
    if q:
        # BUG: f-string SQL injection — attacker can escape the LIKE clause
        sql = f"SELECT * FROM products WHERE name LIKE \'%{q}%\'"
        result = db.execute(text(sql))
        return [dict(r._mapping) for r in result.fetchall()]

    if category:
        # BUG: same injection via category param
        sql = f"SELECT * FROM products WHERE category = \'{category}\'"
        result = db.execute(text(sql))
        return [dict(r._mapping) for r in result.fetchall()]

    return db.query(Product).all()


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: DBSession = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
'''

# ---------------------------------------------------------------------------
# Bug 3 — Missing timeout + connection leak in orders.py
# ---------------------------------------------------------------------------
BUGGY_ORDERS = '''\
"""
routes/orders.py — BUGGY VERSION (missing timeout, connection leak)
Introduced by introduce_bug.py for IncidentIQ demo.
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from database import engine, get_db
from models import Order, OrderItem, Product

router = APIRouter(prefix="/orders", tags=["orders"])


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


# BUG: acquires a raw connection with no timeout — can block forever under load.
# Also: connection is never released if an exception occurs mid-transaction.
@router.post("", status_code=status.HTTP_201_CREATED)
def create_order(order_data: OrderCreate, db: DBSession = Depends(get_db)):
    conn = engine.connect()          # BUG: no timeout, not managed by context manager

    total = 0.0
    resolved = []

    for item in order_data.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            # BUG: conn never closed before raising
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        if product.stock < item.quantity:
            # BUG: conn never closed before raising
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {product.name}")
        total += product.price * item.quantity
        resolved.append((product, item.quantity))

    try:
        conn.execute(
            text(
                f"INSERT INTO orders (user_id, total_amount, status, created_at) "
                f"VALUES ({order_data.user_id}, {round(total,2)}, \'pending\', datetime(\'now\'))"
            )
        )
        conn.commit()
        # BUG: order items never inserted via this path
        return {"status": "created", "total": total}
    except Exception as e:
        # BUG: conn.close() not called — leaks on every error
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[OrderResponse])
def list_orders(user_id: Optional[int] = None, db: DBSession = Depends(get_db)):
    query = db.query(Order)
    if user_id is not None:
        query = query.filter(Order.user_id == user_id)
    return query.order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: DBSession = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order
'''


def main():
    print("=" * 60)
    print("introduce_bug.py — ShopApp IncidentIQ Demo")
    print("=" * 60)

    print("\n[1] Backing up original files...")
    backup("routes/sessions.py")
    backup("routes/products.py")
    backup("routes/orders.py")

    print("\n[2] Writing buggy versions...")
    write("routes/sessions.py", BUGGY_SESSIONS)
    write("routes/products.py", BUGGY_PRODUCTS)
    write("routes/orders.py", BUGGY_ORDERS)

    print("\n[3] Bugs introduced successfully!")
    print("""
Bugs summary:
  • sessions.py  — raw DB connection never released on exception (pool exhaustion)
  • products.py  — SQL injection via f-string interpolation in search/filter
  • orders.py    — no connection timeout + connection leak on error path

Next steps:
  Option A — Send directly to IncidentIQ:
    python scripts/notify_incidentiq.py

  Option B — Push to GitHub (if webhook configured):
    git add backend/routes && git commit -m "Add session caching and search" && git push
""")


if __name__ == "__main__":
    main()
