"""
Seed the database with the initial product catalog and price history.

Run once after a fresh clone to populate the products table:
    python -m app.database.seed

Safe to re-run — skips products that already exist (matched by SKU).
Also backfills price history for existing products that have none.
"""
from datetime import datetime

from app.database.database import Base, SessionLocal, engine
from app.database.models import Product, ProductPriceHistory


PRODUCTS = [
    dict(sku="SH001", name="Adidas Ultraboost",      brand="Adidas",       description="Premium running shoes with boost technology", category="Running", color="Black",  image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85",        current_price=12500.0, currency="NPR", stock_quantity=25),
    dict(sku="SH002", name="Adidas Stan Smith",       brand="Adidas",       description="Classic casual sneaker",                      category="Casual",  color="White",  image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85",        current_price=8500.0,  currency="NPR", stock_quantity=30),
    dict(sku="SH003", name="Adidas Runner",           brand="Adidas",       description="Lightweight running shoes",                   category="Running", color="Red",    image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=85",        current_price=9500.0,  currency="NPR", stock_quantity=18),
    dict(sku="SH004", name="Adidas Cloudfoam",        brand="Adidas",       description="Comfortable everyday sneaker",                category="Casual",  color="Gray",   image_url="https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=800&q=85",        current_price=7500.0,  currency="NPR", stock_quantity=22),
    dict(sku="SH005", name="Nike Air Max",            brand="Nike",         description="Air Max cushioning for comfort",              category="Running", color="Black",  image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85",        current_price=13000.0, currency="NPR", stock_quantity=19),
    dict(sku="SH006", name="Nike Revolution",         brand="Nike",         description="Affordable running shoes",                    category="Running", color="Blue",   image_url="https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=800&q=85",        current_price=8000.0,  currency="NPR", stock_quantity=24),
    dict(sku="SH007", name="Nike Court Legacy",       brand="Nike",         description="Classic court-style sneaker",                 category="Casual",  color="White",  image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85",        current_price=9000.0,  currency="NPR", stock_quantity=25),
    dict(sku="SH008", name="Nike Cortez",             brand="Nike",         description="Vintage-style casual shoe",                   category="Casual",  color="Red",    image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=85",        current_price=9500.0,  currency="NPR", stock_quantity=14),
    dict(sku="SH009", name="Puma RS-X",               brand="Puma",         description="Retro-futuristic design",                     category="Casual",  color="Black",  image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85",        current_price=8500.0,  currency="NPR", stock_quantity=18),
    dict(sku="SH010", name="Puma Suede",              brand="Puma",         description="Classic suede sneaker",                       category="Casual",  color="Navy",   image_url="https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=800&q=85",        current_price=7500.0,  currency="NPR", stock_quantity=26),
    dict(sku="SH011", name="Puma Velocity",           brand="Puma",         description="Lightweight running shoe",                    category="Running", color="Green",  image_url="https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=800&q=85",        current_price=9000.0,  currency="NPR", stock_quantity=21),
    dict(sku="SH012", name="Puma Storm",              brand="Puma",         description="Dynamic running performance",                 category="Running", color="Orange", image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=85&sat=35",  current_price=10000.0, currency="NPR", stock_quantity=17),
    dict(sku="SH013", name="New Balance 990",         brand="New Balance",  description="Premium running heritage",                    category="Running", color="Gray",   image_url="https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=800&q=85",        current_price=14000.0, currency="NPR", stock_quantity=12),
    dict(sku="SH014", name="New Balance 574",         brand="New Balance",  description="Classic retro style",                         category="Casual",  color="Black",  image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85",        current_price=9500.0,  currency="NPR", stock_quantity=24),
    dict(sku="SH015", name="New Balance Fresh Foam",  brand="New Balance",  description="Cushioned running comfort",                   category="Running", color="White",  image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85",        current_price=10500.0, currency="NPR", stock_quantity=19),
    dict(sku="SH016", name="Skechers GoWalk",         brand="Skechers",     description="Lightweight casual shoe",                     category="Casual",  color="Black",  image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85",        current_price=6500.0,  currency="NPR", stock_quantity=32),
    dict(sku="SH017", name="Skechers Memory Foam",    brand="Skechers",     description="Memory foam comfort",                         category="Casual",  color="White",  image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85",        current_price=7000.0,  currency="NPR", stock_quantity=28),
    dict(sku="SH018", name="Skechers Arch Fit",       brand="Skechers",     description="Arch support running shoe",                   category="Running", color="Brown",  image_url="https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=800&q=85",        current_price=8500.0,  currency="NPR", stock_quantity=20),

    # ── Nepali brands ──────────────────────────────────────────────────────
    # Dulla — premium handcrafted Nepali designer brand
    dict(sku="NP001", name="Dulla Leather Classic",   brand="Dulla",        description="Handcrafted premium leather sneaker, made in Nepal", category="Casual",  color="Brown",  image_url="https://static-01.daraz.com.np/p/655f1267d1de6650e5b1d56053499b6f.jpg",        current_price=11000.0, currency="NPR", stock_quantity=15),
    dict(sku="NP002", name="Dulla Canvas Runner",     brand="Dulla",        description="Lightweight canvas runner with Nepali craft details", category="Running", color="White",  image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85",        current_price=8500.0,  currency="NPR", stock_quantity=18),
    dict(sku="NP003", name="Dulla Urban Boot",        brand="Dulla",        description="Stylish urban boot, handmade in Kathmandu",           category="Casual",  color="Black",  image_url="https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=800&q=85",        current_price=13500.0, currency="NPR", stock_quantity=10),

    # Goldstar — Nepal's iconic affordable everyday shoe brand
    dict(sku="NP004", name="Goldstar Classic 032",    brand="Goldstar",     description="Nepal's iconic canvas shoe, durable and affordable",  category="Casual",  color="White",  image_url="https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=800&q=85",        current_price=1800.0,  currency="NPR", stock_quantity=60),
    dict(sku="NP005", name="Goldstar Zest Running",   brand="Goldstar",     description="Affordable everyday running shoe with rubber sole",    category="Running", color="Gray",   image_url="https://images.unsplash.com/photo-1495555961986-6d4c1ecb7be3?auto=format&fit=crop&w=800&q=85",        current_price=2800.0,  currency="NPR", stock_quantity=45),
    dict(sku="NP006", name="Goldstar Hi-Top",         brand="Goldstar",     description="High-top canvas sneaker, popular Nepali school shoe",  category="Casual",  color="Black",  image_url="https://images.unsplash.com/photo-1542291026-7eec264c27ff?auto=format&fit=crop&w=800&q=85",        current_price=2200.0,  currency="NPR", stock_quantity=50),

    # Caliber — mid-range quality-focused Nepali brand, founded 2015
    dict(sku="NP007", name="Caliber Urbane",          brand="Caliber",      description="Trendy urban sneaker by Nepali brand Caliber",        category="Casual",  color="White",  image_url="https://images.unsplash.com/photo-1549298916-b41d501d3772?auto=format&fit=crop&w=800&q=85",        current_price=4500.0,  currency="NPR", stock_quantity=25),
    dict(sku="NP008", name="Caliber Sport Pro",       brand="Caliber",      description="Performance sport shoe with modern Nepali design",     category="Running", color="Blue",   image_url="https://images.unsplash.com/photo-1491553895911-0055eca6402d?auto=format&fit=crop&w=800&q=85",        current_price=5500.0,  currency="NPR", stock_quantity=20),
    dict(sku="NP009", name="Caliber Leather Loafer",  brand="Caliber",      description="Casual leather loafer, crafted in Nepal",             category="Casual",  color="Brown",  image_url="https://images.unsplash.com/photo-1460353581641-37baddab0fa2?auto=format&fit=crop&w=800&q=85",        current_price=3800.0,  currency="NPR", stock_quantity=22),
]

# Price history for all 18 SKUs — (price, valid_from, valid_to)
# Prices start lower and rise to current, reflecting real market patterns.
PRICE_HISTORY: dict[str, list[tuple]] = {
    # Adidas Ultraboost — current 12500
    "SH001": [
        (9500.0,  "2026-01-01", "2026-03-01"),
        (10500.0, "2026-03-01", "2026-05-01"),
        (11000.0, "2026-05-01", "2026-07-01"),
        (12000.0, "2026-07-01", "2026-08-01"),
        (12500.0, "2026-08-01", None),
    ],
    # Adidas Stan Smith — current 8500
    "SH002": [
        (6000.0, "2026-01-01", "2026-04-01"),
        (6800.0, "2026-04-01", "2026-06-01"),
        (7500.0, "2026-06-01", "2026-08-01"),
        (8500.0, "2026-08-01", None),
    ],
    # Adidas Runner — current 9500
    "SH003": [
        (7500.0, "2026-01-01", "2026-04-01"),
        (8000.0, "2026-04-01", "2026-06-15"),
        (8800.0, "2026-06-15", "2026-08-01"),
        (9500.0, "2026-08-01", None),
    ],
    # Adidas Cloudfoam — current 7500
    "SH004": [
        (5500.0, "2026-01-01", "2026-04-01"),
        (6200.0, "2026-04-01", "2026-06-01"),
        (7000.0, "2026-06-01", "2026-08-01"),
        (7500.0, "2026-08-01", None),
    ],
    # Nike Air Max — current 13000
    "SH005": [
        (9500.0,  "2026-01-01", "2026-03-15"),
        (10500.0, "2026-03-15", "2026-05-15"),
        (11500.0, "2026-05-15", "2026-07-15"),
        (12500.0, "2026-07-15", "2026-08-15"),
        (13000.0, "2026-08-15", None),
    ],
    # Nike Revolution — current 8000
    "SH006": [
        (5800.0, "2026-01-01", "2026-04-01"),
        (6500.0, "2026-04-01", "2026-06-01"),
        (7200.0, "2026-06-01", "2026-08-01"),
        (8000.0, "2026-08-01", None),
    ],
    # Nike Court Legacy — current 9000
    "SH007": [
        (6500.0, "2026-01-01", "2026-04-01"),
        (7200.0, "2026-04-01", "2026-06-15"),
        (8000.0, "2026-06-15", "2026-08-01"),
        (9000.0, "2026-08-01", None),
    ],
    # Nike Cortez — current 9500
    "SH008": [
        (7000.0, "2026-01-01", "2026-04-01"),
        (7800.0, "2026-04-01", "2026-06-15"),
        (8500.0, "2026-06-15", "2026-08-01"),
        (9500.0, "2026-08-01", None),
    ],
    # Puma RS-X — current 8500
    "SH009": [
        (6000.0, "2026-01-01", "2026-04-01"),
        (6800.0, "2026-04-01", "2026-06-01"),
        (7500.0, "2026-06-01", "2026-08-01"),
        (8500.0, "2026-08-01", None),
    ],
    # Puma Suede — current 7500
    "SH010": [
        (5500.0, "2026-01-01", "2026-04-01"),
        (6200.0, "2026-04-01", "2026-06-15"),
        (7000.0, "2026-06-15", "2026-08-01"),
        (7500.0, "2026-08-01", None),
    ],
    # Puma Velocity — current 9000
    "SH011": [
        (6500.0, "2026-01-01", "2026-04-01"),
        (7200.0, "2026-04-01", "2026-06-01"),
        (8000.0, "2026-06-01", "2026-08-01"),
        (9000.0, "2026-08-01", None),
    ],
    # Puma Storm — current 10000
    "SH012": [
        (7500.0, "2026-01-01", "2026-04-01"),
        (8200.0, "2026-04-01", "2026-06-15"),
        (9000.0, "2026-06-15", "2026-08-01"),
        (10000.0, "2026-08-01", None),
    ],
    # New Balance 990 — current 14000
    "SH013": [
        (10500.0, "2026-01-01", "2026-03-15"),
        (11500.0, "2026-03-15", "2026-05-15"),
        (12500.0, "2026-05-15", "2026-07-15"),
        (13500.0, "2026-07-15", "2026-08-15"),
        (14000.0, "2026-08-15", None),
    ],
    # New Balance 574 — current 9500
    "SH014": [
        (7000.0, "2026-01-01", "2026-04-01"),
        (7800.0, "2026-04-01", "2026-06-01"),
        (8500.0, "2026-06-01", "2026-08-01"),
        (9500.0, "2026-08-01", None),
    ],
    # New Balance Fresh Foam — current 10500
    "SH015": [
        (8000.0, "2026-01-01", "2026-04-01"),
        (8800.0, "2026-04-01", "2026-06-15"),
        (9500.0, "2026-06-15", "2026-08-01"),
        (10500.0, "2026-08-01", None),
    ],
    # Skechers GoWalk — current 6500
    "SH016": [
        (4500.0, "2026-01-01", "2026-04-01"),
        (5200.0, "2026-04-01", "2026-06-01"),
        (6000.0, "2026-06-01", "2026-08-01"),
        (6500.0, "2026-08-01", None),
    ],
    # Skechers Memory Foam — current 7000
    "SH017": [
        (5000.0, "2026-01-01", "2026-04-01"),
        (5800.0, "2026-04-01", "2026-06-15"),
        (6500.0, "2026-06-15", "2026-08-01"),
        (7000.0, "2026-08-01", None),
    ],
    # Skechers Arch Fit — current 8500
    "SH018": [
        (6000.0, "2026-01-01", "2026-04-01"),
        (6800.0, "2026-04-01", "2026-06-15"),
        (7500.0, "2026-06-15", "2026-08-01"),
        (8500.0, "2026-08-01", None),
    ],

    # ── Nepali brands ──────────────────────────────────────────────────────
    # Dulla Leather Classic — current 11000
    "NP001": [
        (7500.0,  "2026-01-01", "2026-03-01"),
        (8500.0,  "2026-03-01", "2026-05-01"),
        (9500.0,  "2026-05-01", "2026-07-01"),
        (10500.0, "2026-07-01", "2026-08-15"),
        (11000.0, "2026-08-15", None),
    ],
    # Dulla Canvas Runner — current 8500
    "NP002": [
        (6000.0, "2026-01-01", "2026-04-01"),
        (7000.0, "2026-04-01", "2026-06-15"),
        (8000.0, "2026-06-15", "2026-08-01"),
        (8500.0, "2026-08-01", None),
    ],
    # Dulla Urban Boot — current 13500
    "NP003": [
        (9500.0,  "2026-01-01", "2026-03-15"),
        (10500.0, "2026-03-15", "2026-05-15"),
        (11500.0, "2026-05-15", "2026-07-15"),
        (13000.0, "2026-07-15", "2026-08-15"),
        (13500.0, "2026-08-15", None),
    ],
    # Goldstar Classic 032 — current 1800
    "NP004": [
        (1200.0, "2026-01-01", "2026-05-01"),
        (1500.0, "2026-05-01", "2026-07-01"),
        (1800.0, "2026-07-01", None),
    ],
    # Goldstar Zest Running — current 2800
    "NP005": [
        (1800.0, "2026-01-01", "2026-04-01"),
        (2200.0, "2026-04-01", "2026-06-01"),
        (2500.0, "2026-06-01", "2026-08-01"),
        (2800.0, "2026-08-01", None),
    ],
    # Goldstar Hi-Top — current 2200
    "NP006": [
        (1500.0, "2026-01-01", "2026-05-01"),
        (1800.0, "2026-05-01", "2026-07-01"),
        (2200.0, "2026-07-01", None),
    ],
    # Caliber Urbane — current 4500
    "NP007": [
        (2800.0, "2026-01-01", "2026-04-01"),
        (3200.0, "2026-04-01", "2026-06-01"),
        (3800.0, "2026-06-01", "2026-08-01"),
        (4500.0, "2026-08-01", None),
    ],
    # Caliber Sport Pro — current 5500
    "NP008": [
        (3500.0, "2026-01-01", "2026-04-01"),
        (4200.0, "2026-04-01", "2026-06-15"),
        (4800.0, "2026-06-15", "2026-08-01"),
        (5500.0, "2026-08-01", None),
    ],
    # Caliber Leather Loafer — current 3800
    "NP009": [
        (2500.0, "2026-01-01", "2026-04-01"),
        (3000.0, "2026-04-01", "2026-06-15"),
        (3500.0, "2026-06-15", "2026-08-01"),
        (3800.0, "2026-08-01", None),
    ],
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
            db.flush()

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


def backfill_price_history():
    """Add price history to existing products that have none.
    Safe to run at any time — skips products that already have history rows."""
    db = SessionLocal()
    try:
        products = {p.sku: p for p in db.query(Product).all()}
        backfilled = 0

        for sku, history_rows in PRICE_HISTORY.items():
            product = products.get(sku)
            if not product:
                continue

            existing_count = (
                db.query(ProductPriceHistory)
                .filter(ProductPriceHistory.product_id == product.id)
                .count()
            )
            if existing_count > 0:
                continue  # already has history

            for price, valid_from, valid_to in history_rows:
                db.add(ProductPriceHistory(
                    product_id=product.id,
                    price=price,
                    currency="NPR",
                    valid_from=_dt(valid_from),
                    valid_to=_dt(valid_to),
                ))
            backfilled += 1

        db.commit()
        print(f"Backfilled price history for {backfilled} products.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
    backfill_price_history()
