from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import uuid
import hmac
import hashlib
from datetime import datetime
from typing import List, Tuple, Optional

from app.database import get_db
from app.models import User, Transaction, TransactionStatus, TransactionType, Wallet
from app.schemas import (
    WalletDepositRequest,
    PaymentInitiateResponse,
    DepositStatusResponse,
    DepositVerifyResponse,
    WalletBalanceResponse,
    WalletTransferRequest,
    TransactionHistoryResponse,
    WebhookResponse
)
from app.config import settings
from app.auth_utils import get_current_user_with_permissions, check_permission, oauth2_scheme, get_current_user
from app.wallet_service import credit_wallet, transfer_funds

router = APIRouter(prefix="/wallet", tags=["Wallet Operations"])

# Paystack API URLs
PAYSTACK_INITIALIZE_URL = "https://api.paystack.co/transaction/initialize"
PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify"


async def verify_paystack_transaction(reference: str) -> dict:
    """
    Call Paystack's transaction verify endpoint to get transaction status.
    Returns the verification response from Paystack.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{PAYSTACK_VERIFY_URL}/{reference}",
            headers={
                "Authorization": f"Bearer {settings.paystack_secret_key}",
                "Content-Type": "application/json"
            }
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Paystack verification failed: {response.text}"
            )
        
        return response.json()


@router.post("/deposit", response_model=PaymentInitiateResponse, status_code=status.HTTP_201_CREATED)
async def initiate_wallet_deposit(
    request_data: WalletDepositRequest,
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Initiate a Paystack deposit into the user's wallet.
    Requires JWT or API Key with 'deposit' permission.
    """
    current_user, permissions = auth_data
    check_permission("deposit", permissions)

    # Find wallet for the current user
    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not have a wallet.")

    # Validate amount
    if request_data.amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be greater than 0"
        )
    
    # Generate unique reference
    reference = f"dep_{uuid.uuid4().hex}"
    
    # Create transaction record (status: pending)
    transaction = Transaction(
        wallet_id=wallet.id,
        user_id=current_user.id,
        type=TransactionType.DEPOSIT,
        amount=request_data.amount,
        status=TransactionStatus.PENDING,
        reference=reference,
        description="Wallet deposit via Paystack"
    )
    db.add(transaction)
    await db.commit()
    await db.refresh(transaction)

    # Call Paystack Initialize Transaction API
    async with httpx.AsyncClient() as client:
        response = await client.post(
            PAYSTACK_INITIALIZE_URL,
            headers={
                "Authorization": f"Bearer {settings.paystack_secret_key}",
                "Content-Type": "application/json"
            },
            json={
                "amount": request_data.amount,
                "email": current_user.email,
                "reference": reference,
                "currency": "NGN",
            }
        )
        
        if response.status_code != 200:
            # Rollback transaction creation if Paystack fails
            await db.delete(transaction)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Payment initiation failed: {response.text}"
            )
        
        paystack_data = response.json()
        
        if not paystack_data.get("status"):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Payment initiation failed by Paystack"
            )
        
        authorization_url = paystack_data["data"]["authorization_url"]
        
        # Update transaction with authorization URL
        transaction.authorization_url = authorization_url
        await db.commit()
        
        return PaymentInitiateResponse(
            reference=transaction.reference,
            authorization_url=transaction.authorization_url
        )


@router.post("/paystack/webhook", response_model=WebhookResponse, include_in_schema=False)
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_paystack_signature: Optional[str] = Header(None)
):
    """
    Webhook endpoint to receive transaction updates from Paystack.
    This endpoint is not meant to be called directly by users.
    """
    body = await request.body()
    
    # Verify Paystack signature
    if not x_paystack_signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Paystack signature")
    
    computed_signature = hmac.new(
        settings.paystack_webhook_secret.encode('utf-8'),
        body,
        hashlib.sha512
    ).hexdigest()
    
    if not hmac.compare_digest(computed_signature, x_paystack_signature):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")
    
    # Parse event payload
    event = await request.json()
    event_type = event.get("event")
    data = event.get("data", {})
    
    if event_type == "charge.success":
        reference = data.get("reference")
        
        if reference and reference.startswith("dep_"):
            result = await db.execute(select(Transaction).where(Transaction.reference == reference))
            transaction = result.scalar_one_or_none()
            
            # Idempotency check: Only credit wallet if transaction is still pending
            if transaction and transaction.status == TransactionStatus.PENDING:
                await credit_wallet(db, transaction)

    return WebhookResponse(status=True)


