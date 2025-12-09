from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
from urllib.parse import urlencode
import uuid
import logging

from app.database import get_db
from app.models import User
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
    try:
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
    
    except Exception as e:
        logging.error(f"Error in /auth/google endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error generating auth URL: {str(e)}"
        )


@router.get("/google/callback", response_model=GoogleCallbackResponse)
async def google_callback(code: str = None, db: AsyncSession = Depends(get_db)):
    """
    Google OAuth callback endpoint.
    Exchanges the code for access token and creates/updates user in database.
    """
    print("Entering google_callback function") # Added print statement
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
            
            if token_response.status_code != 200:
                print(f"Google token exchange failed: Status {token_response.status_code}, Response: {token_response.text}") # Added print statement
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authorization code"
                )
            
            token_data = token_response.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Failed to obtain access token"
                )
            
            # Step 2: Fetch user info from Google
            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if userinfo_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to fetch user info from Google"
                )
            
            user_info = userinfo_response.json()
            
            # Step 3: Create or update user in database
            google_id = user_info.get("id")
            email = user_info.get("email")
            name = user_info.get("name")
            picture = user_info.get("picture")
            
            if not google_id or not email:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Incomplete user info from Google"
                )
            
            # Check if user exists
            result = await db.execute(select(User).where(User.google_id == google_id))
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                # Update existing user
                existing_user.email = email
                existing_user.name = name
                existing_user.picture = picture
                user = existing_user
            else:
                # Create new user
                user = User(
                    id=str(uuid.uuid4()),
                    google_id=google_id,
                    email=email,
                    name=name,
                    picture=picture
                )
                db.add(user)
            
            await db.commit()
            await db.refresh(user)
            
            # Create JWT token for the user
            access_token = create_access_token(
                data={"sub": user.id, "email": user.email}
            )
            
            return GoogleCallbackResponse(
                user_id=user.id,
                email=user.email,
                name=user.name,
                access_token=access_token,
                token_type="bearer"
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error in /auth/google/callback: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Provider error: {str(e)}"
        )
