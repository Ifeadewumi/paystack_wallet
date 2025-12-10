from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from datetime import datetime, timezone
import uuid

from app.models import Wallet, Transaction, TransactionStatus, TransactionType, User

async def credit_wallet(db: AsyncSession, transaction: Transaction):
    """
    Atomically credits a wallet and marks the transaction as successful.
    This function is designed to be called by the Paystack webhook.
    """
    # Lock the wallet row for update to prevent race conditions
    result = await db.execute(
        select(Wallet).where(Wallet.id == transaction.wallet_id).with_for_update()
    )
    wallet = result.scalar_one_or_none()

    if not wallet:
        # This should ideally not happen if the transaction is valid
        transaction.status = TransactionStatus.FAILED
        transaction.description = "Failed: Wallet not found."
        await db.commit()
        return

    # Idempotency: Ensure we don't credit twice
    if transaction.status == TransactionStatus.SUCCESS:
        return

    wallet.balance += transaction.amount
    transaction.status = TransactionStatus.SUCCESS
    transaction.paid_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(wallet)
    await db.refresh(transaction)

async def transfer_funds(db: AsyncSession, sender_user_id: str, recipient_wallet_number: str, amount: int):
    """
    Atomically transfers funds from a sender's wallet to a recipient's wallet.
    """
    # Use a single transaction block to ensure atomicity
    async with db.begin_nested():
        # 1. Get sender's wallet and lock it
        sender_wallet_res = await db.execute(
            select(Wallet).where(Wallet.user_id == sender_user_id).with_for_update()
        )
        sender_wallet = sender_wallet_res.scalar_one_or_none()

        if not sender_wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sender wallet not found.")

        if sender_wallet.balance < amount:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Insufficient funds.")

        # 2. Get recipient's wallet and lock it
        recipient_wallet_res = await db.execute(
            select(Wallet).where(Wallet.wallet_number == recipient_wallet_number).with_for_update()
        )
        recipient_wallet = recipient_wallet_res.scalar_one_or_none()

        if not recipient_wallet:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient wallet not found.")
        
        if sender_wallet.id == recipient_wallet.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot transfer to the same wallet.")

        # 3. Perform the transfer
        sender_wallet.balance -= amount
        recipient_wallet.balance += amount

        # 4. Record transactions for both parties
        # Generate unique references using UUID to prevent collisions
        # Each transaction gets its own unique reference
        sender_reference = f"xfer_{uuid.uuid4().hex}"
        recipient_reference = f"xfer_{uuid.uuid4().hex}"
        
        sender_transaction = Transaction(
            wallet_id=sender_wallet.id,
            user_id=sender_wallet.user_id,
            type=TransactionType.TRANSFER,
            amount=-amount, # Negative for debit
            status=TransactionStatus.SUCCESS,
            reference=sender_reference,
            description=f"Transfer to wallet {recipient_wallet.wallet_number}",
            paid_at=datetime.now(timezone.utc)
        )
        
        recipient_transaction = Transaction(
            wallet_id=recipient_wallet.id,
            user_id=recipient_wallet.user_id,
            type=TransactionType.TRANSFER,
            amount=amount, # Positive for credit
            status=TransactionStatus.SUCCESS,
            reference=recipient_reference,
            description=f"Transfer from wallet {sender_wallet.wallet_number}",
            paid_at=datetime.now(timezone.utc)
        )

        db.add_all([sender_transaction, recipient_transaction])

    # The transaction is committed automatically upon exiting the `async with` block
    # No need for explicit db.commit()
    
    return sender_wallet, recipient_wallet