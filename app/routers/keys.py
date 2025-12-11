from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
from uuid import UUID
import secrets

from app.database import get_db
from app.models import User, ApiKey, ApiKeyPermissions
from app.schemas import (
    ApiKeyCreateRequest,
    ApiKeyResponse,
    ApiKeyRolloverRequest,
    ApiKeyDetailResponse,
    ExpiryDuration,
)
from app.auth_utils import get_current_user_with_permissions, hash_api_key
from app.config import settings

router = APIRouter(prefix="/keys", tags=["API Key Management"])

MAX_ACTIVE_API_KEYS = 5

def calculate_expiry_datetime(duration: ExpiryDuration) -> datetime:
    now = datetime.now(timezone.utc)
    if duration == ExpiryDuration.ONE_HOUR:
        return now + timedelta(hours=1)
    if duration == ExpiryDuration.ONE_DAY:
        return now + timedelta(days=1)
    if duration == ExpiryDuration.ONE_MONTH:
        return now + timedelta(days=30)
    if duration == ExpiryDuration.ONE_YEAR:
        return now + timedelta(days=365)
    # This case should be prevented by Pydantic's enum validation
    raise ValueError("Invalid expiry duration")


@router.post("/create", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    request_data: ApiKeyCreateRequest,
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new API key for the authenticated user.
    Requires JWT authentication. A user cannot create a key with another API key.
    """
    current_user, _ = auth_data
    
    # Enforce max active API keys
    active_keys_count_result = await db.execute(
        select(func.count(ApiKey.id)).where(
            ApiKey.user_id == current_user.id,
            ApiKey.is_active == True,
            ApiKey.expires_at > datetime.now(timezone.utc)
        )
    )
    if active_keys_count_result.scalar_one() >= MAX_ACTIVE_API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Maximum of {MAX_ACTIVE_API_KEYS} active API keys allowed."
        )
    
    # Generate a secure API key
    random_part = secrets.token_urlsafe(32)
    plain_api_key = f"{settings.api_key_prefix}_{random_part}"
    key_prefix = random_part[:8] # Use first 8 chars of the random part for lookup

    expires_at = calculate_expiry_datetime(request_data.expiry)

    new_api_key = ApiKey(
        user_id=current_user.id,
        key_hash=hash_api_key(plain_api_key),
        key_prefix=key_prefix,
        name=request_data.name,
        permissions=[p.value for p in request_data.permissions],
        expires_at=expires_at
    )
    db.add(new_api_key)
    await db.commit()

    return ApiKeyResponse(api_key=plain_api_key, expires_at=expires_at)


@router.post("/rollover", response_model=ApiKeyResponse)
async def rollover_api_key(
    request_data: ApiKeyRolloverRequest,
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Rollover an expired API key into a new one with the same permissions.
    Requires JWT authentication.
    """
    current_user, _ = auth_data

    # Convert string expired_key_id to UUID
    try:
        expired_key_uuid = UUID(request_data.expired_key_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid expired key ID format.")

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == expired_key_uuid,
            ApiKey.user_id == current_user.id
        )
    )
    expired_key = result.scalar_one_or_none()

    if not expired_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")
    
    if expired_key.expires_at > datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="API key is not yet expired.")
    
    # Deactivate the old key
    expired_key.is_active = False

    # Generate a new API key with the same permissions and name
    random_part = secrets.token_urlsafe(32)
    plain_new_api_key = f"{settings.api_key_prefix}_{random_part}"
    new_key_prefix = random_part[:8]
    new_expires_at = calculate_expiry_datetime(request_data.expiry)

    new_api_key = ApiKey(
        user_id=current_user.id,
        key_hash=hash_api_key(plain_new_api_key),
        key_prefix=new_key_prefix,
        name=expired_key.name,
        permissions=expired_key.permissions,
        expires_at=new_expires_at
    )
    db.add(new_api_key)
    await db.commit()

    return ApiKeyResponse(api_key=plain_new_api_key, expires_at=new_expires_at)


@router.get("/", response_model=List[ApiKeyDetailResponse])
async def list_api_keys(
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    List all API keys for the authenticated user.
    Requires JWT authentication.
    """
    current_user, _ = auth_data

    result = await db.execute(select(ApiKey).where(ApiKey.user_id == current_user.id))
    api_keys = result.scalars().all()

    return [
        ApiKeyDetailResponse(
            id=str(key.id),
            name=key.name,
            permissions=[ApiKeyPermissions(p) for p in key.permissions],
            expires_at=key.expires_at,
            is_active=key.is_active,
            created_at=key.created_at,
            updated_at=key.updated_at
        ) for key in api_keys
    ]

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: str,
    auth_data: Tuple[User, List[str]] = Depends(get_current_user_with_permissions),
    db: AsyncSession = Depends(get_db)
):
    """
    Revoke (deactivate) an API key.
    Requires JWT authentication.
    """
    current_user, _ = auth_data

    # Convert string key_id to UUID
    try:
        key_uuid = UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid key ID format.")

    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_uuid, ApiKey.user_id == current_user.id)
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found.")

    api_key.is_active = False
    await db.commit()

    return None