from fastapi import APIRouter, Depends, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.database import get_db
from app.schemas import WebhookResponse
from app.routers.wallet import paystack_webhook

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/paystack/webhook", response_model=WebhookResponse, include_in_schema=False)
async def payments_paystack_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_paystack_signature: Optional[str] = Header(None)
):
    """
    Legacy webhook endpoint for backward compatibility.
    Redirects to the main webhook handler in wallet router.
    """
    return await paystack_webhook(request, db, x_paystack_signature)