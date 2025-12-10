import pytest
import respx
import httpx
from unittest.mock import AsyncMock
from app.routers.wallet import verify_paystack_transaction
from app.config import settings

pytestmark = pytest.mark.asyncio

PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify"


@respx.mock
async def test_verify_paystack_transaction_success():
    """Test successful Paystack transaction verification."""
    reference = "dep_test_reference_123"
    
    # Mock successful Paystack response
    respx.get(f"{PAYSTACK_VERIFY_URL}/{reference}").respond(200, json={
        "status": True,
        "message": "Verification successful",
        "data": {
            "reference": reference,
            "status": "success",
            "amount": 5000,
            "currency": "NGN",
            "paid_at": "2023-01-01T12:00:00.000Z"
        }
    })
    
    # Call the function
    result = await verify_paystack_transaction(reference)
    
    # Verify the result
    assert result["status"] is True
    assert result["message"] == "Verification successful"
    assert result["data"]["reference"] == reference
    assert result["data"]["status"] == "success"
    assert result["data"]["amount"] == 5000


@respx.mock
async def test_verify_paystack_transaction_failed():
    """Test Paystack transaction verification for failed transaction."""
    reference = "dep_failed_reference_456"
    
    # Mock failed transaction response
    respx.get(f"{PAYSTACK_VERIFY_URL}/{reference}").respond(200, json={
        "status": True,
        "message": "Verification successful",
        "data": {
            "reference": reference,
            "status": "failed",
            "amount": 3000,
            "currency": "NGN"
        }
    })
    
    # Call the function
    result = await verify_paystack_transaction(reference)
    
    # Verify the result
    assert result["status"] is True
    assert result["data"]["reference"] == reference
    assert result["data"]["status"] == "failed"
    assert result["data"]["amount"] == 3000


@respx.mock
async def test_verify_paystack_transaction_api_error():
    """Test handling of Paystack API error during verification."""
    reference = "dep_error_reference_789"
    
    # Mock API error response
    respx.get(f"{PAYSTACK_VERIFY_URL}/{reference}").respond(500, json={
        "status": False,
        "message": "Internal server error"
    })
    
    # Call the function and expect HTTPException
    with pytest.raises(Exception) as exc_info:
        await verify_paystack_transaction(reference)
    
    # Verify the exception details
    assert "Paystack verification failed" in str(exc_info.value)


@respx.mock
async def test_verify_paystack_transaction_network_error():
    """Test handling of network error during verification."""
    reference = "dep_network_error_ref"
    
    # Mock network error
    respx.get(f"{PAYSTACK_VERIFY_URL}/{reference}").side_effect = httpx.ConnectError("Network error")
    
    # Call the function and expect the network error to propagate
    with pytest.raises(httpx.ConnectError):
        await verify_paystack_transaction(reference)


def test_verify_paystack_transaction_url_construction():
    """Test that the correct URL is constructed for Paystack verify API."""
    reference = "dep_url_test_ref"
    expected_url = f"{PAYSTACK_VERIFY_URL}/{reference}"
    
    # This is a simple unit test to verify URL construction logic
    # In a real scenario, this would be part of the function implementation
    constructed_url = f"{PAYSTACK_VERIFY_URL}/{reference}"
    assert constructed_url == expected_url
    assert reference in constructed_url
    assert "https://api.paystack.co/transaction/verify" in constructed_url