"""
Comprehensive unit tests for error response handling.
Tests all error scenarios return correct status codes and descriptive messages.
Requirements: 17.1-17.6
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import respx
import hmac
import hashlib
import json
from datetime import datetime, timedelta, timezone

from app.models import User, Wallet, Transaction, TransactionStatus, TransactionType, ApiKey, ApiKeyPermissions
from app.config import settings
from app.auth_utils import hash_api_key

pytestmark = pytest.mark.asyncio

PAYSTACK_INITIALIZE_URL = "https://api.paystack.co/transaction/initialize"
PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify"


class TestInsufficientBalanceErrors:
    """Test insufficient balance returns 400 with correct message - Requirement 17.1"""
    
    async def test_transfer_insufficient_balance(self, client: TestClient, auth_headers: dict, test_user: User):
        """Test transfer with insufficient balance returns 400 with 'Insufficient funds' message."""
        response = client.post(
            "/wallet/transfer",
            headers=auth_headers,
            json={"recipient_wallet_number": "9876543210", "amount": 999999999}  # Very large amount
        )
        
        assert response.status_code == 400
        assert "Insufficient funds" in response.json()["detail"]


class TestInvalidAPIKeyErrors:
    """Test invalid API key returns 401 with correct message - Requirement 17.2"""
    
    def test_malformed_jwt_token(self, client: TestClient):
        """Test malformed JWT token returns 401."""
        response = client.get(
            "/wallet/balance",
            headers={"Authorization": "Bearer invalid.jwt.token"}
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Could not validate credentials"
    
    def test_no_authentication_provided(self, client: TestClient):
        """Test request with no authentication returns 403 (HTTPBearer behavior)."""
        response = client.get("/wallet/balance")
        
        # HTTPBearer dependency returns 403 when no Authorization header is provided
        assert response.status_code == 403
        assert "Not authenticated" in response.json()["detail"]
    
    def test_invalid_api_key_format(self, client: TestClient):
        """Test API key with wrong format returns 401."""
        response = client.get(
            "/wallet/balance",
            headers={
                "Authorization": "Bearer dummy_token",  # Provide dummy auth to bypass HTTPBearer
                "x-api-key": "invalid_key_format"
            }
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Could not validate credentials"
    
    def test_api_key_wrong_prefix(self, client: TestClient):
        """Test API key with wrong prefix returns 401."""
        response = client.get(
            "/wallet/balance",
            headers={
                "Authorization": "Bearer dummy_token",  # Provide dummy auth to bypass HTTPBearer
                "x-api-key": "wrong_prefix_abcdefghijklmnop"
            }
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Could not validate credentials"
    
    def test_nonexistent_api_key(self, client: TestClient):
        """Test API key that doesn't exist in database returns 401."""
        response = client.get(
            "/wallet/balance",
            headers={
                "Authorization": "Bearer dummy_token",  # Provide dummy auth to bypass HTTPBearer
                "x-api-key": "sk_live_nonexistentkey12345678"
            }
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Could not validate credentials"


class TestExpiredAPIKeyErrors:
    """Test expired API key returns 403 with correct message - Requirement 17.3"""
    
    async def test_expired_api_key_access(self, client: TestClient, db_session: AsyncSession, test_user: User):
        """Test expired API key returns 403 with 'API key has expired' message."""
        import secrets
        
        # Create an expired API key
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        expired_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Expired Test Key",
            permissions=[ApiKeyPermissions.READ.value],
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),  # Expired yesterday
            is_active=True
        )
        
        db_session.add(expired_key)
        await db_session.commit()
        
        response = client.get(
            "/wallet/balance",
            headers={
                "Authorization": "Bearer dummy_token",
                "x-api-key": plain_api_key
            }
        )
        
        assert response.status_code == 403
        assert response.json()["detail"] == "API key has expired"


