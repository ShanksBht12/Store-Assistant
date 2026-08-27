"""
Seed the database with realistic sample data so the Phase 1 demo
scenarios ("How much are A shoes?" / "A shoes were cheaper before" /
"show me black shoes") work out of the box.

Run with: python -m app.database.seed
"""
from datetime import datetime
from urllib.parse import quote

from app.database.database import Base, SessionLocal, engine
from app.database.models import Product, ProductPriceHistory


def _placeholder_image(label: str, hex_color: str) -> str:
    """Simple hosted placeholder swatch — swap for real product photos later."""
    return f"https://placehold.co/300x300/{hex_color}/ffffff?text={quote(label)}"

SHOE_BLACK_IMAGE = (
    "https://images.unsplash.com/photo-1600269452121-4f2416e55c28"
    "?auto=format&fit=crop&w=800&q=85"
)
SHOE_PINK_IMAGE = (
    "https://images.unsplash.com/photo-1525966222134-fcfa99b8ae77"
    "?auto=format&fit=crop&w=800&q=85"
)
SHOE_WHITE_IMAGE = (
    "https://images.unsplash.com/photo-1542291026-7eec264c27ff"
    "?auto=format&fit=crop&w=800&q=85"
)
BACKPACK_BLUE_IMAGE = (
    "https://images.unsplash.com/photo-1581605405669-fcdf81165afa"
    "?auto=format&fit=max&w=800&q=85"
)
BACKPACK_GREY_IMAGE = (
    "https://images.unsplash.com/photo-1622560480605-d83c853bc5c3"
    "?auto=format&fit=max&w=800&q=85"
)


SAMPLE_PRODUCTS = [
    {
        "sku": "SHOE-A-BLACK",
        "name": "AeroRun X1",
        "description": "Everyday running shoes, breathable mesh upper.",
        "category": "Footwear",
        "color": "Black",
        "image_url": SHOE_BLACK_IMAGE,
        "current_price": 8500,
        "currency": "NPR",
        "stock_quantity": 42,
        "history": [
            ("2026-05-01", 6500),
            ("2026-06-01", 6999),
            ("2026-07-15", 7500),
            ("2026-08-01", 8500),
        ],
    },
    {
        "sku": "SHOE-A-PINK",
        "name": "AeroRun X1",
        "description": "Everyday running shoes, breathable mesh upper.",
        "category": "Footwear",
        "color": "Pink",
        "image_url": SHOE_PINK_IMAGE,
        "current_price": 8700,
        "currency": "NPR",
        "stock_quantity": 27,
        "history": [
            ("2026-05-01", 6700),
            ("2026-06-01", 7199),
            ("2026-07-15", 7700),
            ("2026-08-01", 8700),
        ],
    },
    {
        "sku": "SHOE-A-WHITE",
        "name": "AeroRun X1",
        "description": "Everyday running shoes, breathable mesh upper.",
        "category": "Footwear",
        "color": "White",
        "image_url": SHOE_WHITE_IMAGE,
        "current_price": 8500,
        "currency": "NPR",
        "stock_quantity": 35,
        "history": [
            ("2026-05-01", 6500),
            ("2026-06-01", 6999),
            ("2026-07-15", 7500),
            ("2026-08-01", 8500),
        ],
    },
    {
        "sku": "BAG-B-GREY",
        "name": "TrailPack B1",
        "description": "20L water-resistant daily backpack.",
        "category": "Bags",
        "color": "Grey",
        "image_url": BACKPACK_GREY_IMAGE,
        "current_price": 3200,
        "currency": "NPR",
        "stock_quantity": 15,
        "history": [
            ("2026-04-01", 2800),
            ("2026-07-01", 3200),
        ],
    },
    {
        "sku": "BAG-B-BLUE",
        "name": "TrailPack B1",
        "description": "20L water-resistant daily backpack.",
        "category": "Bags",
        "color": "Blue",
        "image_url": BACKPACK_BLUE_IMAGE,
        "current_price": 3300,
        "currency": "NPR",
        "stock_quantity": 9,
        "history": [
            ("2026-04-01", 2900),
            ("2026-07-01", 3300),
        ],
    },
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Product).count() > 0:
            image_urls = {
                entry["sku"]: entry["image_url"] for entry in SAMPLE_PRODUCTS
            }
            product_names = {
                entry["sku"]: entry["name"] for entry in SAMPLE_PRODUCTS
            }
            for product in db.query(Product).all():
                if product.sku in image_urls:
                    product.image_url = image_urls[product.sku]
                    product.name = product_names[product.sku]
            db.commit()
            print("Products already exist — updated product names and images.")
            return

        for entry in SAMPLE_PRODUCTS:
            history = entry.pop("history")
            product = Product(**entry)
            db.add(product)
            db.flush()  # get product.id before creating history rows

            for i, (date_str, price) in enumerate(history):
                valid_from = datetime.strptime(date_str, "%Y-%m-%d")
                valid_to = (
                    datetime.strptime(history[i + 1][0], "%Y-%m-%d")
                    if i + 1 < len(history)
                    else None
                )
                db.add(
                    ProductPriceHistory(
                        product_id=product.id,
                        price=price,
                        currency=product.currency,
                        valid_from=valid_from,
                        valid_to=valid_to,
                    )
                )

        db.commit()
        print(f"Seeded {len(SAMPLE_PRODUCTS)} products with price history.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
