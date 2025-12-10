"""
Simple tests for Hypothesis data generators without database dependencies.
"""
from hypothesis import given, settings
from datetime import datetime

from tests.generators import (
    email_strategy, wallet_number_strategy, positive_amount_strategy, 
    expiry_duration_strategy, permission_list_strategy
)
from app.models import ApiKeyPermissions


@settings(max_examples=10)
@given(email_strategy())
def test_email_generator(email):
    """Test email generator produces valid emails."""
    assert "@" in email
    assert "." in email
    assert len(email) > 5


@settings(max_examples=10)
@given(wallet_number_strategy())
def test_wallet_number_generator(wallet_number):
    """Test wallet number generator produces 10-digit strings."""
    assert len(wallet_number) == 10
    assert wallet_number.isdigit()


@settings(max_examples=10)
@given(positive_amount_strategy())
def test_positive_amount_generator(amount):
    """Test positive amount generator produces positive integers."""
    assert amount > 0
    assert isinstance(amount, int)


@settings(max_examples=10)
@given(expiry_duration_strategy())
def test_expiry_duration_generator(duration):
    """Test expiry duration generator produces valid durations."""
    assert duration in ["1H", "1D", "1M", "1Y"]


@settings(max_examples=10)
@given(permission_list_strategy())
def test_permission_list_generator(permissions):
    """Test permission list generator produces valid permission lists."""
    assert len(permissions) > 0
    valid_permissions = [p.value for p in ApiKeyPermissions]
    for perm in permissions:
        assert perm in valid_permissions
    # Check uniqueness
    assert len(permissions) == len(set(permissions))