class TestInactiveAPIKeyErrors:
    """Test inactive API key returns 403 with correct message - Requirement 17.3"""
    
    async def test_inactive_api_key_access(self, client: TestClient, db_session: AsyncSession, test_user: User):
        """Test inactive API key returns 403 with 'API key is inactive' message."""
        import secrets
        
        # Create an inactive API key
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        inactive_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Inactive Test Key",
            permissions=[ApiKeyPermissions.READ.value],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=False  # Inactive
        )
        
        db_session.add(inactive_key)
        await db_session.commit()
        
        response = client.get(
            "/wallet/balance",
            headers={
                "Authorization": "Bearer dummy_token",
                "x-api-key": plain_api_key
            }
        )
        
        assert response.status_code == 403
        assert response.json()["detail"] == "API key is inactive"


class TestMissingPermissionErrors:
    """Test missing permission returns 403 with permission name - Requirement 17.4"""
    
    async def test_missing_deposit_permission(self, client: TestClient, db_session: AsyncSession, test_user: User):
        """Test API key without deposit permission returns 403 with 'deposit' in message."""
        import secrets
        
        # Create an API key with only read permission
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        read_only_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Read Only Test Key",
            permissions=[ApiKeyPermissions.READ.value],  # Only read permission
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True
        )
        
        db_session.add(read_only_key)
        await db_session.commit()
        
        response = client.post(
            "/wallet/deposit",
            headers={
                "Authorization": "Bearer dummy_token",
                "x-api-key": plain_api_key
            },
            json={"amount": 1000}
        )
        
        assert response.status_code == 403
        assert "deposit" in response.json()["detail"].lower()
        assert "insufficient permissions" in response.json()["detail"].lower()
    
    async def test_missing_transfer_permission(self, client: TestClient, db_session: AsyncSession, test_user: User):
        """Test API key without transfer permission returns 403 with 'transfer' in message."""
        import secrets
        
        # Create an API key with only read permission
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        read_only_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Read Only Test Key",
            permissions=[ApiKeyPermissions.READ.value],  # Only read permission
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True
        )
        
        db_session.add(read_only_key)
        await db_session.commit()
        
        response = client.post(
            "/wallet/transfer",
            headers={
                "Authorization": "Bearer dummy_token",
                "x-api-key": plain_api_key
            },
            json={"recipient_wallet_number": "1234567890", "amount": 500}
        )
        
        assert response.status_code == 403
        assert "transfer" in response.json()["detail"].lower()
        assert "insufficient permissions" in response.json()["detail"].lower()


