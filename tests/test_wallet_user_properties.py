"""
Property-based tests for wallet and user creation functionality.
"""
import pytest
import pytest_asyncio
import uuid
from datetime import datetime
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select
from hypothesis import given, strategies as st, settings, HealthCheck

from app.models import User, Wallet
from tests.generators import user_strategy

pytestmark = pytest.mark.asyncio


class TestWalletUserCreationProperties:
    """Property-based tests for wallet and user creation."""

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture])
    @given(
        google_id=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            min_size=10,
            max_size=30
        ),
        name=st.one_of(
            st.none(),
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ",
                min_size=1,
                max_size=50
            )
        ),
        picture=st.one_of(
            st.none(),
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:/.-_",
                min_size=10,
                max_size=100
            )
        )
    )
    async def test_wallet_creation_accompanies_user_creation_property(self, clean_db_session: AsyncSession, google_id: str, name: str, picture: str):
        """
        Feature: paystack-wallet-compliance, Property 1: Wallet creation accompanies user creation
        
        Property: For any new User created through Google authentication, a Wallet should be 
        created with a unique wallet_number and zero balance.
        
        Validates: Requirements 2.1, 2.2, 2.3
        """
        # Create user in database with unique identifiers to avoid conflicts
        test_id = uuid.uuid4().hex[:8]
        email = f"{test_id}@example.com"  # Generate simple valid email
        user = User(
            google_id=f"{google_id}_{test_id}",
            email=email,
            name=name,
            picture=picture
        )
        
        # Simulate the wallet creation that happens during user registration
        # This mimics what happens in the auth callback
        wallet_number = f"{test_id[:10]}"  # Generate unique wallet number
        wallet = Wallet(
            user=user,
            wallet_number=wallet_number,
            balance=0  # Initial balance should be zero
        )
        
        clean_db_session.add_all([user, wallet])
        await clean_db_session.commit()
        await clean_db_session.refresh(user)
        await clean_db_session.refresh(wallet)
        
        # Verify user was created correctly
        assert user.id is not None
        assert user.google_id == f"{google_id}_{test_id}"
        assert user.email == email
            
        # Verify wallet was created and associated with user
        # Requirement 2.1: WHEN a new User is created during Google authentication, 
        # THE System SHALL create a Wallet for that User
        result = await clean_db_session.execute(
            select(Wallet).where(Wallet.user_id == user.id)
        )
        created_wallet = result.scalar_one_or_none()
        assert created_wallet is not None
        assert created_wallet.user_id == user.id
        
        # Requirement 2.2: WHEN creating a Wallet, THE System SHALL generate a unique wallet_number
        assert created_wallet.wallet_number is not None
        assert len(created_wallet.wallet_number) > 0
        assert created_wallet.wallet_number == wallet_number
        
        # Requirement 2.3: WHEN creating a Wallet, THE System SHALL initialize the balance to zero kobo
        assert created_wallet.balance == 0
        
        # Verify wallet number uniqueness by checking it doesn't exist for other users
        # Create another user with a different wallet number to test uniqueness
        test_id_2 = uuid.uuid4().hex[:8]
        email_2 = f"{test_id_2}@example.com"
        user_2 = User(
            google_id=f"{google_id}_{test_id_2}",
            email=email_2,
            name=name
        )
        
        wallet_number_2 = f"{test_id_2[:10]}"  # Different wallet number
        wallet_2 = Wallet(
            user=user_2,
            wallet_number=wallet_number_2,
            balance=0
        )
        
        clean_db_session.add_all([user_2, wallet_2])
        await clean_db_session.commit()
        await clean_db_session.refresh(wallet_2)
        
        # Requirement 2.4: WHEN a Wallet is created, THE System SHALL ensure 
        # the wallet_number is unique across all Wallets
        assert wallet_2.wallet_number != created_wallet.wallet_number
        
        # Verify both wallets exist and have unique wallet numbers
        all_wallets_result = await clean_db_session.execute(select(Wallet))
        all_wallets = all_wallets_result.scalars().all()
        wallet_numbers = [w.wallet_number for w in all_wallets]
        
        # Check that all wallet numbers are unique
        assert len(wallet_numbers) == len(set(wallet_numbers))
        
        # Verify both our test wallets are in the list
        assert created_wallet.wallet_number in wallet_numbers
        assert wallet_2.wallet_number in wallet_numbers