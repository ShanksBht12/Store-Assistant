"""
Seed the database with the initial product catalog and price history.

Run once after a fresh clone to populate the products table:
    python -m app.database.seed

Safe to re-run — skips products that already exist (matched by SKU).
"""
from datetime import datetime

from app.database.database import Base, SessionLocal, engine
from app.database.models import Product, ProductPriceHistory


PRODUCTS = [
    dict(sku="SH001", name="Adidas Ultraboost", brand="Adidas", description="Premium running shoes with boost technology", category="Running", color="Black", image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85", current_price=12500.0, currency="NPR", stock_quantity=25),
    dict(sku="SH002", name="Adidas Stan Smith",  brand="Adidas", description="Classic casual sneaker",                    category="Casual",  color="White", image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85", current_price=8500.0,  currency="NPR", stock_quantity=30),
    dict(sku="SH003", name="Adidas Runner",       brand="Adidas", description="Lightweight running shoes",                category="Running", color="Red",   image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=85", current_price=9500.0,  currency="NPR", stock_quantity=18),
    dict(sku="SH004", name="Adidas Cloudfoam",    brand="Adidas", description="Comfortable everyday sneaker",             category="Casual",  color="Gray",  image_url="https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=800&q=85", current_price=7500.0,  currency="NPR", stock_quantity=22),
    dict(sku="SH005", name="Nike Air Max",         brand="Nike",   description="Air Max cushioning for comfort",           category="Running", color="Black", image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85", current_price=13000.0, currency="NPR", stock_quantity=19),
    dict(sku="SH006", name="Nike Revolution",      brand="Nike",   description="Affordable running shoes",                 category="Running", color="Blue",  image_url="https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=800&q=85", current_price=8000.0,  currency="NPR", stock_quantity=24),
    dict(sku="SH007", name="Nike Court Legacy",    brand="Nike",   description="Classic court-style sneaker",              category="Casual",  color="White", image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85", current_price=9000.0,  currency="NPR", stock_quantity=25),
    dict(sku="SH008", name="Nike Cortez",          brand="Nike",   description="Vintage-style casual shoe",                category="Casual",  color="Red",   image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=85", current_price=9500.0,  currency="NPR", stock_quantity=14),
    dict(sku="SH009", name="Puma RS-X",            brand="Puma",   description="Retro-futuristic design",                  category="Casual",  color="Black", image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85", current_price=8500.0,  currency="NPR", stock_quantity=18),
    dict(sku="SH010", name="Puma Suede",           brand="Puma",   description="Classic suede sneaker",                    category="Casual",  color="Navy",  image_url="https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=800&q=85", current_price=7500.0,  currency="NPR", stock_quantity=26),
    dict(sku="SH011", name="Puma Velocity",        brand="Puma",   description="Lightweight running shoe",                 category="Running", color="Green", image_url="https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=800&q=85", current_price=9000.0,  currency="NPR", stock_quantity=21),
    dict(sku="SH012", name="Puma Storm",           brand="Puma",   description="Dynamic running performance",              category="Running", color="Orange",image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=85&sat=35", current_price=10000.0, currency="NPR", stock_quantity=17),
    dict(sku="SH013", name="New Balance 990",      brand="New Balance", description="Premium running heritage",            category="Running", color="Gray",  image_url="https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=800&q=85", current_price=14000.0, currency="NPR", stock_quantity=12),
    dict(sku="SH014", name="New Balance 574",      brand="New Balance", description="Classic retro style",                 category="Casual",  color="Black", image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85", current_price=9500.0,  currency="NPR", stock_quantity=24),
    dict(sku="SH015", name="New Balance Fresh Foam",brand="New Balance",description="Cushioned running comfort",           category="Running", color="White", image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85", current_price=10500.0, currency="NPR", stock_quantity=19),
    dict(sku="SH016", name="Skechers GoWalk",      brand="Skechers",description="Lightweight casual shoe",                category="Casual",  color="Black", image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85", current_price=6500.0,  currency="NPR", stock_quantity=32),
    dict(sku="SH017", name="Skechers Memory Foam", brand="Skechers",description="Memory foam comfort",                    category="Casual",  color="White", image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85", current_price=7000.0,  currency="NPR", stock_quantity=28),
    dict(sku="SH018", name="Skechers Arch Fit",    brand="Skechers",description="Arch support running shoe",              category="Running", color="Brown", image_url="https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=800&q=85", current_price=8500.0,  currency="NPR", stock_quantity=20),
]

# Price history keyed by SKU: list of (price, valid_from, valid_to)
PRICE_HISTORY: dict[str, list[tuple]] = {
    "SH001": [(6500.0, "2026-05-01", "2026-06-01"), (6999.0, "2026-06-01", "2026-07-15"), (7500.0, "2026-07-15", "2026-08-01"), (8500.0, "2026-08-01", None)],
    "SH002": [(5500.0, "2026-05-01", "2026-07-20"), (6000.0, "2026-07-20", "2026-08-01"), (6500.0, "2026-08-01", None)],
    "SH003": [(8500.0, "2026-05-01", "2026-07-01"), (9000.0, "2026-07-01", "2026-08-10"), (9200.0, "2026-08-10", None)],
    "SH004": [(7200.0, "2026-04-01", "2026-07-01"), (7500.0, "2026-07-01", "2026-08-05"), (7800.0, "2026-08-05", None)],
    "SH005": [(6500.0, "2026-05-01", "2026-07-15"), (6900.0, "2026-07-15", "2026-08-12"), (7200.0, "2026-08-12", None)],
    "SH006": [(9500.0, "2026-06-01", "2026-08-15"), (10500.0, "2026-08-15", None)],
    "SH007": [(5200.0, "2026-05-01", "2026-07-15"), (5800.0, "2026-07-15", None)],
    "SH008": [(8900.0, "2026-06-01", "2026-08-20"), (9900.0, "2026-08-20", None)],
}


def _dt(s: str | None):
    return datetime.fromisoformat(s) if s else None


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing_skus = {r[0] for r in db.query(Product.sku).all()}
        added = 0

        for p in PRODUCTS:
            if p["sku"] in existing_skus:
                continue
            product = Product(**p)
            db.add(product)
            db.flush()  # get product.id

            for price, valid_from, valid_to in PRICE_HISTORY.get(p["sku"], []):
                db.add(ProductPriceHistory(
                    product_id=product.id,
                    price=price,
                    currency="NPR",
                    valid_from=_dt(valid_from),
                    valid_to=_dt(valid_to),
                ))
            added += 1

        db.commit()
        total = db.query(Product).count()
        print(f"Seeded {added} new products. Total in catalog: {total}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
