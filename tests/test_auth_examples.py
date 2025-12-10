"""
Examples showing how to use authentication headers in tests.
"""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from hypothesis import given, strategies as st
from datetime import datetime, timezone

from app.models import User, ApiKey, ApiKeyPermissions
from tests.generators import permission_list_strategy


class TestAuthenticationExamples:
    """Examples of how to test authenticated endpoints."""

    def test_jwt_headers_format(self, auth_headers: dict):
        """Example: Verify JWT headers are correctly formatted."""
        assert "Authorization" in auth_headers
        assert auth_headers["Authorization"].startswith("Bearer ")
        token = auth_headers["Authorization"].split(" ")[1]
        assert len(token) > 20  # JWT tokens are long

    def test_api_key_headers_format(self, api_key_headers: dict):
        """Example: Verify API key headers are correctly formatted."""
        assert "x-api-key" in api_key_headers
        assert api_key_headers["x-api-key"].startswith("sk_live_")
        key = api_key_headers["x-api-key"]
        assert len(key) > 20  # API keys are long

    @pytest_asyncio.fixture
    async def api_key_with_deposit_only(self, db_session: AsyncSession, test_user: User) -> tuple[str, dict]:
        """Create an API key with only deposit permission."""
        import secrets
        from datetime import datetime, timedelta, timezone
        from app.config import settings
        from app.auth_utils import hash_api_key
        
        # Generate API key
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        # Create API key with only deposit permission
        api_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Deposit Only API Key",
            permissions=[ApiKeyPermissions.DEPOSIT.value],  # Only deposit permission
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True
        )
        
        db_session.add(api_key)
        await db_session.commit()
        
        headers = {"x-api-key": plain_api_key}
        return plain_api_key, headers

    def test_limited_permissions_example(self, client: TestClient, api_key_with_deposit_only):
        """Example: Test API key with limited permissions."""
        plain_api_key, headers = api_key_with_deposit_only
        
        # This should work (deposit permission)
        response = client.post("/wallet/deposit", 
                             headers=headers, 
                             json={"amount": 1000})
        # Handle the response based on your endpoint logic
        
        # This should fail (no transfer permission)
        response = client.post("/wallet/transfer", 
                             headers=headers, 
                             json={"recipient_wallet_number": "1234567890", "amount": 500})
        assert response.status_code == 403
        assert "transfer" in response.json()["detail"].lower()

    @given(permissions=permission_list_strategy())
    def test_property_based_permissions_example(self, permissions: list[str]):
        """Example: Property-based test for API key permissions."""
        # This is a simple example - you'd typically create the API key in the database
        # and test actual endpoint behavior
        
        # Test that permissions list is valid
        valid_permissions = [p.value for p in ApiKeyPermissions]
        for perm in permissions:
            assert perm in valid_permissions
        
        # Test that permissions are unique
        assert len(permissions) == len(set(permissions))


# --- Helper Functions for Manual Use ---

def create_jwt_headers(user_id: str) -> dict:
    """Helper function to create JWT headers for a specific user ID."""
    from app.auth_utils import create_access_token
    token = create_access_token(data={"sub": user_id})
    return {"Authorization": f"Bearer {token}"}


async def create_api_key_headers(db_session: AsyncSession, user: User, permissions: list[str] = None) -> dict:
    """Helper function to create API key headers with specific permissions."""
    import secrets
    from datetime import datetime, timedelta, timezone
    from app.config import settings
    from app.auth_utils import hash_api_key
    
    if permissions is None:
        permissions = [p.value for p in ApiKeyPermissions]  # All permissions
    
    # Generate API key
    random_part = secrets.token_urlsafe(32)
    plain_api_key = f"{settings.api_key_prefix}_{random_part}"
    key_prefix = random_part[:8]
    key_hash = hash_api_key(plain_api_key)
    
    # Create API key in database
    api_key = ApiKey(
        user_id=user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Test API Key",
        permissions=permissions,
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True
    )
    
    db_session.add(api_key)
    await db_session.commit()
    
    return {"x-api-key": plain_api_key}


# --- Property-Based Testing Examples ---

class TestPropertyBasedAuth:
    """Examples of property-based testing with authentication."""
    
    @given(st.lists(st.sampled_from([p.value for p in ApiKeyPermissions]), min_size=1, unique=True))
    async def test_api_key_permissions_property(self, permissions: list[str], db_session: AsyncSession, test_user: User):
        """Property test: API keys should only grant the permissions they're assigned."""
        headers = await create_api_key_headers(db_session, test_user, permissions)
        
        # Test that the API key was created with the correct permissions
        from sqlalchemy import select
        result = await db_session.execute(
            select(ApiKey).where(ApiKey.user_id == test_user.id)
        )
        api_key = result.scalar_one()
        
        assert set(api_key.permissions) == set(permissions)
        assert api_key.is_active is True
        assert api_key.expires_at > datetime.now(timezone.utc)