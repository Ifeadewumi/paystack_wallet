import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from hypothesis import given, strategies as st, settings, HealthCheck
from sqlalchemy import select

from app.models import User, Wallet, Transaction, TransactionStatus, TransactionType
from app.wallet_service import credit_wallet, transfer_funds

pytestmark = pytest.mark.asyncio

@pytest_asyncio.fixture
async def sender(db_session: AsyncSession) -> User:
    """Fixture for a sender user with a wallet."""
    import uuid
    unique_id = uuid.uuid4().hex[:8]
    user = User(google_id=f"sender_google_{unique_id}", email=f"sender_{unique_id}@example.com", name="Sender")
    wallet = Wallet(user=user, wallet_number=f"1111{unique_id[:6]}", balance=15000)
    db_session.add_all([user, wallet])
    await db_session.commit()
    await db_session.refresh(user, ["wallet"])
    return user

@pytest_asyncio.fixture
async def recipient(db_session: AsyncSession) -> User:
    """Fixture for a recipient user with a wallet."""
    import uuid
    unique_id = uuid.uuid4().hex[:8]
    user = User(google_id=f"recipient_google_{unique_id}", email=f"recipient_{unique_id}@example.com", name="Recipient")
    wallet = Wallet(user=user, wallet_number=f"9999{unique_id[:6]}", balance=5000)
    db_session.add_all([user, wallet])
    await db_session.commit()
    await db_session.refresh(user, ["wallet"])
    return user

async def test_credit_wallet_service(db_session: AsyncSession, sender: User):
    """Test the credit_wallet service function."""
    initial_balance = sender.wallet.balance
    credit_amount = 5000

    # Create a pending transaction to be processed
    tx = Transaction(
        wallet_id=sender.wallet.id,
        user_id=sender.id,
        type=TransactionType.DEPOSIT,
        amount=credit_amount,
        status=TransactionStatus.PENDING,
        reference="service_test_ref"
    )
    db_session.add(tx)
    await db_session.commit()
    await db_session.refresh(tx)

    # Call the service function
    await credit_wallet(db_session, tx)

    # Verify results
    await db_session.refresh(sender.wallet)
    await db_session.refresh(tx)

    assert sender.wallet.balance == initial_balance + credit_amount
    assert tx.status == TransactionStatus.SUCCESS
    assert tx.paid_at is not None

async def test_transfer_funds_service_success(db_session: AsyncSession, sender: User, recipient: User):
    """Test the transfer_funds service function for a successful transfer."""
    sender_initial_balance = sender.wallet.balance
    recipient_initial_balance = recipient.wallet.balance
    transfer_amount = 5000

    # Call the service function
    await transfer_funds(
        db=db_session,
        sender_user_id=sender.id,
        recipient_wallet_number=recipient.wallet.wallet_number,
        amount=transfer_amount
    )

    # Verify balances
    await db_session.refresh(sender.wallet)
    await db_session.refresh(recipient.wallet)
    assert sender.wallet.balance == sender_initial_balance - transfer_amount
    assert recipient.wallet.balance == recipient_initial_balance + transfer_amount

async def test_transfer_funds_insufficient_balance(db_session: AsyncSession, sender: User, recipient: User):
    """Test transfer_funds raises an exception for insufficient balance."""
    transfer_amount = sender.wallet.balance + 1 # More than the sender has

    with pytest.raises(HTTPException) as excinfo:
        await transfer_funds(
            db=db_session,
            sender_user_id=sender.id,
            recipient_wallet_number=recipient.wallet.wallet_number,
            amount=transfer_amount
        )
    
    assert excinfo.value.status_code == 400
    assert "Insufficient funds" in excinfo.value.detail

