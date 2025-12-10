from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple
import hashlib

from app.database import get_db
from app.models import User, ApiKey, ApiKeyPermissions
from app.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/google")

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

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User:
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

    key_prefix = api_key.split('_')[1]
    
    result = await db.execute(select(ApiKey).where(ApiKey.key_prefix == key_prefix))
    db_api_key = result.scalar_one_or_none()

    if db_api_key is None:
        raise CREDENTIALS_EXCEPTION

    if not hashlib.sha256(api_key.encode()).hexdigest() == db_api_key.key_hash:
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
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Tuple[User, List[str]]:
    if authorization:
        # JWT authentication
        token_type, _, token = authorization.partition(' ')
        if token_type.lower() != 'bearer' or not token:
            raise CREDENTIALS_EXCEPTION
        user = await get_current_user(token, db)
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