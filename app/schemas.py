from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


# Google Auth Schemas
class GoogleAuthURLResponse(BaseModel):
    google_auth_url: str


class GoogleCallbackResponse(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    access_token: str
    token_type: str = "bearer"


# Paystack Payment Schemas
class PaymentInitiateRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount in kobo (lowest currency unit)")
    
    @field_validator('amount', mode='before')
    @classmethod
    def convert_to_kobo(cls, v):
        """
        Accepts both integers (kobo) and floats (naira).
        If float is provided, converts to kobo automatically.
        
        Examples:
        - 5000 → 5000 kobo (50 NGN)
        - 50.75 → 5075 kobo (50.75 NGN)
        """
        if isinstance(v, float):
            # Convert naira to kobo (multiply by 100 and round)
            return int(round(v * 100))
        return v


class PaymentInitiateResponse(BaseModel):
    reference: str
    authorization_url: str


class TransactionStatusResponse(BaseModel):
    reference: str
    status: str
    amount: int
    paid_at: Optional[datetime] = None


class WebhookResponse(BaseModel):
    status: bool
