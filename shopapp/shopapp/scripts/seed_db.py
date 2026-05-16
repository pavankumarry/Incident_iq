"""
seed_db.py — Populate the ShopApp SQLite database with 10 sample products.

Run from the project root:
    python scripts/seed_db.py
"""

import sys
import os

# Allow imports from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from database import SessionLocal, engine, Base
from models import Product

PRODUCTS = [
    # Electronics
    {
        "name": "Laptop Pro 15",
        "description": "High-performance laptop with 16GB RAM, 512GB SSD, and a 15-inch 4K display.",
        "price": 999.00,
        "stock": 25,
        "category": "Electronics",
    },
    {
        "name": "Smartphone X12",
        "description": "Latest flagship phone with 5G, 128GB storage, and triple-lens camera.",
        "price": 599.00,
        "stock": 50,
        "category": "Electronics",
    },
    {
        "name": "Wireless Headphones",
        "description": "Over-ear noise-cancelling headphones with 30-hour battery life.",
        "price": 149.00,
        "stock": 75,
        "category": "Electronics",
    },
    # Clothing
    {
        "name": "Classic Cotton T-Shirt",
        "description": "100% organic cotton t-shirt, available in multiple colours.",
        "price": 29.00,
        "stock": 200,
        "category": "Clothing",
    },
    {
        "name": "Slim-Fit Jeans",
        "description": "Comfortable stretch denim jeans with a modern slim fit.",
        "price": 79.00,
        "stock": 120,
        "category": "Clothing",
    },
    {
        "name": "Winter Jacket",
        "description": "Waterproof insulated jacket, perfect for cold weather.",
        "price": 149.00,
        "stock": 60,
        "category": "Clothing",
    },
    # Books
    {
        "name": "Python Programming Mastery",
        "description": "Comprehensive guide to Python 3, from basics to advanced patterns.",
        "price": 49.00,
        "stock": 150,
        "category": "Books",
    },
    {
        "name": "React & TypeScript in Practice",
        "description": "Build modern web apps with React 18 and TypeScript.",
        "price": 39.00,
        "stock": 130,
        "category": "Books",
    },
    {
        "name": "AWS Solutions Architect Guide",
        "description": "Prepare for the AWS SAA-C03 exam with real-world examples.",
        "price": 59.00,
        "stock": 90,
        "category": "Books",
    },
    # Home
    {
        "name": "Espresso Coffee Maker",
        "description": "15-bar pressure espresso machine with built-in milk frother.",
        "price": 89.00,
        "stock": 40,
        "category": "Home",
    },
]


def seed():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        existing = db.query(Product).count()
        if existing > 0:
            print(f"Database already has {existing} products — skipping seed.")
            return

        for data in PRODUCTS:
            db.add(Product(**data))
        db.commit()
        print(f"Seeded {len(PRODUCTS)} products successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
