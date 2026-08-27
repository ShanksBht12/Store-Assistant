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


@pytest.mark.asyncio
async def test_programming_request_gets_professional_scope_response(db):
    reply, grounded, product = await handle_chat_message(db, "write me a python code")
    assert grounded is None
    assert product is None
    assert "can't provide Python code" in reply


@pytest.mark.asyncio
async def test_financial_gift_request_gets_empathetic_response(db):
    reply, grounded, product = await handle_chat_message(
        db,
        "I do not have money to buy food but my girlfriend wants a good gift.",
    )
    assert grounded is None
    assert product is None
    assert "prioritize food and essentials" in reply


@pytest.mark.asyncio
async def test_followup_price_claim_gets_database_verification(db):
    _, _, previous_product = await handle_chat_message(db, "black shoes")
    reply, grounded, product = await handle_chat_message(
        db, "my friend bought it for 6000 rs only", previous_product.id
    )
    assert grounded is True
    assert product.id == previous_product.id
    assert "couldn't verify" in reply
    assert "6500" in reply


@pytest.mark.asyncio
async def test_catalog_question_lists_available_products(db):
    reply, grounded, product = await handle_chat_message(
        db, "what are the products you have?"
    )
    assert grounded is True
    assert product is None
    assert "AeroRun X1" in reply
    assert "Pink" in reply
