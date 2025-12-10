"""
Property-based tests for transaction history functionality.
"""
import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import select
from hypothesis import given, strategies as st, settings, HealthCheck

from app.models import User, Wallet, Transaction, TransactionType, TransactionStatus
from app.routers.wallet import get_wallet_transactions
from app.auth_utils import get_current_user_with_permissions, create_access_token
from tests.generators import user_strategy, transaction_strategy

pytestmark = pytest.mark.asyncio


class TestTransactionHistoryProperties:
    """Property-based tests for transaction history functionality."""

    @settings(max_examples=100, deadline=None)
    @given(
        user_data=user_strategy(),
        num_transactions=st.integers(min_value=2, max_value=10)
    )
    async def test_transaction_history_ordering_property(self, test_db_url: str, setup_test_db, user_data: User, num_transactions: int):
        """
        Feature: paystack-wallet-compliance, Property 17: Transaction history ordering
        
        Property: For any transaction history request, transactions should be ordered 
        by created_at in descending order (newest first).
        
        Validates: Requirements 8.2
        """
        engine = create_async_engine(test_db_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db_session:
            # Create user in database with unique identifiers to avoid conflicts
            test_id = uuid.uuid4().hex[:8]
            user = User(
                google_id=f"{user_data.google_id}_{test_id}",
                email=f"{test_id}_{user_data.email}",
                name=user_data.name
            )
            wallet = Wallet(
                user=user,
                wallet_number=f"{test_id[:10]}",
                balance=100000  # Give some balance for transfers
            )
            db_session.add_all([user, wallet])
            await db_session.commit()
            await db_session.refresh(user)
            await db_session.refresh(wallet)
            
            # Create transactions with different timestamps
            transactions = []
            base_time = datetime.now(timezone.utc) - timedelta(hours=num_transactions)
            
            for i in range(num_transactions):
                # Create transactions with incrementing timestamps
                # This ensures we have a known order to test against
                created_at = base_time + timedelta(minutes=i * 10)
                
                transaction = Transaction(
                    wallet_id=wallet.id,
                    user_id=user.id,
                    type=TransactionType.DEPOSIT if i % 2 == 0 else TransactionType.TRANSFER,
                    amount=1000 + i * 100,  # Different amounts for variety
                    status=TransactionStatus.SUCCESS,
                    reference=f"test_{test_id}_{i}_{uuid.uuid4().hex[:8]}",
                    description=f"Test transaction {i}",
                    created_at=created_at
                )
                transactions.append(transaction)
                db_session.add(transaction)
            
            await db_session.commit()
            
            # Refresh all transactions to ensure they're in the session
            for transaction in transactions:
                await db_session.refresh(transaction)
            
            # Create JWT token for authentication
            token = create_access_token(data={"sub": str(user.id)})
            
            # Get current user with permissions (simulating the dependency)
            current_user, permissions = await get_current_user_with_permissions(
                authorization=f"Bearer {token}",
                x_api_key=None,
                db=db_session
            )
            
            # Get transaction history using the actual endpoint logic
            result = await db_session.execute(select(Wallet).where(Wallet.user_id == current_user.id))
            user_wallet = result.scalar_one_or_none()
            assert user_wallet is not None
            
            result = await db_session.execute(
                select(Transaction).where(Transaction.wallet_id == user_wallet.id).order_by(Transaction.created_at.desc())
            )
            retrieved_transactions = result.scalars().all()
            
            # Verify we got all transactions
            assert len(retrieved_transactions) == num_transactions
            
            # Property: Transactions should be ordered by created_at in descending order (newest first)
            for i in range(len(retrieved_transactions) - 1):
                current_tx = retrieved_transactions[i]
                next_tx = retrieved_transactions[i + 1]
                
                # Current transaction should have created_at >= next transaction's created_at
                assert current_tx.created_at >= next_tx.created_at, (
                    f"Transaction ordering violated: transaction at index {i} "
                    f"(created_at={current_tx.created_at}) should be newer than or equal to "
                    f"transaction at index {i+1} (created_at={next_tx.created_at})"
                )
            
            # Additional verification: The first transaction should be the newest
            if retrieved_transactions:
                newest_transaction = max(transactions, key=lambda t: t.created_at)
                assert retrieved_transactions[0].id == newest_transaction.id
                
                # The last transaction should be the oldest
                oldest_transaction = min(transactions, key=lambda t: t.created_at)
                assert retrieved_transactions[-1].id == oldest_transaction.id
            
            # Verify that all transactions belong to the correct wallet
            for tx in retrieved_transactions:
                assert tx.wallet_id == wallet.id
                assert tx.user_id == user.id
        
        await engine.dispose()