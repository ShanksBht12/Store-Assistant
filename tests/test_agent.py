"""
Phase 1 tests. Uses an in-memory SQLite DB and the mock LLM provider
so these run offline with no API key.
"""
import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agent.orchestrator import handle_chat_message
from app.database.database import Base
from app.database.models import Product, ProductPriceHistory

engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(bind=engine)


@pytest.fixture()
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    black = Product(
        sku="SHOE-A-BLACK",
        name="AeroRun X1",
        description="test",
        category="Footwear",
        color="Black",
        current_price=8500,
        currency="NPR",
        stock_quantity=10,
    )
    pink = Product(
        sku="SHOE-A-PINK",
        name="AeroRun X1",
        description="test",
        category="Footwear",
        color="Pink",
        current_price=8700,
        currency="NPR",
        stock_quantity=5,
    )
    session.add_all([black, pink])
    session.flush()
    session.add(
        ProductPriceHistory(
            product_id=black.id,
            price=6500,
            currency="NPR",
            valid_from=datetime(2026, 5, 1),
        )
    )
    session.commit()

    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_current_price_question_is_grounded(db):
    reply, grounded, product = await handle_chat_message(db, "How much are black shoes?")
    assert grounded is True
    assert product is not None
    assert "8500" in reply


@pytest.mark.asyncio
async def test_color_query_matches_correct_variant(db):
    reply, grounded, product = await handle_chat_message(db, "Do you have pink shoes?")
    assert grounded is True
    assert product is not None
    assert product.color == "Pink"
    assert "8700" in reply


@pytest.mark.asyncio
async def test_unknown_product_is_not_hallucinated(db):
    reply, grounded, product = await handle_chat_message(db, "How much are Z Sunglasses?")
    assert grounded is False
    assert product is None
    assert "No matching product" in reply


@pytest.mark.asyncio
async def test_casual_message_does_not_match_product(db):
    reply, grounded, product = await handle_chat_message(db, "hi")
    assert grounded is None
    assert product is None


@pytest.mark.asyncio
async def test_ambiguous_color_followup_stays_with_previous_model(db):
    _, _, previous_product = await handle_chat_message(db, "black shoes")
    reply, grounded, product = await handle_chat_message(
        db, "what blue one?", previous_product.id
    )
    assert grounded is False
    assert product is None
    assert "No matching product" in reply
