import asyncio
import pytest
import asyncpg
from typing import AsyncGenerator, Generator
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db, Base
from app.config import settings
from app.models import User, Wallet
from app.auth_utils import create_access_token

# --- Database Fixtures ---

@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """Create an instance of the default event loop for each test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Create a test database URL and return it."""
    return f"{settings.database_url}_test"

@pytest.fixture(scope="session", autouse=True)
async def setup_test_db(test_db_url: str):
    """Set up and tear down the test database."""
    parsed_url = urlparse(test_db_url)
    db_name = parsed_url.path.lstrip('/')
    
    conn_details = {
        "user": parsed_url.username,
        "password": parsed_url.password,
        "host": parsed_url.hostname,
        "port": parsed_url.port,
        "database": "postgres"
    }

    conn = await asyncpg.connect(**conn_details)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await conn.close()

    # Create tables directly
    engine = create_async_engine(test_db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    yield

    # Teardown
    conn = await asyncpg.connect(**conn_details)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
    finally:
        await conn.close()


@pytest.fixture(scope="function")
async def db_session(test_db_url: str) -> AsyncGenerator[AsyncSession, None]:
    """Yield a new database session for each test function."""
    engine = create_async_engine(test_db_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session
    await engine.dispose()

# --- App and Client Fixtures ---

@pytest.fixture(scope="function")
def client(db_session: AsyncSession) -> Generator[TestClient, None, None]:
    """Yield a TestClient that uses the test database."""
    
    def override_get_db() -> Generator[AsyncSession, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    with TestClient(app) as c:
        yield c

# --- User and Auth Fixtures ---

@pytest.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user and wallet, and return the user object."""
    user = User(
        google_id="test_google_id_123",
        email="testuser@example.com",
        name="Test User"
    )
    wallet = Wallet(
        user=user,
        wallet_number="1234567890",
        balance=10000
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user, ["wallet"])
    return user

@pytest.fixture(scope="function")
def auth_token(test_user: User) -> str:
    """Generate an authentication token for the test user."""
    return create_access_token(data={"sub": str(test_user.id)})