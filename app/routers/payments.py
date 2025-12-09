from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import hashlib
import hmac
from datetime import datetime
from typing import Optional

from app.database import get_db
from app.models import Transaction, TransactionStatus, User
from app.schemas import (
    PaymentInitiateRequest,
    PaymentInitiateResponse,
    TransactionStatusResponse,
    WebhookResponse
)
from app.config import settings
from app.auth_utils import get_current_user

router = APIRouter(prefix="/payments", tags=["Payments"])

# Paystack API URLs
PAYSTACK_INITIALIZE_URL = "https://api.paystack.co/transaction/initialize"
PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify"


from app.dependencies import oauth2_scheme # Change this import

@router.post("/paystack/initiate", response_model=PaymentInitiateResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(oauth2_scheme)])
async def initiate_payment(
    payment_request: PaymentInitiateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Initiate a Paystack payment transaction.
    Requires authentication. Email is taken from authenticated user.
    Returns the payment reference and authorization URL.
    """
    try:
        # Validate amount
        if payment_request.amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be greater than 0"
            )
        
        # Generate unique reference
        import uuid
        reference = f"txn_{uuid.uuid4().hex}"
        
        # Check if reference already exists (idempotency)
        result = await db.execute(select(Transaction).where(Transaction.reference == reference))
        existing_transaction = result.scalar_one_or_none()
        
        if existing_transaction:
            return PaymentInitiateResponse(
                reference=existing_transaction.reference,
                authorization_url=existing_transaction.authorization_url
            )
        
        # Call Paystack Initialize Transaction API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                PAYSTACK_INITIALIZE_URL,
                headers={
                    "Authorization": f"Bearer {settings.paystack_secret_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "amount": payment_request.amount,
                    "email": current_user.email,  # Get email from authenticated user
                    "reference": reference,
                    "currency": "NGN"
                }
            )
            
            if response.status_code != 200:
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
            
            # Persist transaction in database
            transaction = Transaction(
                reference=reference,
                user_id=current_user.id,  # Link transaction to authenticated user
                amount=payment_request.amount,
                status=TransactionStatus.PENDING,
                authorization_url=authorization_url
            )
            db.add(transaction)
            await db.commit()
            await db.refresh(transaction)
            
            return PaymentInitiateResponse(
                reference=transaction.reference,
                authorization_url=transaction.authorization_url
            )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )


@router.post("/paystack/webhook", response_model=WebhookResponse)
async def paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_paystack_signature: Optional[str] = Header(None)
):
    """
    Webhook endpoint to receive transaction updates from Paystack.
    Validates the signature and updates transaction status in the database.
    """
    try:
        # Get request body
        body = await request.body()
        
        # Verify Paystack signature
        if not x_paystack_signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Paystack signature"
            )
        
        # Compute expected signature
        computed_signature = hmac.new(
            settings.paystack_webhook_secret.encode('utf-8'),
            body,
            hashlib.sha512
        ).hexdigest()
        
        if not hmac.compare_digest(computed_signature, x_paystack_signature):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature"
            )
        
        # Parse event payload
        import json
        event = json.loads(body)
        
        event_type = event.get("event")
        data = event.get("data", {})
        
        if event_type == "charge.success":
            reference = data.get("reference")
            
            if reference:
                # Find transaction in database
                result = await db.execute(select(Transaction).where(Transaction.reference == reference))
                transaction = result.scalar_one_or_none()
                
                if transaction:
                    transaction.status = TransactionStatus.SUCCESS
                    transaction.paid_at = datetime.utcnow()
                    await db.commit()
        
        elif event_type == "charge.failed":
            reference = data.get("reference")
            
            if reference:
                result = await db.execute(select(Transaction).where(Transaction.reference == reference))
                transaction = result.scalar_one_or_none()
                
                if transaction:
                    transaction.status = TransactionStatus.FAILED
                    await db.commit()
        
        return WebhookResponse(status=True)
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {str(e)}"
        )


@router.get("/{reference}/status", response_model=TransactionStatusResponse, dependencies=[Depends(oauth2_scheme)])
async def get_transaction_status(
    reference: str,
    refresh: bool = False,
    current_user: User = Depends(get_current_user), # Add this line
    db: AsyncSession = Depends(get_db)
):
    """
    Check transaction status by reference.
    If refresh=true, fetches the latest status from Paystack.
    """
    try:
        # Find transaction in database
        result = await db.execute(select(Transaction).where(Transaction.reference == reference))
        transaction = result.scalar_one_or_none()
        
        if not transaction:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )
        
        # If refresh is requested, fetch from Paystack
        if refresh:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{PAYSTACK_VERIFY_URL}/{reference}",
                    headers={
                        "Authorization": f"Bearer {settings.paystack_secret_key}"
                    }
                )
                
                if response.status_code == 200:
                    paystack_data = response.json()
                    
                    if paystack_data.get("status"):
                        data = paystack_data["data"]
                        paystack_status = data.get("status")
                        
                        # Map Paystack status to our status
                        if paystack_status == "success":
                            transaction.status = TransactionStatus.SUCCESS
                            transaction.paid_at = datetime.utcnow()
                        elif paystack_status == "failed":
                            transaction.status = TransactionStatus.FAILED
                        else:
                            transaction.status = TransactionStatus.PENDING
                        
                        await db.commit()
                        await db.refresh(transaction)
        
        return TransactionStatusResponse(
            reference=transaction.reference,
            status=transaction.status.value,
            amount=transaction.amount,
            paid_at=transaction.paid_at
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error: {str(e)}"
        )