@router.get("/deposit/{reference}/status", response_model=DepositStatusResponse)
async def get_deposit_status(
    reference: str,
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Check the status of a wallet deposit transaction.
    Requires JWT or API Key with 'read' permission.
    This endpoint must not credit wallets.
    """
    current_user, permissions = auth_data
    check_permission("read", permissions)

    result = await db.execute(
        select(Transaction).where(
            Transaction.reference == reference,
            Transaction.user_id == current_user.id,
            Transaction.type == TransactionType.DEPOSIT
        )
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit transaction not found for this user and reference."
        )
    
    return DepositStatusResponse(
        reference=transaction.reference,
        status=transaction.status,
        amount=transaction.amount,
        paid_at=transaction.paid_at
    )


@router.get("/deposit/{reference}/verify", response_model=DepositVerifyResponse)
async def verify_deposit_transaction(
    reference: str,
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Verify a wallet deposit transaction by calling Paystack's verify API.
    Requires JWT or API Key with 'read' permission.
    This endpoint is read-only and does not credit wallets.
    """
    current_user, permissions = auth_data
    check_permission("read", permissions)

    # First check if the transaction exists and belongs to the user
    result = await db.execute(
        select(Transaction).where(
            Transaction.reference == reference,
            Transaction.user_id == current_user.id,
            Transaction.type == TransactionType.DEPOSIT
        )
    )
    transaction = result.scalar_one_or_none()
    
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit transaction not found for this user and reference."
        )
    
    # Call Paystack verify API
    paystack_response = await verify_paystack_transaction(reference)
    
    # Extract Paystack status
    paystack_status = "unknown"
    if paystack_response.get("status") and paystack_response.get("data"):
        paystack_data = paystack_response["data"]
        paystack_status = paystack_data.get("status", "unknown")
    
    return DepositVerifyResponse(
        reference=transaction.reference,
        status=transaction.status,
        amount=transaction.amount,
        paid_at=transaction.paid_at,
        paystack_status=paystack_status,
        paystack_data=paystack_response.get("data", {})
    )


@router.get("/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance(
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the current balance of the authenticated user's wallet.
    Requires JWT or API Key with 'read' permission.
    """
    current_user, permissions = auth_data
    check_permission("read", permissions)

    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not have a wallet.")
    
    return WalletBalanceResponse(balance=wallet.balance)





@router.post("/transfer", response_model=dict)
async def transfer_wallet_funds(
    request_data: WalletTransferRequest,
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Transfer funds from the authenticated user's wallet to another user's wallet.
    Requires JWT or API Key with 'transfer' permission.
    """
    current_user, permissions = auth_data
    check_permission("transfer", permissions)

    if request_data.amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Transfer amount must be greater than 0.")

    await transfer_funds(
        db=db,
        sender_user_id=current_user.id,
        recipient_wallet_number=request_data.recipient_wallet_number,
        amount=request_data.amount
    )

    return {"status": "success", "message": "Transfer completed successfully."}


@router.get("/transactions", response_model=List[TransactionHistoryResponse])
async def get_wallet_transactions(
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Get the transaction history for the authenticated user's wallet.
    Requires JWT or API Key with 'read' permission.
    """
    current_user, permissions = auth_data
    check_permission("read", permissions)

    result = await db.execute(select(Wallet).where(Wallet.user_id == current_user.id))
    wallet = result.scalar_one_or_none()
    if not wallet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User does not have a wallet.")
    
    result = await db.execute(
        select(Transaction).where(Transaction.wallet_id == wallet.id).order_by(Transaction.created_at.desc())
    )
    transactions = result.scalars().all()

    return [
        TransactionHistoryResponse(
            id=str(t.id),
            type=t.type,
            amount=t.amount,
            status=t.status,
            description=t.description,
            created_at=t.created_at
        ) for t in transactions
    ]