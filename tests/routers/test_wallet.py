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
PAYSTACK_VERIFY_URL = "https://api.paystack.co/transaction/verify"

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


@respx.mock
async def test_verify_deposit_transaction_success(client: TestClient, auth_headers: dict, test_user: User, db_session: AsyncSession):
    """Test successful verification of a deposit transaction via Paystack verify API."""
    # 1. Create a pending deposit transaction for the user
    pending_tx = Transaction(
        wallet_id=test_user.wallet.id,
        user_id=test_user.id,
        type=TransactionType.DEPOSIT,
        amount=5000,
        status=TransactionStatus.PENDING,
        reference="dep_verify_test_123"
    )
    db_session.add(pending_tx)
    await db_session.commit()

    # 2. Mock Paystack verify API successful response
    respx.get(f"{PAYSTACK_VERIFY_URL}/dep_verify_test_123").respond(200, json={
        "status": True,
        "message": "Verification successful",
        "data": {
            "reference": "dep_verify_test_123",
            "status": "success",
            "amount": 5000,
            "currency": "NGN",
            "paid_at": "2023-01-01T12:00:00.000Z"
        }
    })

    # 3. Call the verify endpoint
    response = client.get("/wallet/deposit/dep_verify_test_123/verify", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert data["reference"] == "dep_verify_test_123"
    assert data["status"] == TransactionStatus.PENDING  # Our local status
    assert data["amount"] == 5000
    assert data["paystack_status"] == "success"  # Paystack status
    assert "paystack_data" in data
    assert data["paystack_data"]["reference"] == "dep_verify_test_123"


@respx.mock
async def test_verify_deposit_transaction_failed(client: TestClient, auth_headers: dict, test_user: User, db_session: AsyncSession):
    """Test verification of a failed deposit transaction via Paystack verify API."""
    # 1. Create a pending deposit transaction for the user
    pending_tx = Transaction(
        wallet_id=test_user.wallet.id,
        user_id=test_user.id,
        type=TransactionType.DEPOSIT,
        amount=3000,
        status=TransactionStatus.PENDING,
        reference="dep_verify_failed_456"
    )
    db_session.add(pending_tx)
    await db_session.commit()

    # 2. Mock Paystack verify API failed response
    respx.get(f"{PAYSTACK_VERIFY_URL}/dep_verify_failed_456").respond(200, json={
        "status": True,
        "message": "Verification successful",
        "data": {
            "reference": "dep_verify_failed_456",
            "status": "failed",
            "amount": 3000,
            "currency": "NGN"
        }
    })

    # 3. Call the verify endpoint
    response = client.get("/wallet/deposit/dep_verify_failed_456/verify", headers=auth_headers)
    assert response.status_code == 200
    
    data = response.json()
    assert data["reference"] == "dep_verify_failed_456"
    assert data["status"] == TransactionStatus.PENDING  # Our local status
    assert data["amount"] == 3000
    assert data["paystack_status"] == "failed"  # Paystack status
    assert "paystack_data" in data


@respx.mock
async def test_verify_deposit_paystack_api_failure(client: TestClient, auth_headers: dict, test_user: User, db_session: AsyncSession):
    """Test handling of Paystack API failure during verification."""
    # 1. Create a pending deposit transaction for the user
    pending_tx = Transaction(
        wallet_id=test_user.wallet.id,
        user_id=test_user.id,
        type=TransactionType.DEPOSIT,
        amount=2000,
        status=TransactionStatus.PENDING,
        reference="dep_verify_api_fail_789"
    )
    db_session.add(pending_tx)
    await db_session.commit()

    # 2. Mock Paystack verify API failure
    respx.get(f"{PAYSTACK_VERIFY_URL}/dep_verify_api_fail_789").respond(500, json={
        "status": False,
        "message": "Internal server error"
    })

    # 3. Call the verify endpoint
    response = client.get("/wallet/deposit/dep_verify_api_fail_789/verify", headers=auth_headers)
    assert response.status_code == 502  # Bad Gateway
    assert "Paystack verification failed" in response.json()["detail"]


async def test_verify_deposit_transaction_not_found(client: TestClient, auth_headers: dict):
    """Test verification of a non-existent deposit transaction."""
    response = client.get("/wallet/deposit/non_existent_ref/verify", headers=auth_headers)
    assert response.status_code == 404
    assert "Deposit transaction not found" in response.json()["detail"]


async def test_verify_deposit_transaction_ownership(client: TestClient, auth_headers: dict, db_session: AsyncSession):
    """Test that users can only verify their own transactions."""
    # 1. Create another user and their transaction
    other_user = User(google_id="other_google", email="other@example.com", name="Other User")
    other_wallet = Wallet(user=other_user, wallet_number="1111111111", balance=0)
    other_tx = Transaction(
        wallet_id=other_wallet.id,
        user_id=other_user.id,
        type=TransactionType.DEPOSIT,
        amount=1000,
        status=TransactionStatus.PENDING,
        reference="dep_other_user_ref"
    )
    db_session.add_all([other_user, other_wallet, other_tx])
    await db_session.commit()

    # 2. Try to verify the other user's transaction
    response = client.get("/wallet/deposit/dep_other_user_ref/verify", headers=auth_headers)
    assert response.status_code == 404
    assert "Deposit transaction not found" in response.json()["detail"]
