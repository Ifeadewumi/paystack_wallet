import asyncio
import pytest
import pytest_asyncio
import asyncpg
from typing import AsyncGenerator, Generator
from urllib.parse import urlparse

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import get_db, Base
from app.config import settings
from app.models import User, Wallet, ApiKey, ApiKeyPermissions
from app.auth_utils import create_access_token, hash_api_key

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

@pytest_asyncio.fixture(scope="session")
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


@pytest_asyncio.fixture(scope="session")
async def test_engine(test_db_url: str, setup_test_db):
    """Create a single engine for the entire test session."""
    engine = create_async_engine(
        test_db_url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=300
    )
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a new database session for each test function."""
    async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Start a transaction that we can rollback for test isolation
        async with session.begin():
            yield session
            # Transaction will be rolled back automatically

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

@pytest_asyncio.fixture(scope="function")
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user and wallet, and return the user object."""
    import uuid
    test_id = uuid.uuid4().hex[:8]
    
    user = User(
        google_id=f"test_google_id_{test_id}",
        email=f"testuser_{test_id}@example.com",
        name="Test User"
    )
    wallet = Wallet(
        user=user,
        wallet_number=f"{test_id[:10]}",
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

@pytest.fixture(scope="function")
def auth_headers(auth_token: str) -> dict:
    """Generate authorization headers for JWT authentication."""
    return {"Authorization": f"Bearer {auth_token}"}

@pytest_asyncio.fixture(scope="function")
async def test_api_key(db_session: AsyncSession, test_user: User) -> tuple[str, ApiKey]:
    """Create a test API key and return both the plain key and the database object."""
    import secrets
    from datetime import datetime, timedelta, timezone
    
    # Generate a test API key
    random_part = secrets.token_urlsafe(32)
    plain_api_key = f"{settings.api_key_prefix}_{random_part}"
    key_prefix = random_part[:8]
    key_hash = hash_api_key(plain_api_key)
    
    # Create API key in database
    api_key = ApiKey(
        user_id=test_user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Test API Key",
        permissions=[p.value for p in ApiKeyPermissions],  # All permissions
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True
    )
    
    db_session.add(api_key)
    await db_session.commit()
    await db_session.refresh(api_key)
    
    return plain_api_key, api_key

@pytest.fixture(scope="function")
def api_key_headers(test_api_key: tuple[str, ApiKey]) -> dict:
    """Generate x-api-key headers for API key authentication."""
    plain_api_key, _ = test_api_key
    return {"x-api-key": plain_api_key}

# --- Property-Based Testing Fixtures ---

@pytest_asyncio.fixture(scope="function")
async def clean_db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield a clean database session for property-based tests."""
    async_session = sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        yield session

@pytest.fixture(scope="function")
def test_db_url_fixture(test_db_url: str) -> str:
    """Provide test database URL for property tests that need to create their own sessions."""
    return test_db_url