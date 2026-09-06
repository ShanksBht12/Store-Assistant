"""
Phase 2 tool registry -- OOP version.

Previously each tool was a bare function, referenced by name in a
TOOL_FUNCTIONS dict, and the agent loop invoked it by looking up a string
and calling it with **kwargs: `TOOL_FUNCTIONS[name](db, **arguments)`. That
works, but it's dispatch-by-string with the schema (TOOL_SPECS) living
completely separately -- nothing actually ties a function to its schema
except both happening to use the same name string by convention. Nothing
stops them drifting out of sync (e.g. renaming a function's parameter
without updating its schema, or vice versa).

Here, each tool is a class: its name, its JSON schema, and its behavior are
one object. The agent loop calls tool.run(db, **arguments) through the
shared Tool interface -- polymorphism, not string-keyed function lookup.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database.models import Order, OrderItem, OrderStatus, Product, ProductPriceHistory

PAYMENT_METHODS = {"esewa", "khalti", "cash on delivery", "cod"}

# Nepali mobile numbers: start with 98, 97, or 96, exactly 10 digits total.
_NEPALI_PHONE_RE = re.compile(r"^9[678]\d{8}$")


class Tool(ABC):
    """Every tool the agent can call implements this. `name`, `spec`, and
    `run()` living on the same object means there's exactly one place that
    defines each tool, not a schema dict in one place and a function
    somewhere else that both have to be kept in sync by hand."""

    name: str

    @property
    @abstractmethod
    def spec(self) -> dict[str, Any]:
        """OpenAI/Groq-format function-calling schema for this tool."""
        raise NotImplementedError

    @abstractmethod
    def run(self, db: Session, **arguments: Any) -> dict[str, Any]:
        """Execute the tool and return a JSON-serializable result."""
        raise NotImplementedError


class SearchProductsTool(Tool):
    name = "search_products"

    # ── Category synonyms ────────────────────────────────────────────────────
    # Maps lower-cased user terms → actual DB category values (partial match).
    # The resolver below checks these before falling back to token search.
    _CATEGORY_SYNONYMS: dict[str, str] = {
        # Kids
        "kids": "Kids",
        "kid": "Kids",
        "children": "Kids",
        "child": "Kids",
        "boys": "Kids Boys",
        "boy": "Kids Boys",
        "girls": "Kids Girls",
        "girl": "Kids Girls",
        "kids boys": "Kids Boys",
        "kids girls": "Kids Girls",
        "kids clothing": "Kids",
        "childrens clothing": "Kids",
        "children clothing": "Kids",
        "kids clothes": "Kids",
        "boys clothes": "Kids Boys",
        "girls clothes": "Kids Girls",
        "kids wear": "Kids",
        "kidswear": "Kids",
        # Men's clothing
        "mens": "Men's",
        "men": "Men's",
        "men's": "Men's",
        "male": "Men's",
        "menswear": "Men's",
        "mens clothing": "Men's",
        "mens clothes": "Men's",
        "men clothing": "Men's",
        "men's clothing": "Men's",
        "mens tops": "Men's Tops",
        "mens shirts": "Men's Tops",
        "mens tshirts": "Men's Tops",
        "mens t-shirts": "Men's Tops",
        "mens bottoms": "Men's Bottoms",
        "mens jeans": "Men's Bottoms",
        "mens pants": "Men's Bottoms",
        "mens trousers": "Men's Bottoms",
        "mens outerwear": "Men's Outerwear",
        "mens jackets": "Men's Outerwear",
        "mens coats": "Men's Outerwear",
        # Women's clothing
        "womens": "Women's",
        "women": "Women's",
        "women's": "Women's",
        "female": "Women's",
        "ladies": "Women's",
        "womenswear": "Women's",
        "womens clothing": "Women's",
        "womens clothes": "Women's",
        "women clothing": "Women's",
        "women's clothing": "Women's",
        "womens tops": "Women's Tops",
        "womens blouses": "Women's Tops",
        "womens shirts": "Women's Tops",
        "womens bottoms": "Women's Bottoms",
        "womens jeans": "Women's Bottoms",
        "womens skirts": "Women's Bottoms",
        "womens dresses": "Women's Dresses",
        "dress": "Women's Dresses",
        "dresses": "Women's Dresses",
        "womens outerwear": "Women's Outerwear",
        "womens jackets": "Women's Outerwear",
        # Generic clothing
        "clothing": "Men's Tops",   # default clothing → men's section; broader results via ILIKE
        "clothes": "Men's Tops",
        "apparel": "Men's Tops",
        "fashion": "Men's Tops",
        "tops": "Tops",
        "shirts": "Tops",
        "tshirts": "Tops",
        "t-shirts": "Tops",
        "bottoms": "Bottoms",
        "jeans": "Bottoms",
        "pants": "Bottoms",
        "trousers": "Bottoms",
        "shorts": "Bottoms",
        "outerwear": "Outerwear",
        "jackets": "Outerwear",
        "coats": "Outerwear",
        "hoodies": "Outerwear",
        # Accessories
        "sunglasses": "Sunglasses",
        "sunnies": "Sunglasses",
        "shades": "Sunglasses",
        "glasses": "Sunglasses",
        "eyewear": "Sunglasses",
        "watches": "Watches",
        "watch": "Watches",
        "timepiece": "Watches",
        "bags": "Bags",
        "bag": "Bags",
        "backpacks": "Bags & Backpacks",
        "backpack": "Bags & Backpacks",
        "handbags": "Bags",
        "tote": "Bags",
        "purse": "Bags",
        "hats": "Hats",
        "hat": "Hats",
        "caps": "Hats",
        "cap": "Hats",
        "beanie": "Hats",
        "headwear": "Hats",
        "socks": "Socks",
        "underwear": "Socks & Underwear",
        "innerwear": "Socks & Underwear",
        "sportswear": "Sportswear",
        "activewear": "Sportswear",
        "gym wear": "Sportswear",
        "gymwear": "Sportswear",
        "sports": "Sportswear",
        "athletic": "Sportswear",
        # Footwear
        "shoes": "Running",       # partial — will match Running, Casual etc via ILIKE
        "shoe": "Running",
        "sneakers": "Casual",
        "trainers": "Running",
        "boots": "Hiking",
        "sandals": "Sandal",
        "footwear": "Running",
        "running shoes": "Running",
        "casual shoes": "Casual",
        "hiking boots": "Hiking",
        "hiking shoes": "Hiking",
        "basketball shoes": "Basketball",
        "trail shoes": "Trail",
        "formal shoes": "Formal",
    }

    # ── Narrowing terms ──────────────────────────────────────────────────────
    # Some synonym keys above map to a CATEGORY that is broader than the term
    # itself (e.g. "jeans" -> "Bottoms", which also holds shorts/trousers/
    # joggers). Without this, the specific word the customer used ("jeans")
    # gets discarded entirely once it's been turned into a category, so a
    # query like "blue jeans" would return ANY blue item in Bottoms, not just
    # jeans. This maps the synonym key to a word that must also appear in the
    # product's name/description, so the specific item type survives.
    # Deliberately curated/explicit rather than derived automatically — an
    # automatic version would also try to filter on generic words like
    # "clothing" or "footwear", which don't appear in real product names and
    # would wrongly return zero results.
    _NARROWING_TERMS: dict[str, str] = {
        "jeans": "jean", "mens jeans": "jean", "womens jeans": "jean",
        "pants": "pant", "mens pants": "pant",
        "trousers": "trouser", "mens trousers": "trouser",
        "shorts": "short",
        "hoodies": "hoodie",
        "jackets": "jacket", "mens jackets": "jacket", "womens jackets": "jacket",
        "coats": "coat", "mens coats": "coat",
        "shirts": "shirt", "mens shirts": "shirt", "womens shirts": "shirt",
        "tshirts": "shirt", "t-shirts": "shirt",
        "mens tshirts": "shirt", "mens t-shirts": "shirt",
        "sneakers": "sneaker",
        "trainers": "trainer",
        "boots": "boot", "hiking boots": "boot",
        "handbags": "handbag", "tote": "tote", "purse": "purse",
        "skirts": "skirt", "womens skirts": "skirt",
        "blouses": "blouse", "womens blouses": "blouse",
    }

    @classmethod
    def _resolve_category(cls, query: str) -> tuple[str | None, str | None, str | None]:
        """Try to resolve a query to a category alias.

        Returns (resolved_category, remaining_query, matched_key).
        remaining_query is None if the whole query was consumed by the
        category resolution, or the brand/model part if the query was e.g.
        'Nike running shoes'. matched_key is the synonym key that was
        actually matched (used by the caller to look up _NARROWING_TERMS).
        """
        q_lower = query.strip().lower()

        # Full-phrase match first (longest wins)
        sorted_keys = sorted(cls._CATEGORY_SYNONYMS.keys(), key=len, reverse=True)
        for key in sorted_keys:
            if q_lower == key:
                return cls._CATEGORY_SYNONYMS[key], None, key

        # Phrase appears at start — extract remaining part
        for key in sorted_keys:
            if q_lower.startswith(key + " "):
                remaining = query[len(key):].strip()
                # If the remaining part is itself a category synonym,
                # pick the more specific one (the prefix synonym in this case)
                remaining_lower = remaining.lower()
                if remaining_lower in cls._CATEGORY_SYNONYMS:
                    # e.g. "mens clothing" → prefix "mens" maps to "Men's",
                    # remaining "clothing" is generic → use Men's (prefix)
                    return cls._CATEGORY_SYNONYMS[key], None, key
                return cls._CATEGORY_SYNONYMS[key], remaining or None, key

        # Phrase appears at end — extract remaining part as brand/model query
        for key in sorted_keys:
            if q_lower.endswith(" " + key):
                remaining = query[: -(len(key) + 1)].strip()
                remaining_lower = remaining.lower()
                # If remaining is itself a category synonym, combine them
                # e.g. "girls clothing" → suffix "clothing" is generic,
                # remaining "girls" → maps to "Kids Girls"
                if remaining_lower in cls._CATEGORY_SYNONYMS:
                    return cls._CATEGORY_SYNONYMS[remaining_lower], None, remaining_lower
                return cls._CATEGORY_SYNONYMS[key], remaining or None, key

        return None, query, None

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Search the store's product catalog. Use this for ANY "
                    "product-related question: specific lookups, browsing, "
                    "comparisons, or listing everything available.\n"
                    "- To list ALL products: omit 'query', set max_results=50.\n"
                    "- For a category browse (e.g. 'kids clothing', 'backpacks', "
                    "'women dresses'): pass the category phrase as 'query' — the "
                    "tool resolves it automatically. Do NOT guess a category string.\n"
                    "- For a specific product: pass brand+model as 'query' and "
                    "optionally 'color'.\n"
                    "- For multiple specific products: call ONCE PER product.\n"
                    "Never invent product details — always call this tool first."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Free-text search: brand name, model name, category phrase "
                                "(e.g. 'Nike', 'Dior Hexagonal Frame', 'kids clothing', "
                                "'backpacks', 'mens tops'). Omit to return all products."
                            ),
                        },
                        "color": {"type": "string", "description": "Filter by color, e.g. 'black'."},
                        "category": {
                            "type": "string",
                            "description": (
                                "Exact category filter — only use this when you already know "
                                "the exact DB category name (e.g. 'Kids Boys', 'Sunglasses', "
                                "'Watches'). For natural-language category queries, use 'query' instead."
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Max products to return. Default 20. Use 50 for full catalog listing or comparisons.",
                        },
                    },
                },
            },
        }

    def run(
        self,
        db: Session,
        query: str | None = None,
        color: str | None = None,
        category: str | None = None,
        max_results: int = 20,
    ) -> dict[str, Any]:
        from sqlalchemy import case

        # ── Step 0: exact/near-exact name short-circuit ───────────────────────
        # Prevents category-synonym stripping below (e.g. "...Running Shoes"
        # getting its "Shoes" suffix stripped into category="Running") from
        # hijacking a search for a specific, already-known product name — the
        # case where the customer types back the exact name the bot just gave
        # them. Without this, an exact name could still get filtered into the
        # wrong category (or an over-narrowed remaining_query) and return the
        # wrong product or nothing at all.
        if query:
            exact = db.query(Product).filter(Product.name.ilike(query.strip())).first()
            if exact and (not color or (exact.color or "").lower() == color.lower()):
                return {
                    "count": 1,
                    "products": [{
                        "id": exact.id,
                        "sku": exact.sku,
                        "name": exact.name,
                        "brand": exact.brand,
                        "color": exact.color,
                        "category": exact.category,
                        "description": exact.description,
                        "image_url": exact.image_url,
                        "price": exact.current_price,
                        "currency": exact.currency,
                        "stock_quantity": exact.stock_quantity,
                    }],
                }

        # ── Step 1: resolve category synonyms from query ─────────────────────
        resolved_category: str | None = category
        remaining_query: str | None = query
        narrow_word: str | None = None

        if query:
            cat_from_query, leftover, matched_key = self._resolve_category(query)
            if cat_from_query:
                if not category:
                    resolved_category = cat_from_query
                remaining_query = leftover  # None if whole query was category phrase
                if matched_key:
                    narrow_word = self._NARROWING_TERMS.get(matched_key.lower())

        # ── Step 1b: extract color baked into query string ───────────────────
        # LLMs often call search_products(query="Nike Air Max Red") instead of
        # using the separate color param. Detect trailing color words and split.
        resolved_color: str | None = color

        # Also strip noise words that sometimes remain after category resolution
        # e.g. "womens section" -> remaining="section" -> useless token
        _noise_words = {
            "section", "area", "stuff", "things", "items", "products",
            "category", "collection", "range", "options", "available",
        }
        if remaining_query and remaining_query.strip().lower() in _noise_words:
            remaining_query = None
        if not resolved_color and remaining_query:
            _known_colors = {
                "black", "white", "gray", "grey", "navy", "blue", "red", "green",
                "orange", "brown", "pink", "purple", "yellow", "beige", "olive",
                "teal", "maroon", "cream", "charcoal", "gold", "silver",
                "rose gold", "tan", "caramel", "tortoise", "clear", "khaki",
                "multicolor", "coral", "mint", "lavender", "mustard",
            }
            words = remaining_query.split()
            # Check last 2 words then last 1 word for a known color
            for n in (2, 1):
                if len(words) >= n:
                    candidate = " ".join(words[-n:]).lower()
                    if candidate in _known_colors:
                        resolved_color = " ".join(words[-n:]).title()
                        remaining_query = " ".join(words[:-n]).strip() or None
                        break

        # ── Step 2: build base DB query ──────────────────────────────────────
        q = db.query(Product)

        if remaining_query:
            stop_words = {"and", "or", "&", "the", "a", "an", "for", "in", "with", "of"}
            tokens = [
                t.strip(".,;:")
                for t in remaining_query.split()
                if t.strip(".,;:").lower() not in stop_words and t.strip(".,;:")
            ]
            if tokens:
                token_filters = []
                for token in tokens:
                    like = f"%{token}%"
                    token_filters.append(Product.name.ilike(like))
                    token_filters.append(Product.brand.ilike(like))
                    # Only match category and description if token is ≥4 chars
                    # to avoid noise from short tokens like "co", "go" etc.
                    if len(token) >= 4:
                        token_filters.append(Product.category.ilike(like))
                        token_filters.append(Product.description.ilike(like))
                q = q.filter(or_(*token_filters))

                # Rank exact full-name / brand matches first
                full_like = f"%{remaining_query}%"
                q = q.order_by(
                    case(
                        (Product.name.ilike(full_like), 0),
                        (Product.brand.ilike(full_like), 1),
                        else_=2,
                    ),
                    Product.id,
                )
            else:
                q = q.order_by(Product.id)
        else:
            q = q.order_by(Product.id)

        # ── Step 3: apply filters ─────────────────────────────────────────────
        if resolved_color:
            q = q.filter(Product.color.ilike(f"%{resolved_color}%"))
        if resolved_category:
            # Use exact match when the resolved category is a full known category name,
            # otherwise fall back to substring ILIKE (for partial like "Kids", "Bags").
            # This avoids "Men's Tops" matching inside "Women's Tops" via ILIKE.
            exact_categories = {
                "Men's Tops", "Men's Bottoms", "Men's Outerwear",
                "Women's Tops", "Women's Bottoms", "Women's Dresses", "Women's Outerwear",
                "Kids Boys", "Kids Girls",
                "Bags & Backpacks", "Hats & Caps", "Socks & Underwear",
                "Sunglasses", "Watches", "Sportswear",
                "Running", "Casual", "Training", "Basketball", "Trail",
                "Hiking", "Formal", "Sandal",
            }
            if resolved_category in exact_categories:
                q = q.filter(Product.category == resolved_category)
            else:
                q = q.filter(Product.category.ilike(f"%{resolved_category}%"))
        if narrow_word:
            # e.g. "blue jeans" resolved to category=Bottoms, color=Blue —
            # without this, "jeans" itself would be lost and any blue item
            # in Bottoms (shorts, trousers, etc.) could match.
            narrow_like = f"%{narrow_word}%"
            q = q.filter(or_(Product.name.ilike(narrow_like), Product.description.ilike(narrow_like)))

        products = q.limit(max_results).all()
        return {
            "count": len(products),
            "products": [
                {
                    "id": p.id,
                    "sku": p.sku,
                    "name": p.name,
                    "brand": p.brand,
                    "color": p.color,
                    "category": p.category,
                    "description": p.description,
                    "image_url": p.image_url,
                    "price": p.current_price,
                    "currency": p.currency,
                    "stock_quantity": p.stock_quantity,
                }
                for p in products
            ],
        }


class GetPriceHistoryTool(Tool):
    name = "get_price_history"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Get the recorded price history for one specific product, by its id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer", "description": "The product's database id."},
                    },
                    "required": ["product_id"],
                },
            },
        }

    def run(self, db: Session, product_id: int) -> dict[str, Any]:
        product = db.get(Product, product_id)
        if product is None:
            return {"error": f"No product found with id {product_id}"}

        history = (
            db.query(ProductPriceHistory)
            .filter(ProductPriceHistory.product_id == product_id)
            .order_by(ProductPriceHistory.valid_from)
            .all()
        )
        return {
            "product_id": product_id,
            "product_name": product.name,
            "current_price": product.current_price,
            "currency": product.currency,
            "history": [
                {
                    "date": h.valid_from.date().isoformat(),
                    "price": h.price,
                    "currency": h.currency,
                }
                for h in history
            ],
        }


class CheckStockTool(Tool):
    name = "check_stock"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "Check live stock quantity for one specific product, by its id.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer", "description": "The product's database id."},
                    },
                    "required": ["product_id"],
                },
            },
        }

    def run(self, db: Session, product_id: int) -> dict[str, Any]:
        product = db.get(Product, product_id)
        if product is None:
            return {"error": f"No product found with id {product_id}"}
        return {
            "product_id": product_id,
            "product_name": product.name,
            "stock_quantity": product.stock_quantity,
            "in_stock": product.stock_quantity > 0,
        }


class GetProductTool(Tool):
    """Fetch a single product's full details (including image URL) by its id.
    Use this when you want to confirm the exact product before placing an order
    or when you need the image URL for a specific product."""

    name = "get_product"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Fetch the full details of a single product by its database id, "
                    "including its image URL, description, price, stock, and category. "
                    "Use this after search_products to confirm the exact product the "
                    "customer wants before proceeding to check_stock or create_order."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "integer",
                            "description": "The product's database id (from search_products results).",
                        },
                    },
                    "required": ["product_id"],
                },
            },
        }

    def run(self, db: Session, product_id: int) -> dict[str, Any]:
        product = db.get(Product, product_id)
        if product is None:
            return {"error": f"No product found with id {product_id}"}
        return {
            "product_id": product.id,
            "sku": product.sku,
            "name": product.name,
            "brand": product.brand,
            "description": product.description,
            "category": product.category,
            "color": product.color,
            "image_url": product.image_url,
            "current_price": product.current_price,
            "currency": product.currency,
            "stock_quantity": product.stock_quantity,
            "in_stock": product.stock_quantity > 0,
        }


class CreateOrderTool(Tool):
    name = "create_order"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Create ONE order for the customer containing all their products as line items. "
                    "Call this ONCE with all products in the 'items' list — do NOT call it multiple "
                    "times. Only call after: stock confirmed for every item, customer name, phone, "
                    "address, and payment method all collected and validated."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "description": "List of products the customer wants to buy.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "product_id": {"type": "integer", "description": "Product database id."},
                                    "quantity":   {"type": "integer", "description": "Number of units. Default 1."},
                                    "size":       {"type": "string",  "description": "e.g. 'EU 42'"},
                                    "color":      {"type": "string"},
                                },
                                "required": ["product_id"],
                            },
                        },
                        "customer_name":  {"type": "string"},
                        "phone":          {"type": "string"},
                        "address":        {"type": "string"},
                        "payment_method": {
                            "type": "string",
                            "description": "One of: eSewa, Khalti, Cash on Delivery",
                        },
                    },
                    "required": ["items", "customer_name", "phone", "address", "payment_method"],
                },
            },
        }

    def run(
        self,
        db: Session,
        items: list[dict],
        customer_name: str,
        phone: str,
        address: str,
        payment_method: str,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        # ── Basic validation ──────────────────────────────────────────────────
        if not items:
            return {"error": "items list cannot be empty."}

        if payment_method.strip().lower() not in PAYMENT_METHODS:
            return {"error": f"Unsupported payment method '{payment_method}'. Supported: eSewa, Khalti, Cash on Delivery."}

        phone_digits = re.sub(r"[\s\-]", "", phone)
        if not _NEPALI_PHONE_RE.match(phone_digits):
            return {"error": f"'{phone}' is not a valid Nepali mobile number. Must be 10 digits starting with 98, 97, or 96."}

        # ── Validate every item before creating anything ──────────────────────
        resolved: list[dict] = []
        for item in items:
            pid = item.get("product_id")
            qty = max(1, int(item.get("quantity") or 1))
            size  = item.get("size")
            color = item.get("color")

            product = db.get(Product, pid)
            if product is None:
                return {"error": f"No product found with id {pid}."}
            if product.stock_quantity < qty:
                return {"error": f"Only {product.stock_quantity} left in stock for '{product.name}', cannot order {qty}."}

            resolved.append({
                "product": product,
                "qty": qty,
                "size": size,
                "color": color or product.color,
                "unit_price": product.current_price,
                "line_total": product.current_price * qty,
                "currency": product.currency,
            })

        grand_total = sum(r["line_total"] for r in resolved)
        currency = resolved[0]["currency"]

        # ── Create one Order row ──────────────────────────────────────────────
        order = Order(
            conversation_id=conversation_id,
            grand_total=grand_total,
            currency=currency,
            customer_name=customer_name,
            phone=phone_digits,
            address=address,
            payment_method=payment_method,
            status=OrderStatus.PENDING_PAYMENT,
        )
        db.add(order)
        db.flush()  # get order.id before inserting items

        # ── Create OrderItem rows + decrement stock ───────────────────────────
        item_summaries: list[dict] = []
        for r in resolved:
            product = r["product"]
            oi = OrderItem(
                order_id=order.id,
                product_id=product.id,
                product_name_snapshot=product.name,
                color=r["color"],
                size=r["size"],
                quantity=r["qty"],
                unit_price=r["unit_price"],
                line_total=r["line_total"],
                currency=r["currency"],
            )
            db.add(oi)
            product.stock_quantity -= r["qty"]
            db.add(product)
            item_summaries.append({
                "product_name": product.name,
                "color": r["color"],
                "size": r["size"],
                "quantity": r["qty"],
                "unit_price": r["unit_price"],
                "line_total": r["line_total"],
            })

        db.commit()
        db.refresh(order)

        return {
            "order_id": order.id,
            "items": item_summaries,
            "item_count": len(item_summaries),
            "grand_total": grand_total,
            "currency": currency,
            "payment_method": payment_method,
            "status": order.status.value,
        }


class GetOrderStatusTool(Tool):
    name = "get_order_status"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Look up one or more orders by order ID or by the customer's "
                    "phone number. Use this whenever a customer asks about their "
                    "order status, delivery, or payment confirmation. "
                    "Provide either order_id OR phone — not both."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "integer",
                            "description": "The numeric order ID from the order confirmation.",
                        },
                        "phone": {
                            "type": "string",
                            "description": "Customer's 10-digit Nepali mobile number to look up all their orders.",
                        },
                    },
                },
            },
        }

    def run(
        self,
        db: Session,
        order_id: int | None = None,
        phone: str | None = None,
    ) -> dict[str, Any]:
        if not order_id and not phone:
            return {"error": "Please provide either an order ID or a phone number to look up an order."}

        if order_id:
            order = db.get(Order, order_id)
            if order is None:
                return {"error": f"No order found with id {order_id}."}
            return {"orders": [_order_to_dict(order)]}

        # Validate phone before querying — reject non-numeric or too-short values
        phone_digits = re.sub(r"[\s\-]", "", phone)
        if not phone_digits.isdigit() or len(phone_digits) < 7:
            return {
                "error": (
                    f"'{phone}' doesn't look like a valid phone number or order ID. "
                    "Please ask the customer to provide their 10-digit Nepali mobile number "
                    "or their numeric order ID."
                )
            }

        # Lookup by phone — normalise the same way CreateOrderTool does
        phone_digits = re.sub(r"[\s\-]", "", phone)
        orders = (
            db.query(Order)
            .filter(Order.phone == phone_digits)
            .order_by(Order.created_at.desc())
            .limit(10)
            .all()
        )
        if not orders:
            return {"error": f"No orders found for phone number {phone}."}
        return {"orders": [_order_to_dict(o) for o in orders]}


def _order_to_dict(order: Order) -> dict[str, Any]:
    return {
        "order_id": order.id,
        "grand_total": order.grand_total,
        "currency": order.currency,
        "payment_method": order.payment_method,
        "status": order.status.value,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "address": order.address,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "items": [
            {
                "product_name": it.product_name_snapshot,
                "color": it.color,
                "size": it.size,
                "quantity": it.quantity,
                "unit_price": it.unit_price,
                "line_total": it.line_total,
            }
            for it in (order.items or [])
        ],
    }


class ValidatePhoneTool(Tool):
    name = "validate_phone"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Validate a Nepali mobile phone number IMMEDIATELY after "
                    "the customer provides it — before asking for address or "
                    "payment method. Returns valid=true if it is a 10-digit "
                    "number starting with 98, 97, or 96. If invalid, tell the "
                    "customer right away and ask them to re-enter it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {
                            "type": "string",
                            "description": "The phone number the customer provided.",
                        }
                    },
                    "required": ["phone"],
                },
            },
        }

    def run(self, db: Session, phone: str) -> dict[str, Any]:
        digits = re.sub(r"[\s\-]", "", phone)
        if _NEPALI_PHONE_RE.match(digits):
            return {"valid": True, "phone": digits}
        return {
            "valid": False,
            "phone": phone,
            "reason": (
                f"'{phone}' is not a valid Nepali mobile number. "
                "Must be 10 digits starting with 98, 97, or 96."
            ),
        }


class ValidateAddressTool(Tool):
    name = "validate_address"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Validate a delivery address IMMEDIATELY after the customer "
                    "provides it — before asking for payment method. "
                    "A valid address must be within Nepal and contain enough "
                    "detail to deliver to (area/tole/street + city at minimum). "
                    "Single words, food names, gibberish, or vague responses "
                    "are invalid. If invalid, ask the customer to re-enter a "
                    "complete delivery address."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "string",
                            "description": "The delivery address the customer provided.",
                        }
                    },
                    "required": ["address"],
                },
            },
        }

    def run(self, db: Session, address: str) -> dict[str, Any]:
        address = address.strip()

        # Must have at least 8 characters
        if len(address) < 8:
            return {
                "valid": False,
                "reason": f"'{address}' is too short to be a valid delivery address.",
            }

        # Must contain at least 2 words
        words = address.split()
        if len(words) < 2:
            return {
                "valid": False,
                "reason": (
                    f"'{address}' doesn't look like a complete address. "
                    "Please provide area/tole/street and city."
                ),
            }

        # Reject obvious non-addresses: all digits, single repeated char, etc.
        if re.fullmatch(r"[\d\s\-]+", address):
            return {
                "valid": False,
                "reason": f"'{address}' is not a valid address. Please provide a locality and city name.",
            }

        # Block known food/nonsense words as standalone addresses
        _NONSENSE = {
            "chana", "muni", "dal", "bhat", "roti", "khana", "pani",
            "test", "abc", "xyz", "hello", "hi", "idk", "none", "na",
            "nothing", "no", "yes", "ok", "okay",
        }
        lower_words = {w.lower().strip(".,") for w in words}
        if lower_words.issubset(_NONSENSE):
            return {
                "valid": False,
                "reason": (
                    f"'{address}' is not a valid delivery address. "
                    "Please provide a real location — for example: Thamel, Kathmandu or Lazimpat, Ward 2, Kathmandu."
                ),
            }

        return {"valid": True, "address": address}


class UpdateOrderPaymentTool(Tool):
    name = "update_order_payment"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Update the payment method on an existing pending order in "
                    "this conversation. Use this when the customer wants to "
                    "change their payment method AFTER an order has already been "
                    "placed — instead of creating a duplicate order. "
                    "Only works if the order status is still pending_payment."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {
                            "type": "integer",
                            "description": "The order ID to update.",
                        },
                        "payment_method": {
                            "type": "string",
                            "description": "New payment method: eSewa, Khalti, or Cash on Delivery.",
                        },
                    },
                    "required": ["order_id", "payment_method"],
                },
            },
        }

    def run(self, db: Session, order_id: int, payment_method: str) -> dict[str, Any]:
        order = db.get(Order, order_id)
        if order is None:
            return {"error": f"No order found with id {order_id}."}

        if order.status != OrderStatus.PENDING_PAYMENT:
            return {
                "error": (
                    f"Order {order_id} cannot be updated — "
                    f"status is '{order.status.value}', not pending_payment."
                )
            }

        normalised = payment_method.strip().lower()
        if normalised not in PAYMENT_METHODS:
            return {
                "error": (
                    f"Unsupported payment method '{payment_method}'. "
                    "Supported: eSewa, Khalti, Cash on Delivery."
                )
            }

        order.payment_method = payment_method
        db.add(order)
        db.commit()
        db.refresh(order)

        return {
            "order_id": order.id,
            "product_name": None,
            "payment_method": order.payment_method,
            "total_price": order.grand_total,
            "currency": order.currency,
            "status": order.status.value,
        }


class GetBestSellersTool(Tool):
    name = "get_best_sellers"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Get the most purchased products ranked by total units sold. "
                    "Use this whenever a customer asks about best sellers, most "
                    "popular shoes, most purchased, or top products. "
                    "Never guess — always call this tool."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Number of top products to return. Default 5.",
                        }
                    },
                },
            },
        }

    def run(self, db: Session, limit: int = 5) -> dict[str, Any]:
        from sqlalchemy import func
        # Join OrderItem → Order to filter cancelled orders
        rows = (
            db.query(
                OrderItem.product_name_snapshot,
                OrderItem.color,
                func.sum(OrderItem.quantity).label("total_sold"),
            )
            .join(Order, OrderItem.order_id == Order.id)
            .filter(Order.status != OrderStatus.CANCELLED)
            .group_by(OrderItem.product_name_snapshot, OrderItem.color)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
            .all()
        )

        if not rows:
            return {"message": "No sales data available yet.", "best_sellers": []}

        return {
            "best_sellers": [
                {
                    "rank": i + 1,
                    "product_name": row.product_name_snapshot,
                    "color": row.color,
                    "total_sold": int(row.total_sold),
                }
                for i, row in enumerate(rows)
            ]
        }


# --- Registry ----------------------------------------------------------
# One dict, built from the tool objects themselves -- TOOL_SPECS is derived
# from TOOLS, not maintained as a second, independent list that could
# silently drift out of sync with the actual tool classes.

TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        SearchProductsTool(),
        GetProductTool(),
        GetPriceHistoryTool(),
        CheckStockTool(),
        CreateOrderTool(),
        GetOrderStatusTool(),
        ValidatePhoneTool(),
        ValidateAddressTool(),
        UpdateOrderPaymentTool(),
        GetBestSellersTool(),
    )
}

TOOL_SPECS: list[dict[str, Any]] = [tool.spec for tool in TOOLS.values()]