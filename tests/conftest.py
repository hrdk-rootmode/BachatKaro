"""
Pytest configuration and fixtures for DealHunt backend tests.
"""
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.api.v1 import api_router
from app.models import User, Platform, Product

# Test database URL
TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    settings.POSTGRES_DB, f"{settings.POSTGRES_DB}_test"
)

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    poolclass=NullPool,
    echo=False,
)

# Test session factory
TestingSessionLocal = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def setup_test_database() -> AsyncGenerator[None, None]:
    """Create test database tables before all tests and drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    # Seed test data
    async with TestingSessionLocal() as session:
        await seed_test_data(session)
        await session.commit()
    
    yield
    
    # Cleanup
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def seed_test_data(session: AsyncSession) -> None:
    """Seed test platforms and sample data."""
    # Add test platforms
    platforms = [
        Platform(
            name="amazon",
            base_url="https://www.amazon.in",
            affiliate_tag="test-tag",
            selectors={
                "search_url_template": "https://www.amazon.in/s?k={query}",
                "product_title": "#productTitle",
            },
            is_active=True,
        ),
        Platform(
            name="flipkart",
            base_url="https://www.flipkart.com",
            affiliate_tag="test-tag",
            selectors={
                "search_url_template": "https://www.flipkart.com/search?q={query}",
                "product_title": "span.B_NuCI",
            },
            is_active=True,
        ),
    ]
    
    for platform in platforms:
        session.add(platform)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for tests."""
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def app() -> FastAPI:
    """Create a test FastAPI application."""
    from main import app
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict:
    """Return mock authentication headers for testing."""
    # In real tests, you'd generate a valid Firebase token
    return {"Authorization": "Bearer test_token"}


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        firebase_uid="test_firebase_uid_123",
        email="test@example.com",
        phone_number="+919999999999",
        is_active=True,
        hardware_id="test_hardware_123",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user
