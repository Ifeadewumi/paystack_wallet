from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import httpx
from urllib.parse import urlencode
import logging
from datetime import datetime
import random

from app.database import get_db
from app.models import User, Wallet
from app.schemas import GoogleAuthURLResponse, GoogleCallbackResponse
from app.config import settings
from app.auth_utils import create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Google OAuth URLs
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


@router.get("/google", response_model=GoogleAuthURLResponse)
async def google_signin():
    """
    Trigger Google sign-in flow.
    Returns the Google OAuth consent page URL.
    """
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent"
    }
    google_auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return GoogleAuthURLResponse(google_auth_url=google_auth_url)


@router.get("/google/callback", response_model=GoogleCallbackResponse)
async def google_callback(code: str = None, db: AsyncSession = Depends(get_db)):
    """
    Google OAuth callback endpoint.
    Exchanges the code for access token, creates/updates user,
    and creates a wallet for new users.
    """
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code"
        )
    
    try:
        # Step 1: Exchange code for access token
        async with httpx.AsyncClient() as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code"
                }
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            
            # Step 2: Fetch user info from Google
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {token_data['access_token']}"}
            )
            userinfo_response.raise_for_status()
            user_info = userinfo_response.json()

        google_id = user_info.get("id")
        email = user_info.get("email")
        if not google_id or not email:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Incomplete user info from Google"
            )
        
        # Step 3: Create or update user in database
        result = await db.execute(
            select(User).options(selectinload(User.wallet)).where(User.google_id == google_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Update existing user's info
            user.email = email
            user.name = user_info.get("name")
            user.picture = user_info.get("picture")
        else:
            # Create new user
            user = User(
                google_id=google_id,
                email=email,
                name=user_info.get("name"),
                picture=user_info.get("picture")
            )
            db.add(user)
            # Create a wallet for the new user
            wallet_number = f"{int(datetime.now().timestamp() * 1000)}{random.randint(100, 999)}"
            new_wallet = Wallet(
                user=user,
                wallet_number=wallet_number,
                balance=0
            )
            db.add(new_wallet)
        
        await db.commit()
        await db.refresh(user)
        
        # Step 4: Create JWT token for the user
        # Note: The 'sub' (subject) of the token should be the user's ID in our system
        jwt_token = create_access_token(data={"sub": str(user.id)})
        
        return GoogleCallbackResponse(
            user_id=str(user.id),
            email=user.email,
            name=user.name,
            access_token=jwt_token,
            token_type="bearer"
        )
    
    except httpx.HTTPStatusError as e:
        logging.error(f"HTTP error during Google OAuth: {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Error communicating with Google"
        )
    except Exception as e:
        logging.error(f"Error in /auth/google/callback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {str(e)}"
        )