async def test_transfer_funds_invalid_recipient(db_session: AsyncSession, sender: User):
    """Test transfer_funds raises an exception for a non-existent recipient."""
    with pytest.raises(HTTPException) as excinfo:
        await transfer_funds(
            db=db_session,
            sender_user_id=sender.id,
            recipient_wallet_number="non_existent_wallet",
            amount=1000
        )
    
    assert excinfo.value.status_code == 404
    assert "Recipient wallet not found" in excinfo.value.detail

@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    num_transfers=st.integers(min_value=2, max_value=10),
    transfer_amounts=st.lists(st.integers(min_value=1, max_value=1000), min_size=2, max_size=10)
)
async def test_transfer_reference_uniqueness_property(
    test_db_url_fixture: str,
    setup_test_db,
    num_transfers: int, 
    transfer_amounts: list[int]
):
    """
    Feature: paystack-wallet-compliance, Property 3: Transfer reference uniqueness
    
    Property: For any two transfer operations, their references should be different 
    and follow the "xfer_" prefix pattern.
    
    Validates: Requirements 16.2, 16.3, 16.4
    """
    # Create our own database session for this property test
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.orm import sessionmaker
    
    engine = create_async_engine(test_db_url_fixture)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db_session:
        # Ensure we have enough transfer amounts for the number of transfers
        if len(transfer_amounts) < num_transfers:
            transfer_amounts = transfer_amounts * ((num_transfers // len(transfer_amounts)) + 1)
        transfer_amounts = transfer_amounts[:num_transfers]
        
        # Create sender with sufficient balance
        import uuid
        test_id = uuid.uuid4().hex[:8]  # Unique identifier for this test run
        total_amount = sum(transfer_amounts)
        sender = User(
            google_id=f"sender_prop_test_{test_id}", 
            email=f"sender_prop_{test_id}@example.com", 
            name=f"Sender Prop {test_id}"
        )
        sender_wallet = Wallet(
            user=sender, 
            wallet_number=f"1111{test_id[:6]}", 
            balance=total_amount + 10000  # Extra buffer
        )
        db_session.add_all([sender, sender_wallet])
        
        # Create multiple recipients
        recipients = []
        for i in range(num_transfers):
            recipient = User(
                google_id=f"recipient_prop_test_{test_id}_{i}", 
                email=f"recipient_prop_{test_id}_{i}@example.com", 
                name=f"Recipient Prop {test_id} {i}"
            )
            recipient_wallet = Wallet(
                user=recipient, 
                wallet_number=f"9999{test_id[:4]}{i:02d}", 
                balance=5000
            )
            recipients.append((recipient, recipient_wallet))
            db_session.add_all([recipient, recipient_wallet])
        
        await db_session.commit()
        await db_session.refresh(sender, ["wallet"])
        for recipient, recipient_wallet in recipients:
            await db_session.refresh(recipient, ["wallet"])
        
        # Perform multiple transfers
        for i in range(num_transfers):
            recipient, recipient_wallet = recipients[i]
            amount = transfer_amounts[i]
            
            await transfer_funds(
                db=db_session,
                sender_user_id=sender.id,
                recipient_wallet_number=recipient_wallet.wallet_number,
                amount=amount
            )
        
        # Verify all transfer references are unique and follow correct pattern
        result = await db_session.execute(
            select(Transaction.reference).where(
                Transaction.type == TransactionType.TRANSFER,
                Transaction.user_id == sender.id
            )
        )
        transfer_references = [row[0] for row in result.fetchall()]
        
        # Check uniqueness
        assert len(transfer_references) == len(set(transfer_references)), \
            f"Transfer references are not unique: {transfer_references}"
        
        # Check prefix pattern
        for ref in transfer_references:
            assert ref.startswith("xfer_"), \
                f"Transfer reference '{ref}' does not start with 'xfer_' prefix"
            
            # Check that it's not the old collision-prone pattern
            assert not ref.startswith("xfer_") or "_to_" not in ref, \
                f"Transfer reference '{ref}' uses old collision-prone pattern"
    
    await engine.dispose()
