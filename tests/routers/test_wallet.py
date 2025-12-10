import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import respx
import hmac
import hashlib
import json

from app.models import User, Wallet, Transaction, TransactionStatus, TransactionType
from app.config import settings

pytestmark = pytest.mark.asyncio

PAYSTACK_INITIALIZE_URL = "https://api.paystack.co/transaction/initialize"

@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    return {"Authorization": f"Bearer {auth_token}"}

async def test_get_wallet_balance(client: TestClient, auth_headers: dict, test_user: User):
    """Test retrieving the wallet balance for an authenticated user."""
    response = client.get("/wallet/balance", headers=auth_headers)
    assert response.status_code == 200
    # The test_user fixture starts with 10000 kobo
    assert response.json() == {"balance": 10000}

@respx.mock
async def test_initiate_wallet_deposit(client: TestClient, auth_headers: dict, test_user: User, db_session: AsyncSession):
    """Test successfully initiating a wallet deposit."""
    # Mock Paystack's response
    respx.post(PAYSTACK_INITIALIZE_URL).respond(200, json={
        "status": True,
        "message": "Authorization URL created",
        "data": {
            "authorization_url": "https://checkout.paystack.com/test-url",
            "access_code": "test-access-code",
            "reference": "dep_test-reference"
        }
    })

    response = client.post("/wallet/deposit", headers=auth_headers, json={"amount": 5000})
    assert response.status_code == 201
    data = response.json()
    assert "authorization_url" in data
    assert "reference" in data

    # Verify a pending transaction was created
    tx_res = await db_session.execute(select(Transaction).where(Transaction.reference == data["reference"]))
    transaction = tx_res.scalar_one()
    assert transaction.status == TransactionStatus.PENDING
    assert transaction.amount == 5000
    assert transaction.user_id == test_user.id

async def test_paystack_webhook_charge_success(client: TestClient, test_user: User, db_session: AsyncSession):
    """Test the webhook correctly credits a user's wallet on a successful charge."""
    # 1. Create a pending deposit transaction for the user
    pending_tx = Transaction(
        wallet_id=test_user.wallet.id,
        user_id=test_user.id,
        type=TransactionType.DEPOSIT,
        amount=7500, # 75 NGN
        status=TransactionStatus.PENDING,
        reference="test_webhook_ref_123"
    )
    db_session.add(pending_tx)
    await db_session.commit()

    initial_balance = test_user.wallet.balance

    # 2. Craft the webhook payload and signature
    payload = {
        "event": "charge.success",
        "data": {
            "reference": "test_webhook_ref_123",
            "status": "success",
            "amount": 7500,
        }
    }
    payload_bytes = json.dumps(payload).encode('utf-8')
    signature = hmac.new(settings.paystack_webhook_secret.encode('utf-8'), payload_bytes, hashlib.sha512).hexdigest()

    # 3. Call the webhook
    response = client.post(
        "/wallet/paystack/webhook",
        content=payload_bytes,
        headers={"x-paystack-signature": signature, "Content-Type": "application/json"}
    )
    assert response.status_code == 200
    assert response.json() == {"status": True}

    # 4. Verify wallet balance and transaction status
    await db_session.refresh(test_user.wallet)
    await db_session.refresh(pending_tx)
    assert test_user.wallet.balance == initial_balance + 7500
    assert pending_tx.status == TransactionStatus.SUCCESS

async def test_paystack_webhook_invalid_signature(client: TestClient):
    """Test that the webhook rejects requests with an invalid signature."""
    payload = {"event": "charge.success", "data": {"reference": "any"}}
    response = client.post(
        "/wallet/paystack/webhook",
        json=payload,
        headers={"x-paystack-signature": "invalid-signature"}
    )
    assert response.status_code == 400
    assert "Invalid signature" in response.json()["detail"]

async def test_wallet_transfer_success(client: TestClient, auth_headers: dict, test_user: User, db_session: AsyncSession):
    """Test a successful wallet-to-wallet transfer."""
    # 1. Create a recipient user and wallet
    recipient_user = User(google_id="recipient_google", email="recipient@example.com", name="Recipient")
    recipient_wallet = Wallet(user=recipient_user, wallet_number="9876543210", balance=5000)
    db_session.add_all([recipient_user, recipient_wallet])
    await db_session.commit()

    sender_initial_balance = test_user.wallet.balance
    recipient_initial_balance = recipient_wallet.balance

    # 2. Perform the transfer
    response = client.post(
        "/wallet/transfer",
        headers=auth_headers,
        json={"recipient_wallet_number": "9876543210", "amount": 3000}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    # 3. Verify balances
    await db_session.refresh(test_user.wallet)
    await db_session.refresh(recipient_wallet)
    assert test_user.wallet.balance == sender_initial_balance - 3000
    assert recipient_wallet.balance == recipient_initial_balance + 3000

async def test_wallet_transfer_insufficient_funds(client: TestClient, auth_headers: dict, test_user: User):
    """Test that a transfer fails if the sender has insufficient funds."""
    # test_user starts with 10000 kobo. Try to send 20000.
    response = client.post(
        "/wallet/transfer",
        headers=auth_headers,
        json={"recipient_wallet_number": "9876543210", "amount": 20000}
    )
    assert response.status_code == 400
    assert "Insufficient funds" in response.json()["detail"]
