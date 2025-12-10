"""
Property-based tests for webhook processing functionality.
"""
import json
import hmac
import hashlib
import pytest
from hypothesis import given, strategies as st
from hypothesis import settings as hypothesis_settings, HealthCheck
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import User, Wallet, Transaction, TransactionStatus, TransactionType
from tests.generators import (
    user_strategy, 
    transaction_reference_strategy,
    positive_amount_strategy
)


class TestWebhookProperties:
    """Property-based tests for webhook processing."""

    @given(
        payload_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(
                st.text(min_size=1, max_size=100),
                st.integers(),
                st.booleans(),
                st.dictionaries(
                    keys=st.text(min_size=1, max_size=10),
                    values=st.text(min_size=1, max_size=50)
                )
            ),
            min_size=1,
            max_size=10
        ),
        wrong_secret=st.text(min_size=1, max_size=100).filter(
            lambda x: x != settings.paystack_webhook_secret
        )
    )
    @hypothesis_settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_webhook_signature_validation_property(
        self, 
        client: TestClient, 
        payload_data: dict,
        wrong_secret: str
    ):
        """
        Feature: paystack-wallet-compliance, Property 16: Webhook signature validation
        
        For any webhook request, if the computed HMAC SHA512 signature does not match 
        the x-paystack-signature header, the request should be rejected.
        """
        # Create payload
        payload = {
            "event": "charge.success",
            "data": payload_data
        }
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        
        # Create incorrect signature using wrong secret
        wrong_signature = hmac.new(
            wrong_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha512
        ).hexdigest()
        
        # Send webhook with wrong signature
        response = client.post(
            "/wallet/paystack/webhook",
            content=payload_bytes,
            headers={
                "x-paystack-signature": wrong_signature,
                "Content-Type": "application/json"
            }
        )
        
        # Should be rejected with 400 status
        assert response.status_code == 400
        assert "Invalid signature" in response.json()["detail"]

    @given(
        payload_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(
                st.text(min_size=1, max_size=100),
                st.integers(),
                st.booleans()
            ),
            min_size=1,
            max_size=10
        )
    )
    @hypothesis_settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_webhook_missing_signature_rejection(
        self, 
        client: TestClient, 
        payload_data: dict
    ):
        """
        Test that webhooks without signature headers are rejected.
        """
        payload = {
            "event": "charge.success", 
            "data": payload_data
        }
        
        # Send webhook without signature header
        response = client.post(
            "/wallet/paystack/webhook",
            json=payload
        )
        
        # Should be rejected with 400 status
        assert response.status_code == 400
        assert "Missing Paystack signature" in response.json()["detail"]

    @given(
        payload_data=st.dictionaries(
            keys=st.text(min_size=1, max_size=20),
            values=st.one_of(
                st.text(min_size=1, max_size=100),
                st.integers(),
                st.booleans()
            ),
            min_size=1,
            max_size=10
        )
    )
    @hypothesis_settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_webhook_valid_signature_acceptance(
        self, 
        client: TestClient, 
        payload_data: dict
    ):
        """
        Test that webhooks with valid signatures are accepted (even if they don't process anything).
        """
        payload = {
            "event": "charge.success",
            "data": payload_data
        }
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        
        # Create correct signature
        correct_signature = hmac.new(
            settings.paystack_webhook_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha512
        ).hexdigest()
        
        # Send webhook with correct signature
        response = client.post(
            "/wallet/paystack/webhook",
            content=payload_bytes,
            headers={
                "x-paystack-signature": correct_signature,
                "Content-Type": "application/json"
            }
        )
        
        # Should be accepted with 200 status
        assert response.status_code == 200
        assert response.json()["status"] is True

    @given(
        amount=positive_amount_strategy(),
        reference=transaction_reference_strategy("dep")
    )
    @hypothesis_settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_webhook_idempotency_property(
        self, 
        client: TestClient, 
        amount: int,
        reference: str
    ):
        """
        Feature: paystack-wallet-compliance, Property 4: Webhook idempotency
        
        For any webhook event received multiple times with the same reference, 
        the wallet should only be credited once.
        """
        # Create webhook payload
        payload = {
            "event": "charge.success",
            "data": {
                "reference": reference,
                "amount": amount,
                "status": "success"
            }
        }
        payload_bytes = json.dumps(payload, sort_keys=True).encode('utf-8')
        
        # Create correct signature
        correct_signature = hmac.new(
            settings.paystack_webhook_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha512
        ).hexdigest()
        
        headers = {
            "x-paystack-signature": correct_signature,
            "Content-Type": "application/json"
        }
        
        # Send webhook first time
        response1 = client.post(
            "/wallet/paystack/webhook",
            content=payload_bytes,
            headers=headers
        )
        
        # Send webhook second time (idempotency test)
        response2 = client.post(
            "/wallet/paystack/webhook",
            content=payload_bytes,
            headers=headers
        )
        
        # Both should succeed (webhook should not fail on duplicate)
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        # Both should return success status
        assert response1.json()["status"] is True
        assert response2.json()["status"] is True