class TestNotFoundErrors:
    """Test not found returns 404 with descriptive message - Requirement 17.5"""
    
    def test_deposit_status_not_found(self, client: TestClient, auth_headers: dict):
        """Test deposit status for non-existent reference returns 404."""
        response = client.get(
            "/wallet/deposit/nonexistent_reference/status",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "Deposit transaction not found" in response.json()["detail"]
    
    def test_deposit_verify_not_found(self, client: TestClient, auth_headers: dict):
        """Test deposit verify for non-existent reference returns 404."""
        response = client.get(
            "/wallet/deposit/nonexistent_reference/verify",
            headers=auth_headers
        )
        
        assert response.status_code == 404
        assert "Deposit transaction not found" in response.json()["detail"]
    
    def test_transfer_to_nonexistent_wallet(self, client: TestClient, auth_headers: dict):
        """Test transfer to non-existent wallet returns 404."""
        response = client.post(
            "/wallet/transfer",
            headers=auth_headers,
            json={"recipient_wallet_number": "nonexistent123", "amount": 100}
        )
        
        assert response.status_code == 404
        assert "Recipient wallet not found" in response.json()["detail"]


class TestPaystackFailureErrors:
    """Test Paystack failure returns 402 with details - Requirement 17.6"""
    
    @respx.mock
    def test_paystack_initialization_failure(self, client: TestClient, auth_headers: dict):
        """Test Paystack initialization failure returns 402 with details."""
        # Mock Paystack API failure
        respx.post(PAYSTACK_INITIALIZE_URL).respond(400, text="Invalid request parameters")
        
        response = client.post(
            "/wallet/deposit",
            headers=auth_headers,
            json={"amount": 1000}
        )
        
        assert response.status_code == 402
        assert "Payment initiation failed" in response.json()["detail"]
        assert "Invalid request parameters" in response.json()["detail"]
    
    @respx.mock
    def test_paystack_status_false_response(self, client: TestClient, auth_headers: dict):
        """Test Paystack returning status: false returns 402."""
        # Mock Paystack API returning status: false
        respx.post(PAYSTACK_INITIALIZE_URL).respond(200, json={
            "status": False, 
            "message": "Transaction failed"
        })
        
        response = client.post(
            "/wallet/deposit",
            headers=auth_headers,
            json={"amount": 1000}
        )
        
        assert response.status_code == 402
        assert "Payment initiation failed by Paystack" in response.json()["detail"]
    
    @respx.mock
    async def test_paystack_verify_failure(self, client: TestClient, auth_headers: dict, db_session: AsyncSession):
        """Test Paystack verify API failure returns 502."""
        # First create a deposit transaction
        respx.post(PAYSTACK_INITIALIZE_URL).respond(200, json={
            "status": True,
            "message": "Authorization URL created",
            "data": {
                "authorization_url": "https://checkout.paystack.com/test-url",
                "access_code": "test-access-code",
                "reference": "dep_test-reference"
            }
        })
        
        response = client.post(
            "/wallet/deposit",
            headers=auth_headers,
            json={"amount": 1000}
        )
        reference = response.json()["reference"]
        
        # Mock verify API failure
        respx.get(f"{PAYSTACK_VERIFY_URL}/{reference}").respond(400, text="API error")
        
        # Try to verify the deposit
        response = client.get(
            f"/wallet/deposit/{reference}/verify",
            headers=auth_headers
        )
        
        assert response.status_code == 502
        assert "Paystack verification failed" in response.json()["detail"]


class TestValidationErrors:
    """Test validation errors return 400 with correct messages"""
    
    def test_zero_deposit_amount(self, client: TestClient, auth_headers: dict):
        """Test deposit with zero amount returns 400."""
        response = client.post(
            "/wallet/deposit",
            headers=auth_headers,
            json={"amount": 0}
        )
        
        assert response.status_code == 400
        assert "Amount must be greater than 0" in response.json()["detail"]
    
    def test_negative_deposit_amount(self, client: TestClient, auth_headers: dict):
        """Test deposit with negative amount returns 400."""
        response = client.post(
            "/wallet/deposit",
            headers=auth_headers,
            json={"amount": -100}
        )
        
        assert response.status_code == 400
        assert "Amount must be greater than 0" in response.json()["detail"]
    
    def test_zero_transfer_amount(self, client: TestClient, auth_headers: dict):
        """Test transfer with zero amount returns 400."""
        response = client.post(
            "/wallet/transfer",
            headers=auth_headers,
            json={"recipient_wallet_number": "1234567890", "amount": 0}
        )
        
        assert response.status_code == 400
        assert "Transfer amount must be greater than 0" in response.json()["detail"]
    
    def test_negative_transfer_amount(self, client: TestClient, auth_headers: dict):
        """Test transfer with negative amount returns 400."""
        response = client.post(
            "/wallet/transfer",
            headers=auth_headers,
            json={"recipient_wallet_number": "1234567890", "amount": -500}
        )
        
        assert response.status_code == 400
        assert "Transfer amount must be greater than 0" in response.json()["detail"]


class TestWebhookErrors:
    """Test webhook-specific error scenarios"""
    
    def test_webhook_missing_signature(self, client: TestClient):
        """Test webhook without signature returns 400."""
        response = client.post(
            "/wallet/paystack/webhook",
            json={"event": "charge.success", "data": {"reference": "dep_test123"}}
        )
        
        assert response.status_code == 400
        assert "Missing Paystack signature" in response.json()["detail"]
    
    def test_webhook_invalid_signature(self, client: TestClient):
        """Test webhook with invalid signature returns 400."""
        response = client.post(
            "/wallet/paystack/webhook",
            headers={"x-paystack-signature": "invalid_signature"},
            json={"event": "charge.success", "data": {"reference": "dep_test123"}}
        )
        
        assert response.status_code == 400
        assert "Invalid signature" in response.json()["detail"]