import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, Wallet, Transaction, TransactionStatus, TransactionType
from app.wallet_service import credit_wallet, transfer_funds

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def sender(db_session: AsyncSession) -> User:
    """Fixture for a sender user with a wallet."""
    user = User(google_id="sender_google", email="sender@example.com", name="Sender")
    wallet = Wallet(user=user, wallet_number="1111111111", balance=15000)
    db_session.add_all([user, wallet])
    await db_session.commit()
    await db_session.refresh(user, ["wallet"])
    return user

@pytest.fixture
async def recipient(db_session: AsyncSession) -> User:
    """Fixture for a recipient user with a wallet."""
    user = User(google_id="recipient_google", email="recipient@example.com", name="Recipient")
    wallet = Wallet(user=user, wallet_number="9999999999", balance=5000)
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
