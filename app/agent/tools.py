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

from app.database.models import Order, OrderStatus, Product, ProductPriceHistory

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

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Search the store's product catalog. Use this for ANY "
                    "product-related question: specific lookups, browsing, "
                    "comparisons ('cheapest', 'most expensive'), or listing "
                    "everything available. "
                    "To list ALL products, omit 'query' and set max_results=50. "
                    "To find the cheapest/most expensive, omit 'query', set "
                    "max_results=50, then reason over the returned list. "
                    "Never invent product details — always call this tool first."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Free-text keyword matching name, brand, or category "
                                "(e.g. 'Nike', 'running shoes'). Omit to return all products."
                            ),
                        },
                        "color": {"type": "string", "description": "Filter by color, e.g. 'black'."},
                        "category": {
                            "type": "string",
                            "description": "Filter by category, e.g. 'Shoes', 'Sunglasses'.",
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
        q = db.query(Product)
        if query:
            like = f"%{query}%"
            q = q.filter(
                or_(
                    Product.name.ilike(like),
                    Product.brand.ilike(like),
                    Product.category.ilike(like),
                )
            )
        if color:
            q = q.filter(Product.color.ilike(f"%{color}%"))
        if category:
            q = q.filter(Product.category.ilike(f"%{category}%"))

        products = q.order_by(Product.id).limit(max_results).all()
        return {
            "count": len(products),
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "brand": p.brand,
                    "color": p.color,
                    "category": p.category,
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


class CreateOrderTool(Tool):
    name = "create_order"

    @property
    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": (
                    "Create a pending order for the customer. Only call this "
                    "once you have: confirmed the exact product (and its "
                    "stock via check_stock), the customer's size and/or "
                    "color if relevant, and collected their full name, phone "
                    "number, delivery address, and payment method (eSewa, "
                    "Khalti, or Cash on Delivery). If anything required is "
                    "missing, ask the customer for it first instead of "
                    "calling this -- do not guess or fill in placeholder "
                    "values."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "integer", "description": "The product's database id."},
                        "customer_name": {"type": "string"},
                        "phone": {"type": "string"},
                        "address": {"type": "string"},
                        "payment_method": {
                            "type": "string",
                            "description": "One of: eSewa, Khalti, Cash on Delivery",
                        },
                        "size": {"type": "string", "description": "e.g. 'EU 42', 'US 9'."},
                        "color": {"type": "string"},
                        "quantity": {"type": "integer", "description": "Default 1."},
                    },
                    "required": [
                        "product_id",
                        "customer_name",
                        "phone",
                        "address",
                        "payment_method",
                    ],
                },
            },
        }

    def run(
        self,
        db: Session,
        product_id: int,
        customer_name: str,
        phone: str,
        address: str,
        payment_method: str,
        size: str | None = None,
        color: str | None = None,
        quantity: int = 1,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        product = db.get(Product, product_id)
        if product is None:
            return {"error": f"No product found with id {product_id}"}
        if quantity < 1:
            return {"error": "quantity must be at least 1"}
        if product.stock_quantity < quantity:
            return {
                "error": (
                    f"Only {product.stock_quantity} left in stock, "
                    f"cannot order {quantity}."
                )
            }
        if payment_method.strip().lower() not in PAYMENT_METHODS:
            return {
                "error": (
                    f"Unsupported payment method '{payment_method}'. "
                    "Supported: eSewa, Khalti, Cash on Delivery."
                )
            }

        # Validate Nepali mobile number (strip spaces/dashes first)
        phone_digits = re.sub(r"[\s\-]", "", phone)
        if not _NEPALI_PHONE_RE.match(phone_digits):
            return {
                "error": (
                    f"'{phone}' doesn't look like a valid Nepali mobile number. "
                    "Please provide a 10-digit number starting with 98, 97, or 96."
                )
            }

        # Duplicate order guard — prevent placing a second order for the same
        # product in the same conversation session.
        if conversation_id:
            existing = (
                db.query(Order)
                .filter(
                    Order.conversation_id == conversation_id,
                    Order.product_id == product_id,
                )
                .first()
            )
            if existing:
                return {
                    "error": (
                        f"An order for this product already exists in this session "
                        f"(Order ID: {existing.id}). To make changes, contact support at 9800000006."
                    )
                }

        total_price = product.current_price * quantity
        order = Order(
            conversation_id=conversation_id,
            product_id=product.id,
            product_name_snapshot=product.name,
            color=color or product.color,
            size=size,
            quantity=quantity,
            unit_price=product.current_price,
            total_price=total_price,
            currency=product.currency,
            customer_name=customer_name,
            phone=phone_digits,
            address=address,
            payment_method=payment_method,
            status=OrderStatus.PENDING_PAYMENT,
        )
        db.add(order)

        # Decrement stock atomically in the same transaction so overselling
        # is impossible — if the commit fails, neither the order nor the
        # stock change is persisted.
        product.stock_quantity -= quantity
        db.add(product)

        db.commit()
        db.refresh(order)

        return {
            "order_id": order.id,
            "product_name": product.name,
            "size": size,
            "color": order.color,
            "quantity": quantity,
            "total_price": total_price,
            "currency": product.currency,
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
            return {"error": "Provide either order_id or phone to look up an order."}

        if order_id:
            order = db.get(Order, order_id)
            if order is None:
                return {"error": f"No order found with id {order_id}."}
            return {"orders": [_order_to_dict(order)]}

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
        "product_name": order.product_name_snapshot,
        "color": order.color,
        "size": order.size,
        "quantity": order.quantity,
        "total_price": order.total_price,
        "currency": order.currency,
        "payment_method": order.payment_method,
        "status": order.status.value,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "address": order.address,
        "created_at": order.created_at.isoformat() if order.created_at else None,
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
            "product_name": order.product_name_snapshot,
            "payment_method": order.payment_method,
            "total_price": order.total_price,
            "currency": order.currency,
            "status": order.status.value,
        }


# --- Registry ----------------------------------------------------------
# One dict, built from the tool objects themselves -- TOOL_SPECS is derived
# from TOOLS, not maintained as a second, independent list that could
# silently drift out of sync with the actual tool classes.

TOOLS: dict[str, Tool] = {
    tool.name: tool
    for tool in (
        SearchProductsTool(),
        GetPriceHistoryTool(),
        CheckStockTool(),
        CreateOrderTool(),
        GetOrderStatusTool(),
        ValidatePhoneTool(),
        ValidateAddressTool(),
        UpdateOrderPaymentTool(),
    )
}

TOOL_SPECS: list[dict[str, Any]] = [tool.spec for tool in TOOLS.values()]