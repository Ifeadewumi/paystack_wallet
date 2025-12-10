# Authentication Testing Guide

This guide explains how to test authenticated endpoints in the Paystack Wallet application.

## Authentication Methods

The application supports two authentication methods:

1. **JWT Authentication**: Uses `Authorization: Bearer <token>` header
2. **API Key Authentication**: Uses `x-api-key: <api_key>` header

## Available Test Fixtures

### JWT Authentication Fixtures

```python
# Basic fixtures (available in conftest.py)
def test_example(auth_headers: dict):
    # auth_headers = {"Authorization": "Bearer <jwt_token>"}
    response = client.get("/wallet/balance", headers=auth_headers)
```

### API Key Authentication Fixtures

```python
# Basic API key with all permissions
def test_example(api_key_headers: dict):
    # api_key_headers = {"x-api-key": "sk_live_<random_key>"}
    response = client.get("/wallet/balance", headers=api_key_headers)

# Access the raw API key and database object
def test_example(test_api_key: tuple[str, ApiKey]):
    plain_api_key, api_key_db_object = test_api_key
    headers = {"x-api-key": plain_api_key}
```

## Creating Custom API Keys with Specific Permissions

### Method 1: Custom Fixture

```python
@pytest_asyncio.fixture
async def deposit_only_api_key(db_session: AsyncSession, test_user: User):
    """API key with only deposit permission."""
    import secrets
    from datetime import datetime, timedelta, timezone
    from app.config import settings
    from app.auth_utils import hash_api_key
    
    random_part = secrets.token_urlsafe(32)
    plain_api_key = f"{settings.api_key_prefix}_{random_part}"
    key_prefix = random_part[:8]
    key_hash = hash_api_key(plain_api_key)
    
    api_key = ApiKey(
        user_id=test_user.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name="Deposit Only Key",
        permissions=[ApiKeyPermissions.DEPOSIT.value],
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        is_active=True
    )
    
    db_session.add(api_key)
    await db_session.commit()
    
    return {"x-api-key": plain_api_key}
```

### Method 2: Helper Function

```python
async def create_api_key_headers(db_session, user, permissions=None):
    """Helper to create API key with specific permissions."""
    # Implementation in tests/test_auth_examples.py
    pass

# Usage:
async def test_example(db_session, test_user):
    headers = await create_api_key_headers(
        db_session, 
        test_user, 
        permissions=[ApiKeyPermissions.READ.value]
    )
    response = client.get("/wallet/transactions", headers=headers)
```

## Property-Based Testing with Authentication

### Using Hypothesis with Authentication

```python
from hypothesis import given, strategies as st
from tests.generators import permission_list_strategy

@given(permissions=permission_list_strategy())
async def test_api_key_permissions_property(permissions, db_session, test_user):
    """Test that API keys work with any valid permission combination."""
    headers = await create_api_key_headers(db_session, test_user, permissions)
    
    # Test endpoints based on permissions
    if ApiKeyPermissions.READ.value in permissions:
        response = client.get("/wallet/balance", headers=headers)
        assert response.status_code != 403
    else:
        response = client.get("/wallet/balance", headers=headers)
        assert response.status_code == 403
```

## Permission Testing Patterns

### Testing Permission Enforcement

```python
def test_permission_enforcement(client, test_user, db_session):
    # Create API key without transfer permission
    headers = await create_api_key_headers(
        db_session, 
        test_user, 
        permissions=[ApiKeyPermissions.DEPOSIT.value, ApiKeyPermissions.READ.value]
    )
    
    # Should succeed (has deposit permission)
    response = client.post("/wallet/deposit", headers=headers, json={"amount": 1000})
    assert response.status_code != 403
    
    # Should fail (no transfer permission)
    response = client.post("/wallet/transfer", headers=headers, json={
        "recipient_wallet_number": "1234567890", 
        "amount": 500
    })
    assert response.status_code == 403
    assert "transfer" in response.json()["detail"].lower()
```

### JWT vs API Key Comparison

```python
def test_jwt_vs_api_key(client, auth_headers, api_key_headers):
    # JWT should have all permissions
    response = client.get("/wallet/balance", headers=auth_headers)
    jwt_status = response.status_code
    
    # API key should have same access (if it has all permissions)
    response = client.get("/wallet/balance", headers=api_key_headers)
    api_key_status = response.status_code
    
    assert jwt_status == api_key_status
```

## Common Authentication Test Patterns

### 1. Test Unauthenticated Access

```python
def test_requires_authentication(client):
    response = client.get("/wallet/balance")
    assert response.status_code == 401
```

### 2. Test Invalid Token

```python
def test_invalid_token(client):
    headers = {"Authorization": "Bearer invalid_token"}
    response = client.get("/wallet/balance", headers=headers)
    assert response.status_code == 401
```

### 3. Test Invalid API Key

```python
def test_invalid_api_key(client):
    headers = {"x-api-key": "sk_live_invalid_key"}
    response = client.get("/wallet/balance", headers=headers)
    assert response.status_code == 401
```

### 4. Test Expired API Key

```python
@pytest_asyncio.fixture
async def expired_api_key(db_session, test_user):
    # Create API key that's already expired
    from datetime import datetime, timedelta, timezone
    
    api_key = ApiKey(
        user_id=test_user.id,
        # ... other fields ...
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired
        is_active=True
    )
    
    db_session.add(api_key)
    await db_session.commit()
    
    return {"x-api-key": plain_api_key}

def test_expired_api_key(client, expired_api_key):
    response = client.get("/wallet/balance", headers=expired_api_key)
    assert response.status_code == 403
    assert "expired" in response.json()["detail"].lower()
```

## Available Permission Types

```python
from app.models import ApiKeyPermissions

# Available permissions:
ApiKeyPermissions.DEPOSIT.value   # "deposit"
ApiKeyPermissions.TRANSFER.value  # "transfer" 
ApiKeyPermissions.READ.value      # "read"
```

## Quick Reference

| Authentication Type | Header | Format | Permissions |
|-------------------|---------|---------|-------------|
| JWT | `Authorization` | `Bearer <token>` | All permissions |
| API Key | `x-api-key` | `sk_live_<random>` | Configurable |

## Example Test File Structure

```python
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

class TestWalletEndpoints:
    def test_balance_with_jwt(self, client, auth_headers):
        response = client.get("/wallet/balance", headers=auth_headers)
        # Test logic
    
    def test_balance_with_api_key(self, client, api_key_headers):
        response = client.get("/wallet/balance", headers=api_key_headers)
        # Test logic
    
    async def test_deposit_permission_required(self, client, db_session, test_user):
        # Create API key without deposit permission
        headers = await create_api_key_headers(
            db_session, test_user, 
            permissions=[ApiKeyPermissions.READ.value]
        )
        
        response = client.post("/wallet/deposit", headers=headers, json={"amount": 1000})
        assert response.status_code == 403
```