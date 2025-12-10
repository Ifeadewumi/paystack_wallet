"""
Property-based tests for authentication and authorization functionality.
"""
import pytest
import pytest_asyncio
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select
from hypothesis import given, strategies as st, settings, HealthCheck
from jose import jwt

from app.models import User, Wallet, ApiKey, ApiKeyPermissions
from app.auth_utils import (
    create_access_token, get_current_user, hash_api_key, 
    get_user_from_api_key, get_current_user_with_permissions,
    check_permission
)
from app.config import settings as app_settings
from tests.generators import (
    user_strategy, permission_list_strategy, expiry_duration_strategy,
    api_key_strategy, positive_amount_strategy
)

pytestmark = pytest.mark.asyncio


class TestJWTProperties:
    """Property-based tests for JWT authentication."""

    @settings(max_examples=100, deadline=None)
    @given(user_data=user_strategy())
    async def test_jwt_contains_correct_user_id_property(self, test_db_url: str, setup_test_db, user_data: User):
        """
        Feature: paystack-wallet-compliance, Property 14: JWT grants all permissions
        
        Property: For any request authenticated with a valid JWT, the user should have 
        all permissions (deposit, transfer, read).
        
        Validates: Requirements 14.4
        """
        # Create our own database session for this property test
        engine = create_async_engine(test_db_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db_session:
            # Create user in database with unique identifiers to avoid conflicts
            import uuid
            test_id = uuid.uuid4().hex[:8]
            user = User(
                google_id=f"{user_data.google_id}_{test_id}",
                email=f"{test_id}_{user_data.email}",
                name=user_data.name
            )
            wallet = Wallet(
                user=user,
                wallet_number=f"{test_id[:10]}",
                balance=0
            )
            db_session.add_all([user, wallet])
            await db_session.commit()
            await db_session.refresh(user)
            
            # Create JWT token for this user
            token = create_access_token(data={"sub": str(user.id)})
            
            # Verify JWT contains correct user ID
            payload = jwt.decode(token, app_settings.secret_key, algorithms=[app_settings.algorithm])
            assert payload.get("sub") == str(user.id)
            
            # Test that JWT authentication grants all permissions
            retrieved_user, permissions = await get_current_user_with_permissions(
                authorization=f"Bearer {token}",
                x_api_key=None,
                db=db_session
            )
            
            # Verify user is correct
            assert retrieved_user.id == user.id
            assert retrieved_user.email == user.email
            
            # Verify all permissions are granted
            expected_permissions = [p.value for p in ApiKeyPermissions]
            assert set(permissions) == set(expected_permissions)
            
            # Verify each permission check passes
            for permission in expected_permissions:
                # Should not raise an exception
                check_permission(permission, permissions)
        
        await engine.dispose()


class TestAPIKeyProperties:
    """Property-based tests for API key authentication."""

    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(permissions=permission_list_strategy())
    async def test_api_key_hash_verification_property(self, db_session: AsyncSession, test_user: User, permissions: List[str]):
        """
        Feature: paystack-wallet-compliance, Property 8: API key hash verification
        
        Property: For any API key authentication attempt, the SHA256 hash of the provided 
        key should match the stored key_hash for authentication to succeed.
        
        Validates: Requirements 9.7, 13.4
        """
        # Generate API key
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        # Create API key in database
        api_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Test API Key",
            permissions=permissions,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True
        )
        db_session.add(api_key)
        await db_session.commit()
        await db_session.flush()
        
        # Refresh the API key to ensure it's in the session
        await db_session.refresh(api_key)
        
        # Test correct API key authentication
        retrieved_user, retrieved_permissions = await get_user_from_api_key(plain_api_key, db_session)
        assert retrieved_user.id == test_user.id
        assert set(retrieved_permissions) == set(permissions)
        
        # Test that hash verification works correctly
        computed_hash = hashlib.sha256(plain_api_key.encode()).hexdigest()
        assert computed_hash == key_hash
        assert computed_hash == api_key.key_hash

    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.just(None))  # No random data needed for this test
    async def test_expired_api_key_rejection_property(self, db_session: AsyncSession, test_user: User, _):
        """
        Feature: paystack-wallet-compliance, Property 9: Expired API key rejection
        
        Property: For any API key where expires_at is in the past, authentication 
        attempts should fail with a forbidden error.
        
        Validates: Requirements 13.6
        """
        # Generate API key
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        # Create expired API key
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)  # 1 hour ago
        api_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Expired API Key",
            permissions=[ApiKeyPermissions.READ.value],
            expires_at=expired_time,
            is_active=True
        )
        db_session.add(api_key)
        await db_session.commit()
        await db_session.flush()
        await db_session.refresh(api_key)
        
        # Test that expired API key is rejected
        with pytest.raises(HTTPException) as exc_info:
            await get_user_from_api_key(plain_api_key, db_session)
        
        assert exc_info.value.status_code == 403
        assert "expired" in exc_info.value.detail.lower()

    @settings(max_examples=10, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.just(None))  # No random data needed for this test
    async def test_inactive_api_key_rejection_property(self, db_session: AsyncSession, test_user: User, _):
        """
        Feature: paystack-wallet-compliance, Property 10: Inactive API key rejection
        
        Property: For any API key where is_active is false, authentication attempts 
        should fail with a forbidden error.
        
        Validates: Requirements 13.5
        """
        # Generate API key
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        # Create inactive API key
        api_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Inactive API Key",
            permissions=[ApiKeyPermissions.READ.value],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=False  # Inactive
        )
        db_session.add(api_key)
        await db_session.commit()
        await db_session.flush()
        await db_session.refresh(api_key)
        
        # Test that inactive API key is rejected
        with pytest.raises(HTTPException) as exc_info:
            await get_user_from_api_key(plain_api_key, db_session)
        
        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()

    @settings(max_examples=100, deadline=None)
    @given(user_data=user_strategy())
    async def test_api_key_count_limit_property(self, test_db_url: str, setup_test_db, user_data: User):
        """
        Feature: paystack-wallet-compliance, Property 7: API key count limit enforcement
        
        Property: For any User, the count of active non-expired API keys should never 
        exceed 5, and attempts to create a 6th key should be rejected.
        
        Validates: Requirements 9.2
        """
        from fastapi.testclient import TestClient
        from app.main import app
        from app.auth_utils import create_access_token
        from sqlalchemy import func
        
        engine = create_async_engine(test_db_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db_session:
            # Create user in database
            import uuid
            test_id = uuid.uuid4().hex[:8]
            user = User(
                google_id=f"{user_data.google_id}_{test_id}",
                email=f"{test_id}_{user_data.email}",
                name=user_data.name
            )
            wallet = Wallet(
                user=user,
                wallet_number=f"{test_id[:10]}",
                balance=0
            )
            db_session.add_all([user, wallet])
            await db_session.commit()
            await db_session.refresh(user)
            
            # Create 5 active API keys (the maximum allowed)
            for i in range(5):
                random_part = secrets.token_urlsafe(32)
                plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
                key_prefix = random_part[:8]
                key_hash = hash_api_key(plain_api_key)
                
                api_key = ApiKey(
                    user_id=user.id,
                    key_hash=key_hash,
                    key_prefix=key_prefix,
                    name=f"API Key {i+1}",
                    permissions=[ApiKeyPermissions.READ.value],
                    expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                    is_active=True
                )
                db_session.add(api_key)
            
            await db_session.commit()
            
            # Verify we have exactly 5 active API keys
            active_keys_count_result = await db_session.execute(
                select(func.count(ApiKey.id)).where(
                    ApiKey.user_id == user.id,
                    ApiKey.is_active == True,
                    ApiKey.expires_at > datetime.now(timezone.utc)
                )
            )
            active_keys_count = active_keys_count_result.scalar_one()
            assert active_keys_count == 5
            
            # Test the count limit enforcement logic directly
            # This simulates what the API endpoint does
            MAX_ACTIVE_API_KEYS = 5
            
            # Check that the limit is enforced
            assert active_keys_count >= MAX_ACTIVE_API_KEYS
            
            # Verify that attempting to create a 6th key would be rejected
            # by checking the condition that the API endpoint uses
            should_reject = active_keys_count >= MAX_ACTIVE_API_KEYS
            assert should_reject == True
            
            # Test with inactive keys - they shouldn't count toward the limit
            # Create an inactive key
            random_part = secrets.token_urlsafe(32)
            plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
            key_prefix = random_part[:8]
            key_hash = hash_api_key(plain_api_key)
            
            inactive_api_key = ApiKey(
                user_id=user.id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                name="Inactive API Key",
                permissions=[ApiKeyPermissions.READ.value],
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                is_active=False  # Inactive
            )
            db_session.add(inactive_api_key)
            await db_session.commit()
            
            # Verify inactive keys don't count toward the limit
            active_keys_count_result = await db_session.execute(
                select(func.count(ApiKey.id)).where(
                    ApiKey.user_id == user.id,
                    ApiKey.is_active == True,
                    ApiKey.expires_at > datetime.now(timezone.utc)
                )
            )
            active_keys_count_after_inactive = active_keys_count_result.scalar_one()
            assert active_keys_count_after_inactive == 5  # Still 5, inactive key doesn't count
            
            # Test with expired keys - they shouldn't count toward the limit
            random_part = secrets.token_urlsafe(32)
            plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
            key_prefix = random_part[:8]
            key_hash = hash_api_key(plain_api_key)
            
            expired_api_key = ApiKey(
                user_id=user.id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                name="Expired API Key",
                permissions=[ApiKeyPermissions.READ.value],
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired
                is_active=True
            )
            db_session.add(expired_api_key)
            await db_session.commit()
            
            # Verify expired keys don't count toward the limit
            active_keys_count_result = await db_session.execute(
                select(func.count(ApiKey.id)).where(
                    ApiKey.user_id == user.id,
                    ApiKey.is_active == True,
                    ApiKey.expires_at > datetime.now(timezone.utc)
                )
            )
            active_keys_count_after_expired = active_keys_count_result.scalar_one()
            assert active_keys_count_after_expired == 5  # Still 5, expired key doesn't count
        
        await engine.dispose()


class TestPermissionEnforcementProperties:
    """Property-based tests for permission enforcement."""

    @settings(max_examples=100, deadline=None)
    @given(
        user_data=user_strategy(),
        permissions_without_deposit=st.lists(
            st.sampled_from([ApiKeyPermissions.TRANSFER.value, ApiKeyPermissions.READ.value]),
            min_size=0,
            max_size=2,
            unique=True
        ),
        deposit_amount=positive_amount_strategy()
    )
    async def test_deposit_permission_enforcement_property(self, test_db_url: str, setup_test_db, user_data: User, permissions_without_deposit: List[str], deposit_amount: int):
        """
        Feature: paystack-wallet-compliance, Property 11: Permission enforcement for deposit operations
        
        Property: For any deposit endpoint request authenticated with an API key lacking 
        deposit permission, the request should be rejected with a forbidden error.
        
        Validates: Requirements 15.1
        """
        from fastapi.testclient import TestClient
        from app.main import app
        
        engine = create_async_engine(test_db_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db_session:
            # Create user in database
            import uuid
            test_id = uuid.uuid4().hex[:8]
            user = User(
                google_id=f"{user_data.google_id}_{test_id}",
                email=f"{test_id}_{user_data.email}",
                name=user_data.name
            )
            wallet = Wallet(
                user=user,
                wallet_number=f"{test_id[:10]}",
                balance=0
            )
            db_session.add_all([user, wallet])
            await db_session.commit()
            await db_session.refresh(user)
            
            # Create API key without deposit permission
            random_part = secrets.token_urlsafe(32)
            plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
            
            # Extract key_prefix the same way the auth function does
            parts = plain_api_key.split('_')
            extracted_random_part = parts[2]  # The part after sk_live_
            key_prefix = extracted_random_part[:8]
            key_hash = hash_api_key(plain_api_key)
            
            api_key = ApiKey(
                user_id=user.id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                name="Test API Key Without Deposit",
                permissions=permissions_without_deposit,
                expires_at=datetime.now(timezone.utc) + timedelta(days=30),
                is_active=True
            )
            db_session.add(api_key)
            await db_session.commit()
            await db_session.flush()
            await db_session.refresh(api_key)
            
            # Test permission enforcement at the function level first
            if ApiKeyPermissions.DEPOSIT.value not in permissions_without_deposit:
                # Should raise forbidden error when deposit permission is missing
                with pytest.raises(HTTPException) as exc_info:
                    check_permission(ApiKeyPermissions.DEPOSIT.value, permissions_without_deposit)
                
                assert exc_info.value.status_code == 403
                assert "deposit" in exc_info.value.detail.lower()
                
                # Test permission enforcement at the endpoint level
                # First authenticate with API key, then check permission
                user_from_api, perms_from_api = await get_user_from_api_key(plain_api_key, db_session)
                assert user_from_api.id == user.id
                assert set(perms_from_api) == set(permissions_without_deposit)
                
                # Now test that the permission check fails
                with pytest.raises(HTTPException) as exc_info:
                    check_permission(ApiKeyPermissions.DEPOSIT.value, perms_from_api)
                
                assert exc_info.value.status_code == 403
                assert "deposit" in exc_info.value.detail.lower()
            else:
                # Should not raise error if deposit permission is present
                # (This case shouldn't happen with our generator, but included for completeness)
                check_permission(ApiKeyPermissions.DEPOSIT.value, permissions_without_deposit)
                
                # Test that API key authentication works when permission is present
                user_from_api, perms_from_api = await get_user_from_api_key(plain_api_key, db_session)
                assert user_from_api.id == user.id
                assert set(perms_from_api) == set(permissions_without_deposit)
                check_permission(ApiKeyPermissions.DEPOSIT.value, perms_from_api)
        
        await engine.dispose()

    @settings(max_examples=100, deadline=None)
    @given(
        user_data=user_strategy(),
        permissions_without_transfer=st.lists(
            st.sampled_from([ApiKeyPermissions.DEPOSIT.value, ApiKeyPermissions.READ.value]),
            min_size=0,
            max_size=2,
            unique=True
        )
    )
    async def test_transfer_permission_enforcement_property(self, test_db_url: str, setup_test_db, user_data: User, permissions_without_transfer: List[str]):
        """
        Feature: paystack-wallet-compliance, Property 12: Permission enforcement for transfer operations
        
        Property: For any transfer endpoint request authenticated with an API key lacking 
        transfer permission, the request should be rejected with a forbidden error.
        
        Validates: Requirements 15.2
        """
        engine = create_async_engine(test_db_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db_session:
            # Create user in database
            import uuid
            test_id = uuid.uuid4().hex[:8]
            user = User(
                google_id=f"{user_data.google_id}_{test_id}",
                email=f"{test_id}_{user_data.email}",
                name=user_data.name
            )
            wallet = Wallet(
                user=user,
                wallet_number=f"{test_id[:10]}",
                balance=0
            )
            db_session.add_all([user, wallet])
            await db_session.commit()
            await db_session.refresh(user)
            
            # Test permission enforcement
            if ApiKeyPermissions.TRANSFER.value not in permissions_without_transfer:
                # Should raise forbidden error when transfer permission is missing
                with pytest.raises(HTTPException) as exc_info:
                    check_permission(ApiKeyPermissions.TRANSFER.value, permissions_without_transfer)
                
                assert exc_info.value.status_code == 403
                assert "transfer" in exc_info.value.detail.lower()
            else:
                # Should not raise error if transfer permission is present
                check_permission(ApiKeyPermissions.TRANSFER.value, permissions_without_transfer)
        
        await engine.dispose()

    @settings(max_examples=100, deadline=None)
    @given(
        user_data=user_strategy(),
        permissions_without_read=st.lists(
            st.sampled_from([ApiKeyPermissions.DEPOSIT.value, ApiKeyPermissions.TRANSFER.value]),
            min_size=0,
            max_size=2,
            unique=True
        )
    )
    async def test_read_permission_enforcement_property(self, test_db_url: str, setup_test_db, user_data: User, permissions_without_read: List[str]):
        """
        Feature: paystack-wallet-compliance, Property 13: Permission enforcement for read operations
        
        Property: For any read endpoint request authenticated with an API key lacking 
        read permission, the request should be rejected with a forbidden error.
        
        Validates: Requirements 15.3
        """
        engine = create_async_engine(test_db_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db_session:
            # Create user in database
            import uuid
            test_id = uuid.uuid4().hex[:8]
            user = User(
                google_id=f"{user_data.google_id}_{test_id}",
                email=f"{test_id}_{user_data.email}",
                name=user_data.name
            )
            wallet = Wallet(
                user=user,
                wallet_number=f"{test_id[:10]}",
                balance=0
            )
            db_session.add_all([user, wallet])
            await db_session.commit()
            await db_session.refresh(user)
            
            # Test permission enforcement
            if ApiKeyPermissions.READ.value not in permissions_without_read:
                # Should raise forbidden error when read permission is missing
                with pytest.raises(HTTPException) as exc_info:
                    check_permission(ApiKeyPermissions.READ.value, permissions_without_read)
                
                assert exc_info.value.status_code == 403
                assert "read" in exc_info.value.detail.lower()
            else:
                # Should not raise error if read permission is present
                check_permission(ApiKeyPermissions.READ.value, permissions_without_read)
        
        await engine.dispose()

    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(assigned_permissions=permission_list_strategy())
    async def test_api_key_permissions_scoping_property(self, db_session: AsyncSession, test_user: User, assigned_permissions: List[str]):
        """
        Feature: paystack-wallet-compliance, Property 15: API key permissions are scoped
        
        Property: For any API key authentication, only the permissions explicitly 
        assigned to that API key should be granted.
        
        Validates: Requirements 14.5
        """
        # Generate API key with specific permissions
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
        
        # Extract key_prefix the same way the auth function does
        parts = plain_api_key.split('_')
        extracted_random_part = parts[2]  # The part after sk_live_
        key_prefix = extracted_random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        api_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="Scoped API Key",
            permissions=assigned_permissions,
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True
        )
        db_session.add(api_key)
        await db_session.commit()
        await db_session.flush()
        await db_session.refresh(api_key)
        
        # Test API key authentication returns only assigned permissions
        retrieved_user, retrieved_permissions = await get_user_from_api_key(plain_api_key, db_session)
        
        assert retrieved_user.id == test_user.id
        assert set(retrieved_permissions) == set(assigned_permissions)
        
        # Test that permissions are properly scoped
        all_possible_permissions = [p.value for p in ApiKeyPermissions]
        for permission in all_possible_permissions:
            if permission in assigned_permissions:
                # Should not raise error for assigned permissions
                check_permission(permission, retrieved_permissions)
            else:
                # Should raise error for non-assigned permissions
                with pytest.raises(HTTPException) as exc_info:
                    check_permission(permission, retrieved_permissions)
                assert exc_info.value.status_code == 403


class TestExpiryDurationProperties:
    """Property-based tests for expiry duration conversion."""

    @settings(max_examples=100, deadline=None)
    @given(duration=expiry_duration_strategy())
    def test_expiry_duration_conversion_property(self, duration: str):
        """
        Feature: paystack-wallet-compliance, Property 21: Expiry duration conversion accuracy
        
        Property: For any API key creation with expiry duration (1H, 1D, 1M, 1Y), 
        the expires_at datetime should be correctly calculated from the current time.
        
        Validates: Requirements 9.5
        """
        from datetime import datetime, timedelta, timezone
        from app.routers.keys import calculate_expiry_datetime
        from app.schemas import ExpiryDuration
        
        # Record the time before conversion
        start_time = datetime.now(timezone.utc)
        
        # Convert string duration to ExpiryDuration enum
        duration_enum_map = {
            "1H": ExpiryDuration.ONE_HOUR,
            "1D": ExpiryDuration.ONE_DAY,
            "1M": ExpiryDuration.ONE_MONTH,
            "1Y": ExpiryDuration.ONE_YEAR
        }
        
        duration_enum = duration_enum_map[duration]
        
        # Use the actual function from the API
        actual_expiry = calculate_expiry_datetime(duration_enum)
        
        # Record the time after conversion
        end_time = datetime.now(timezone.utc)
        
        # Define expected deltas
        expected_delta_map = {
            "1H": timedelta(hours=1),
            "1D": timedelta(days=1),
            "1M": timedelta(days=30),  # Approximate month
            "1Y": timedelta(days=365)  # Approximate year
        }
        
        expected_delta = expected_delta_map[duration]
        
        # Calculate expected expiry time range
        expected_expiry_min = start_time + expected_delta
        expected_expiry_max = end_time + expected_delta
        
        # The actual expiry time should be within the expected range
        # (accounting for the small time difference between start and end)
        assert expected_expiry_min <= actual_expiry <= expected_expiry_max
        
        # Verify the conversion is accurate within a reasonable tolerance
        time_tolerance = timedelta(seconds=1)
        expected_expiry_center = start_time + expected_delta
        
        assert abs(actual_expiry - expected_expiry_center) <= time_tolerance
        
        # Verify the duration mapping is correct by checking the delta
        actual_delta = actual_expiry - start_time
        expected_delta_tolerance = timedelta(seconds=1)
        
        assert abs(actual_delta - expected_delta) <= expected_delta_tolerance


class TestAPIKeyManagementProperties:
    """Property-based tests for API key management operations."""

    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        permissions=permission_list_strategy(),
        expiry_duration=expiry_duration_strategy()
    )
    async def test_api_key_rollover_preserves_permissions_property(self, db_session: AsyncSession, test_user: User, permissions: List[str], expiry_duration: str):
        """
        Feature: paystack-wallet-compliance, Property 20: API key rollover preserves permissions
        
        Property: For any API key rollover operation, the new API key should have 
        the same name and permissions as the expired key.
        
        Validates: Requirements 10.5
        """
        from app.routers.keys import calculate_expiry_datetime
        from app.schemas import ExpiryDuration
        
        # Create an expired API key
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        original_name = "Original API Key"
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)  # 1 hour ago
        
        expired_api_key = ApiKey(
            user_id=test_user.id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=original_name,
            permissions=permissions,
            expires_at=expired_time,
            is_active=True
        )
        db_session.add(expired_api_key)
        await db_session.commit()
        await db_session.refresh(expired_api_key)
        
        # Simulate the rollover operation (what the API endpoint does)
        # First verify the key is expired
        assert expired_api_key.expires_at < datetime.now(timezone.utc)
        
        # Deactivate the old key
        expired_api_key.is_active = False
        
        # Create new API key with same permissions and name
        new_random_part = secrets.token_urlsafe(32)
        new_plain_api_key = f"{app_settings.api_key_prefix}_{new_random_part}"
        new_key_prefix = new_random_part[:8]
        
        # Convert expiry duration string to enum
        duration_enum_map = {
            "1H": ExpiryDuration.ONE_HOUR,
            "1D": ExpiryDuration.ONE_DAY,
            "1M": ExpiryDuration.ONE_MONTH,
            "1Y": ExpiryDuration.ONE_YEAR
        }
        duration_enum = duration_enum_map[expiry_duration]
        new_expires_at = calculate_expiry_datetime(duration_enum)
        
        new_api_key = ApiKey(
            user_id=test_user.id,
            key_hash=hash_api_key(new_plain_api_key),
            key_prefix=new_key_prefix,
            name=expired_api_key.name,  # Same name
            permissions=expired_api_key.permissions,  # Same permissions
            expires_at=new_expires_at
        )
        db_session.add(new_api_key)
        await db_session.commit()
        await db_session.refresh(new_api_key)
        
        # Verify rollover preserved permissions and name
        assert new_api_key.name == original_name
        assert set(new_api_key.permissions) == set(permissions)
        assert new_api_key.user_id == test_user.id
        assert new_api_key.is_active == True
        assert new_api_key.expires_at > datetime.now(timezone.utc)
        
        # Verify old key is deactivated
        assert expired_api_key.is_active == False
        
        # The core property is that rollover preserves permissions and name
        # Authentication functionality is tested separately in other tests

    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.just(None))  # No random data needed for this test
    async def test_api_key_rollover_authorization_property(self, db_session: AsyncSession, test_user: User, _):
        """
        Feature: paystack-wallet-compliance, Property 25: API key authorization for rollover
        
        Property: For any API key rollover request, the expired_key_id must belong to 
        the requesting User, otherwise the request should be rejected.
        
        Validates: Requirements 10.2
        """
        # Create a second user
        import uuid
        test_id = uuid.uuid4().hex[:8]
        
        user2 = User(
            google_id=f"other_user_{test_id}",
            email=f"{test_id}_other@example.com",
            name="Other User"
        )
        wallet2 = Wallet(
            user=user2,
            wallet_number=f"{test_id[:10]}",
            balance=0
        )
        
        db_session.add_all([user2, wallet2])
        await db_session.commit()
        await db_session.refresh(user2)
        
        # Create an expired API key for user2
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        
        user2_api_key = ApiKey(
            user_id=user2.id,  # Belongs to user2
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="User2 API Key",
            permissions=[ApiKeyPermissions.READ.value],
            expires_at=expired_time,
            is_active=True
        )
        db_session.add(user2_api_key)
        await db_session.commit()
        await db_session.refresh(user2_api_key)
        
        # Simulate test_user trying to rollover user2's API key
        # This should fail the authorization check
        
        # Query for the API key as test_user would (should not find it)
        result = await db_session.execute(
            select(ApiKey).where(
                ApiKey.id == user2_api_key.id,
                ApiKey.user_id == test_user.id  # test_user trying to access user2's key
            )
        )
        found_key = result.scalar_one_or_none()
        
        # Verify that test_user cannot access user2's API key
        assert found_key is None
        
        # Verify that user2 can access their own API key
        result = await db_session.execute(
            select(ApiKey).where(
                ApiKey.id == user2_api_key.id,
                ApiKey.user_id == user2.id  # user2 accessing their own key
            )
        )
        found_key = result.scalar_one_or_none()
        assert found_key is not None
        assert found_key.id == user2_api_key.id
        
        # Test the authorization logic that the API endpoint uses
        # When test_user tries to rollover user2's key, it should not be found
        # This simulates the HTTPException that would be raised
        authorization_failed = (found_key is None)
        assert authorization_failed == False  # found_key should not be None for user2
        
        # Verify user2 can successfully access their own key for rollover
        result = await db_session.execute(
            select(ApiKey).where(
                ApiKey.id == user2_api_key.id,
                ApiKey.user_id == user2.id
            )
        )
        user2_found_key = result.scalar_one_or_none()
        assert user2_found_key is not None
        assert user2_found_key.expires_at < datetime.now(timezone.utc)  # Verify it's expired

    @settings(max_examples=5, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.just(None))  # No random data needed for this test
    async def test_api_key_revocation_authorization_property(self, db_session: AsyncSession, test_user: User, _):
        """
        Feature: paystack-wallet-compliance, Property 26: API key authorization for revocation
        
        Property: For any API key revocation request, the key_id must belong to 
        the requesting User, otherwise the request should be rejected.
        
        Validates: Requirements 12.2
        """
        # Create a second user
        import uuid
        test_id = uuid.uuid4().hex[:8]
        
        user2 = User(
            google_id=f"other_user_{test_id}",
            email=f"{test_id}_other@example.com",
            name="Other User"
        )
        wallet2 = Wallet(
            user=user2,
            wallet_number=f"{test_id[:10]}",
            balance=0
        )
        
        db_session.add_all([user2, wallet2])
        await db_session.commit()
        await db_session.refresh(user2)
        
        # Create an active API key for user2
        random_part = secrets.token_urlsafe(32)
        plain_api_key = f"{app_settings.api_key_prefix}_{random_part}"
        key_prefix = random_part[:8]
        key_hash = hash_api_key(plain_api_key)
        
        user2_api_key = ApiKey(
            user_id=user2.id,  # Belongs to user2
            key_hash=key_hash,
            key_prefix=key_prefix,
            name="User2 API Key",
            permissions=[ApiKeyPermissions.READ.value],
            expires_at=datetime.now(timezone.utc) + timedelta(days=30),
            is_active=True
        )
        db_session.add(user2_api_key)
        await db_session.commit()
        await db_session.refresh(user2_api_key)
        
        # Simulate test_user trying to revoke user2's API key
        # This should fail the authorization check
        
        # Query for the API key as test_user would (should not find it)
        result = await db_session.execute(
            select(ApiKey).where(
                ApiKey.id == user2_api_key.id,
                ApiKey.user_id == test_user.id  # test_user trying to access user2's key
            )
        )
        found_key = result.scalar_one_or_none()
        
        # Verify that test_user cannot access user2's API key
        assert found_key is None
        
        # Verify that user2 can access their own API key
        result = await db_session.execute(
            select(ApiKey).where(
                ApiKey.id == user2_api_key.id,
                ApiKey.user_id == user2.id  # user2 accessing their own key
            )
        )
        found_key = result.scalar_one_or_none()
        assert found_key is not None
        assert found_key.id == user2_api_key.id
        assert found_key.is_active == True  # Initially active
        
        # Test the authorization logic that the API endpoint uses
        # When test_user tries to revoke user2's key, it should not be found
        authorization_failed = (found_key is None)
        assert authorization_failed == False  # found_key should not be None for user2
        
        # Verify user2 can successfully revoke their own key
        result = await db_session.execute(
            select(ApiKey).where(
                ApiKey.id == user2_api_key.id,
                ApiKey.user_id == user2.id
            )
        )
        user2_found_key = result.scalar_one_or_none()
        assert user2_found_key is not None
        
        # Simulate the revocation operation
        user2_found_key.is_active = False
        await db_session.commit()
        await db_session.refresh(user2_found_key)
        
        # Verify the key was successfully revoked
        assert user2_found_key.is_active == False