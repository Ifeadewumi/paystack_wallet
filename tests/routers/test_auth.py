import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import respx

from app.models import User, Wallet
from app.config import settings

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

def test_google_signin(client: TestClient):
    """Test the endpoint to get the Google sign-in URL."""
    response = client.get("/auth/google")
    assert response.status_code == 200
    data = response.json()
    assert "google_auth_url" in data
    assert settings.google_client_id in data["google_auth_url"]

@respx.mock
async def test_google_callback_new_user(client: TestClient, db_session: AsyncSession):
    """Test the Google callback for a new user."""
    # Mock Google's API responses
    respx.post(GOOGLE_TOKEN_URL).respond(200, json={"access_token": "fake_google_token"})
    respx.get(GOOGLE_USERINFO_URL).respond(200, json={
        "id": "new_google_id",
        "email": "newuser@example.com",
        "name": "New User",
        "picture": "http://example.com/pic.jpg"
    })

    # Make the call to our callback endpoint
    response = client.get("/auth/google/callback?code=fake_auth_code")
    assert response.status_code == 200
    
    data = response.json()
    assert "access_token" in data
    assert data["email"] == "newuser@example.com"

    # Verify user and wallet were created in the database
    user_result = await db_session.execute(select(User).where(User.email == "newuser@example.com"))
    user = user_result.scalar_one_or_none()
    assert user is not None
    assert user.google_id == "new_google_id"

    wallet_result = await db_session.execute(select(Wallet).where(Wallet.user_id == user.id))
    wallet = wallet_result.scalar_one_or_none()
    assert wallet is not None
    assert wallet.balance == 0

@respx.mock
async def test_google_callback_existing_user(client: TestClient, db_session: AsyncSession, test_user: User):
    """Test the Google callback for an existing user."""
    # Mock Google's API to return the existing user's info
    respx.post(GOOGLE_TOKEN_URL).respond(200, json={"access_token": "fake_google_token"})
    respx.get(GOOGLE_USERINFO_URL).respond(200, json={
        "id": test_user.google_id, # Use the google_id of the fixture user
        "email": "updated.email@example.com", # Simulate an email update
        "name": "Updated Name",
        "picture": test_user.picture
    })

    # Count users before the call
    user_count_before = (await db_session.execute(select(User))).scalars().all()

    # Make the call
    response = client.get("/auth/google/callback?code=fake_auth_code")
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user_id"] == str(test_user.id)

    # Verify no new user was created
    user_count_after = (await db_session.execute(select(User))).scalars().all()
    assert len(user_count_after) == len(user_count_before)

    # Verify the user's details were updated
    await db_session.refresh(test_user)
    assert test_user.email == "updated.email@example.com"
    assert test_user.name == "Updated Name"
