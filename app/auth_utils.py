from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
import hashlib

from app.database import get_db
from app.models import User, ApiKey, ApiKeyPermissions
from app.config import settings

oauth2_scheme = HTTPBearer()

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

# --- JWT Functions ---

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

async def get_current_user(credentials = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise CREDENTIALS_EXCEPTION
    except JWTError:
        raise CREDENTIALS_EXCEPTION
    
    user = await db.get(User, user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
    return user

# --- API Key Functions ---

def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()

async def get_user_from_api_key(api_key: str, db: AsyncSession = Depends(get_db)) -> Tuple[User, List[str]]:
    if not api_key.startswith(settings.api_key_prefix + "_"):
        raise CREDENTIALS_EXCEPTION

    # Extract the random part after the prefix (sk_live_)
    parts = api_key.split('_')
    if len(parts) < 3:
        raise CREDENTIALS_EXCEPTION
    random_part = parts[2]  # The part after sk_live_
    key_prefix = random_part[:8]
    
    # Get all API keys with matching prefix (there might be multiple due to collisions)
    result = await db.execute(select(ApiKey).where(ApiKey.key_prefix == key_prefix))
    potential_keys = result.scalars().all()

    if not potential_keys:
        raise CREDENTIALS_EXCEPTION

    # Find the correct API key by checking the full hash
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    db_api_key = None
    for key in potential_keys:
        if key.key_hash == api_key_hash:
            db_api_key = key
            break

    if db_api_key is None:
        raise CREDENTIALS_EXCEPTION

    if not db_api_key.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key is inactive")

    if db_api_key.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API key has expired")

    user = await db.get(User, db_api_key.user_id)
    if user is None:
        raise CREDENTIALS_EXCEPTION
        
    return user, db_api_key.permissions


# --- Combined Auth Dependency ---

async def get_current_user_with_permissions(
    credentials = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db)
) -> Tuple[User, List[str]]:
    # Try JWT authentication first (from HTTPBearer)
    if credentials:
        token = credentials.credentials
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise CREDENTIALS_EXCEPTION
        except JWTError:
            raise CREDENTIALS_EXCEPTION
        
        user = await db.get(User, user_id)
        if user is None:
            raise CREDENTIALS_EXCEPTION
            
        # JWT users have all permissions
        all_permissions = [p.value for p in ApiKeyPermissions]
        return user, all_permissions
    elif x_api_key:
        # API Key authentication
        return await get_user_from_api_key(x_api_key, db)
    else:
        raise CREDENTIALS_EXCEPTION

# --- Permission Check ---

def check_permission(required_permission: str, permissions: List[str]):
    if required_permission not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. '{required_permission}' required."
        )