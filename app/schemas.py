from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
import enum
import uuid

# --- Enums (mirroring models) ---

class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"

class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    TRANSFER = "transfer"

class ApiKeyPermissions(str, enum.Enum):
    DEPOSIT = "deposit"
    TRANSFER = "transfer"
    READ = "read"

class ExpiryDuration(str, enum.Enum):
    ONE_HOUR = "1H"
    ONE_DAY = "1D"
    ONE_MONTH = "1M"
    ONE_YEAR = "1Y"


# --- Google Auth Schemas ---

class GoogleAuthURLResponse(BaseModel):
    google_auth_url: str

class GoogleCallbackResponse(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    access_token: str
    token_type: str = "bearer"


# --- API Key Schemas ---

class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., description="A human-readable name for the API key.")
    permissions: List[ApiKeyPermissions] = Field(..., description="List of permissions for the key.")
    expiry: ExpiryDuration = Field(..., description="Expiration duration (1H, 1D, 1M, 1Y).")

class ApiKeyResponse(BaseModel):
    api_key: str = Field(..., description="The generated API key. This is the only time it will be shown.")
    expires_at: datetime

class ApiKeyRolloverRequest(BaseModel):
    expired_key_id: str = Field(..., description="The ID of the expired key to rollover.")
    expiry: ExpiryDuration = Field(..., description="New expiration duration for the rolled-over key.")

class ApiKeyDetailResponse(BaseModel):
    id: str
    name: str
    permissions: List[ApiKeyPermissions]
    expires_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


# --- Wallet & Payment Schemas ---

class PaymentInitiateResponse(BaseModel):
    reference: str
    authorization_url: str

class WalletDepositRequest(BaseModel):
    amount: int = Field(..., gt=0, description="Amount to deposit in kobo (lowest currency unit).")

class DepositStatusResponse(BaseModel):
    reference: str
    status: TransactionStatus
    amount: int
    paid_at: Optional[datetime] = None

class WebhookResponse(BaseModel):
    status: bool

class WalletBalanceResponse(BaseModel):
    balance: int # in kobo

class WalletTransferRequest(BaseModel):
    recipient_wallet_number: str = Field(..., description="The wallet number of the recipient.")
    amount: int = Field(..., gt=0, description="Amount to transfer in kobo.")

class TransactionHistoryResponse(BaseModel):
    id: str
    type: TransactionType
    amount: int
    status: TransactionStatus
    description: Optional[str] = None
    created_at: datetime

# This schema is not directly exposed via an endpoint but is used for dependency injection
class User(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None
    google_id: str

    class Config:
        from_attributes = True