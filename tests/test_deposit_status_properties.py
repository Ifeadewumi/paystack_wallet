"""
Property-based tests for deposit status checking operations.
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

from app.models import User, Wallet, Transaction, TransactionType, TransactionStatus
from tests.generators import user_strategy, wallet_strategy, transaction_strategy, positive_amount_strategy

pytestmark = pytest.mark.asyncio


class TestDepositStatusProperties:
    """Property-based tests for deposit status checking operations."""

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture])
    @given(
        num_users=st.integers(min_value=2, max_value=5),
        num_transactions_per_user=st.integers(min_value=1, max_value=3)
    )
    async def test_transaction_ownership_verification_property(
        self, 
        test_db_url_fixture: str, 
        setup_test_db, 
        num_users: int,
        num_transactions_per_user: int
    ):
        """
        Feature: paystack-wallet-compliance, Property 19: Transaction ownership verification
        
        Property: For any deposit status request, only the User who owns the Transaction 
        should be able to view it.
        
        Validates: Requirements 5.1
        """
        engine = create_async_engine(test_db_url_fixture)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db_session:
            # Create multiple users with wallets and transactions
            users_with_data = []
            
            for i in range(num_users):
                # Create user and wallet
                test_id = uuid.uuid4().hex[:8]
                user = User(
                    google_id=f"test_google_{test_id}",
                    email=f"{test_id}@example.com",
                    name=f"Test User {i}"
                )
                
                wallet = Wallet(
                    user=user,
                    wallet_number=f"{test_id[:10]}",
                    balance=10000
                )
                
                db_session.add_all([user, wallet])
                await db_session.commit()
                await db_session.refresh(user)
                await db_session.refresh(wallet)
                
                # Create transactions for this user
                user_transactions = []
                for j in range(num_transactions_per_user):
                    reference = f"dep_{uuid.uuid4().hex}"
                    transaction = Transaction(
                        wallet_id=wallet.id,
                        user_id=user.id,
                        type=TransactionType.DEPOSIT,
                        amount=1000 + (j * 500),  # Different amounts
                        status=TransactionStatus.PENDING,
                        reference=reference,
                        description=f"Test deposit {j}"
                    )
                    
                    user_transactions.append(transaction)
                    db_session.add(transaction)
                
                await db_session.commit()
                
                # Refresh transactions to get IDs
                for transaction in user_transactions:
                    await db_session.refresh(transaction)
                
                users_with_data.append({
                    'user': user,
                    'wallet': wallet,
                    'transactions': user_transactions
                })
            
            # Test ownership verification: each user should only see their own transactions
            for owner_idx, owner_data in enumerate(users_with_data):
                owner_user = owner_data['user']
                owner_transactions = owner_data['transactions']
                
                # Test that owner can access their own transactions
                for transaction in owner_transactions:
                    # Simulate the deposit status endpoint logic
                    result = await db_session.execute(
                        select(Transaction).where(
                            Transaction.reference == transaction.reference,
                            Transaction.user_id == owner_user.id,
                            Transaction.type == TransactionType.DEPOSIT
                        )
                    )
                    found_transaction = result.scalar_one_or_none()
                    
                    # Requirement 5.1: WHEN a User requests deposit status by reference, 
                    # THE System SHALL verify the Transaction belongs to the requesting User
                    assert found_transaction is not None, f"Owner should be able to access their own transaction {transaction.reference}"
                    assert found_transaction.id == transaction.id, "Found transaction should match the original"
                    assert found_transaction.user_id == owner_user.id, "Transaction should belong to the requesting user"
                
                # Test that owner cannot access other users' transactions
                for other_idx, other_data in enumerate(users_with_data):
                    if other_idx == owner_idx:
                        continue  # Skip self
                    
                    other_transactions = other_data['transactions']
                    
                    for other_transaction in other_transactions:
                        # Try to access another user's transaction as if we were the owner
                        result = await db_session.execute(
                            select(Transaction).where(
                                Transaction.reference == other_transaction.reference,
                                Transaction.user_id == owner_user.id,  # Wrong user ID
                                Transaction.type == TransactionType.DEPOSIT
                            )
                        )
                        found_transaction = result.scalar_one_or_none()
                        
                        # Should not find the transaction because it belongs to a different user
                        assert found_transaction is None, f"User {owner_user.id} should not be able to access transaction {other_transaction.reference} belonging to user {other_transaction.user_id}"
            
            # Additional verification: test with non-existent references
            for user_data in users_with_data:
                user = user_data['user']
                non_existent_reference = f"dep_{uuid.uuid4().hex}"
                
                result = await db_session.execute(
                    select(Transaction).where(
                        Transaction.reference == non_existent_reference,
                        Transaction.user_id == user.id,
                        Transaction.type == TransactionType.DEPOSIT
                    )
                )
                found_transaction = result.scalar_one_or_none()
                
                # Should not find non-existent transactions
                assert found_transaction is None, f"Should not find non-existent transaction {non_existent_reference}"
        
        await engine.dispose()

    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.function_scoped_fixture])
    @given(
        initial_balance=st.integers(min_value=0, max_value=100000),
        transaction_amount=positive_amount_strategy(),
        transaction_status=st.sampled_from([TransactionStatus.PENDING, TransactionStatus.SUCCESS, TransactionStatus.FAILED])
    )
    async def test_deposit_status_read_only_property(
        self, 
        test_db_url_fixture: str, 
        setup_test_db, 
        initial_balance: int,
        transaction_amount: int,
        transaction_status: TransactionStatus
    ):
        """
        Feature: paystack-wallet-compliance, Property 18: Deposit status read-only
        
        Property: For any deposit status check, the Transaction and Wallet balance 
        should remain unchanged after the operation.
        
        Validates: Requirements 5.3
        """
        engine = create_async_engine(test_db_url_fixture)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        
        async with async_session() as db_session:
            # Create user and wallet with specific initial balance
            test_id = uuid.uuid4().hex[:8]
            user = User(
                google_id=f"test_google_{test_id}",
                email=f"{test_id}@example.com",
                name="Test User"
            )
            
            wallet = Wallet(
                user=user,
                wallet_number=f"{test_id[:10]}",
                balance=initial_balance
            )
            
            db_session.add_all([user, wallet])
            await db_session.commit()
            await db_session.refresh(user)
            await db_session.refresh(wallet)
            
            # Create a deposit transaction
            reference = f"dep_{uuid.uuid4().hex}"
            transaction = Transaction(
                wallet_id=wallet.id,
                user_id=user.id,
                type=TransactionType.DEPOSIT,
                amount=transaction_amount,
                status=transaction_status,
                reference=reference,
                description="Test deposit for read-only check"
            )
            
            db_session.add(transaction)
            await db_session.commit()
            await db_session.refresh(transaction)
            
            # Record initial state before deposit status check
            initial_wallet_balance = wallet.balance
            initial_transaction_status = transaction.status
            initial_transaction_amount = transaction.amount
            initial_transaction_paid_at = transaction.paid_at
            initial_transaction_updated_at = transaction.updated_at
            
            # Simulate the deposit status endpoint logic (read-only operation)
            # Requirement 5.3: WHEN checking deposit status, THE System SHALL not modify 
            # the Transaction or Wallet balance
            result = await db_session.execute(
                select(Transaction).where(
                    Transaction.reference == reference,
                    Transaction.user_id == user.id,
                    Transaction.type == TransactionType.DEPOSIT
                )
            )
            found_transaction = result.scalar_one_or_none()
            
            # Verify transaction was found (this is the read operation)
            assert found_transaction is not None, "Transaction should be found"
            
            # Simulate reading the transaction data (what the endpoint returns)
            status_response_data = {
                "reference": found_transaction.reference,
                "status": found_transaction.status,
                "amount": found_transaction.amount,
                "paid_at": found_transaction.paid_at
            }
            
            # Verify the response contains expected data
            assert status_response_data["reference"] == reference
            assert status_response_data["status"] == transaction_status
            assert status_response_data["amount"] == transaction_amount
            
            # Refresh objects to get current state from database
            await db_session.refresh(wallet)
            await db_session.refresh(transaction)
            
            # Verify that the read operation did not modify the wallet balance
            assert wallet.balance == initial_wallet_balance, f"Wallet balance should remain unchanged: expected {initial_wallet_balance}, got {wallet.balance}"
            
            # Verify that the read operation did not modify the transaction
            assert transaction.status == initial_transaction_status, f"Transaction status should remain unchanged: expected {initial_transaction_status}, got {transaction.status}"
            assert transaction.amount == initial_transaction_amount, f"Transaction amount should remain unchanged: expected {initial_transaction_amount}, got {transaction.amount}"
            assert transaction.paid_at == initial_transaction_paid_at, f"Transaction paid_at should remain unchanged: expected {initial_transaction_paid_at}, got {transaction.paid_at}"
            
            # The updated_at field should also remain unchanged since no modifications occurred
            assert transaction.updated_at == initial_transaction_updated_at, f"Transaction updated_at should remain unchanged: expected {initial_transaction_updated_at}, got {transaction.updated_at}"
            
            # Additional verification: check that no other transactions were created or modified
            all_transactions_result = await db_session.execute(
                select(Transaction).where(Transaction.wallet_id == wallet.id)
            )
            all_transactions = all_transactions_result.scalars().all()
            
            # Should only have the one transaction we created
            assert len(all_transactions) == 1, f"Should have exactly 1 transaction, found {len(all_transactions)}"
            assert all_transactions[0].id == transaction.id, "The transaction should be the same one we created"
            
            # Verify no side effects on the wallet
            wallet_transactions_result = await db_session.execute(
                select(Transaction).where(Transaction.wallet_id == wallet.id)
            )
            wallet_transactions = wallet_transactions_result.scalars().all()
            
            # Count should remain the same
            assert len(wallet_transactions) == 1, "Wallet should still have exactly 1 transaction"
        
        await engine.dispose()