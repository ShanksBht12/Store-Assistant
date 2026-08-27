"""Import a store_assistant.db export into the application's catalog tables."""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

from app.database.database import Base, SessionLocal, engine
from app.database.models import Product, ProductPriceHistory

SHOE_IMAGE = (
    "https://images.unsplash.com/photo-1600269452121-4f2416e55c28"
    "?auto=format&fit=crop&w=800&q=85"
)


def import_dataset(source_path: Path) -> tuple[int, int]:
    """Replace the app catalog with products and history from source_path."""
    with sqlite3.connect(source_path) as source:
        source.row_factory = sqlite3.Row
        products = source.execute(
            """
            SELECT product_id, sku, name, category, description,
                     current_price, currency, stock_quantity, created_at, updated_at
            FROM products
            ORDER BY product_id
            """
        ).fetchall()
        history = source.execute(
            """
            SELECT product_id, price, currency, effective_from, effective_to
            FROM product_price_history
            ORDER BY product_id, effective_from
            """
        ).fetchall()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(ProductPriceHistory).delete()
        db.query(Product).delete()

        product_ids = {}
        for row in products:
            product = Product(
                sku=row["sku"],
                name=row["name"],
                description=row["description"],
                category=row["category"],
                image_url=SHOE_IMAGE,
                current_price=row["current_price"],
                currency=row["currency"],
                stock_quantity=row["stock_quantity"],
                created_at=datetime.fromisoformat(row["created_at"])
                if row["created_at"]
                else None,
                updated_at=datetime.fromisoformat(row["updated_at"])
                if row["updated_at"]
                else None,
            )
            db.add(product)
            db.flush()
            product_ids[row["product_id"]] = product.id

        for row in history:
            db.add(
                ProductPriceHistory(
                    product_id=product_ids[row["product_id"]],
                    price=row["price"],
                    currency=row["currency"],
                    valid_from=datetime.fromisoformat(row["effective_from"]),
                    valid_to=(
                        datetime.fromisoformat(row["effective_to"])
                        if row["effective_to"]
                        else None
                    ),
                )
            )

        db.commit()
        return len(products), len(history)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=Path("store_assistant.db"),
        help="Path to the store_assistant.db export",
    )
    args = parser.parse_args()
    products, history = import_dataset(args.source)
    print(f"Imported {products} products and {history} price-history rows.")


if __name__ == "__main__":
    main()