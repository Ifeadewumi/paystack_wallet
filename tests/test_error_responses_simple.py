"""
Simple unit tests for error response handling.
Tests all error scenarios return correct status codes and descriptive messages.
Requirements: 17.1-17.6
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock

from app.main import app


@pytest.fixture
def client():
    """Simple test client without database dependencies."""
    return TestClient(app)


class TestAuthenticationErrors:
    """Test authentication error responses - Requirements 17.2, 17.3"""
    
    def test_malformed_jwt_token(self, client: TestClient):
        """Test malformed JWT token returns 401."""
        response = client.get(
            "/wallet/balance",
            headers={"Authorization": "Bearer invalid.jwt.token"}
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Could not validate credentials"
    
    def test_no_authentication_provided(self, client: TestClient):
        """Test request with no authentication returns 403."""
        response = client.get("/wallet/balance")
        
        assert response.status_code == 403
        assert "Not authenticated" in response.json()["detail"]
    
    def test_invalid_api_key_format(self, client: TestClient):
        """Test API key with wrong format returns 401."""
        response = client.get(
            "/wallet/balance",
            headers={
                "Authorization": "Bearer dummy_token",
                "x-api-key": "invalid_key_format"
            }
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Could not validate credentials"


class TestValidationErrors:
    """Test validation error responses - Requirement 17.1"""
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_zero_deposit_amount(self, mock_auth, client: TestClient):
        """Test deposit with zero amount returns 400."""
        # Mock authentication to bypass auth checks
        mock_auth.return_value = (None, ["deposit"])
        
        response = client.post(
            "/wallet/deposit",
            headers={"Authorization": "Bearer test_token"},
            json={"amount": 0}
        )
        
        assert response.status_code == 400
        assert "Amount must be greater than 0" in response.json()["detail"]
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_negative_deposit_amount(self, mock_auth, client: TestClient):
        """Test deposit with negative amount returns 400."""
        # Mock authentication to bypass auth checks
        mock_auth.return_value = (None, ["deposit"])
        
        response = client.post(
            "/wallet/deposit",
            headers={"Authorization": "Bearer test_token"},
            json={"amount": -100}
        )
        
        assert response.status_code == 400
        assert "Amount must be greater than 0" in response.json()["detail"]
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_zero_transfer_amount(self, mock_auth, client: TestClient):
        """Test transfer with zero amount returns 400."""
        # Mock authentication to bypass auth checks
        mock_auth.return_value = (None, ["transfer"])
        
        response = client.post(
            "/wallet/transfer",
            headers={"Authorization": "Bearer test_token"},
            json={"recipient_wallet_number": "1234567890", "amount": 0}
        )
        
        assert response.status_code == 400
        assert "Transfer amount must be greater than 0" in response.json()["detail"]
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_negative_transfer_amount(self, mock_auth, client: TestClient):
        """Test transfer with negative amount returns 400."""
        # Mock authentication to bypass auth checks
        mock_auth.return_value = (None, ["transfer"])
        
        response = client.post(
            "/wallet/transfer",
            headers={"Authorization": "Bearer test_token"},
            json={"recipient_wallet_number": "1234567890", "amount": -500}
        )
        
        assert response.status_code == 400
        assert "Transfer amount must be greater than 0" in response.json()["detail"]


class TestPermissionErrors:
    """Test permission error responses - Requirement 17.4"""
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_missing_deposit_permission(self, mock_auth, client: TestClient):
        """Test API key without deposit permission returns 403."""
        # Mock authentication with only read permission
        mock_auth.return_value = (None, ["read"])
        
        response = client.post(
            "/wallet/deposit",
            headers={"Authorization": "Bearer test_token"},
            json={"amount": 1000}
        )
        
        assert response.status_code == 403
        assert "deposit" in response.json()["detail"].lower()
        assert "insufficient permissions" in response.json()["detail"].lower()
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_missing_transfer_permission(self, mock_auth, client: TestClient):
        """Test API key without transfer permission returns 403."""
        # Mock authentication with only read permission
        mock_auth.return_value = (None, ["read"])
        
        response = client.post(
            "/wallet/transfer",
            headers={"Authorization": "Bearer test_token"},
            json={"recipient_wallet_number": "1234567890", "amount": 500}
        )
        
        assert response.status_code == 403
        assert "transfer" in response.json()["detail"].lower()
        assert "insufficient permissions" in response.json()["detail"].lower()
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_missing_read_permission(self, mock_auth, client: TestClient):
        """Test API key without read permission returns 403."""
        # Mock authentication with only deposit permission
        mock_auth.return_value = (None, ["deposit"])
        
        response = client.get(
            "/wallet/balance",
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 403
        assert "read" in response.json()["detail"].lower()
        assert "insufficient permissions" in response.json()["detail"].lower()


class TestPaystackErrors:
    """Test Paystack error responses - Requirement 17.6"""
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    @patch('httpx.AsyncClient.post')
    def test_paystack_initialization_failure(self, mock_post, mock_auth, client: TestClient):
        """Test Paystack initialization failure returns 402."""
        # Mock authentication
        mock_auth.return_value = (None, ["deposit"])
        
        # Mock Paystack API failure
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid request parameters"
        mock_post.return_value = mock_response
        
        response = client.post(
            "/wallet/deposit",
            headers={"Authorization": "Bearer test_token"},
            json={"amount": 1000}
        )
        
        assert response.status_code == 402
        assert "Payment initiation failed" in response.json()["detail"]
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    @patch('httpx.AsyncClient.post')
    def test_paystack_status_false_response(self, mock_post, mock_auth, client: TestClient):
        """Test Paystack returning status: false returns 402."""
        # Mock authentication
        mock_auth.return_value = (None, ["deposit"])
        
        # Mock Paystack API returning status: false
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": False, "message": "Transaction failed"}
        mock_post.return_value = mock_response
        
        response = client.post(
            "/wallet/deposit",
            headers={"Authorization": "Bearer test_token"},
            json={"amount": 1000}
        )
        
        assert response.status_code == 402
        assert "Payment initiation failed by Paystack" in response.json()["detail"]


class TestWebhookErrors:
    """Test webhook error responses"""
    
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


class TestNotFoundErrors:
    """Test not found error responses - Requirement 17.5"""
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_deposit_status_not_found(self, mock_auth, client: TestClient):
        """Test deposit status for non-existent reference returns 404."""
        # Mock authentication
        mock_auth.return_value = (None, ["read"])
        
        response = client.get(
            "/wallet/deposit/nonexistent_reference/status",
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 404
        assert "Deposit transaction not found" in response.json()["detail"]
    
    @patch('app.auth_utils.get_current_user_with_permissions')
    def test_deposit_verify_not_found(self, mock_auth, client: TestClient):
        """Test deposit verify for non-existent reference returns 404."""
        # Mock authentication
        mock_auth.return_value = (None, ["read"])
        
        response = client.get(
            "/wallet/deposit/nonexistent_reference/verify",
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 404
        assert "Deposit transaction not found" in response.json()["detail"]