# Design Document

## Overview

The Paystack Wallet Application is a FastAPI-based backend system that provides secure wallet management with Google OAuth authentication, Paystack payment integration, and granular API key-based access control. The system enables users to deposit funds via Paystack, transfer money between wallets, and allows services to interact with wallets through permission-scoped API keys.

The architecture follows a layered approach with clear separation between routing, business logic, data access, and authentication. The system uses PostgreSQL with SQLAlchemy ORM for data persistence and implements row-level locking for concurrent transaction safety.

## Architecture

### Technology Stack

- **Framework**: FastAPI (async Python web framework)
- **Database**: PostgreSQL with asyncpg driver
- **ORM**: SQLAlchemy 2.0 (async)
- **Authentication**: JWT (python-jose) and custom API key system
- **Payment Gateway**: Paystack REST API
- **HTTP Client**: httpx (async)

### Layered Architecture

```
┌─────────────────────────────────────────┐
│         FastAPI Application             │
│  (main.py, CORS, OpenAPI, Lifespan)    │
└─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼────────┐    ┌────────▼────────┐
│    Routers     │    │  Auth Utilities │
│  (auth, keys,  │    │  (JWT, API Key, │
│    wallet)     │    │   Permissions)  │
└───────┬────────┘    └────────┬────────┘
        │                      │
        └──────────┬───────────┘
                   │
        ┌──────────▼──────────┐
        │  Business Services  │
        │  (wallet_service)   │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │   Data Access Layer │
        │  (models, database) │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │    PostgreSQL DB    │
        └─────────────────────┘
```

### External Integrations

1. **Google OAuth 2.0**: User authentication and profile retrieval
2. **Paystack API**: Payment initialization and transaction processing
3. **Paystack Webhooks**: Asynchronous payment confirmation

## Components and Interfaces

### 1. Authentication Module (`auth_utils.py`)

**Purpose**: Handles JWT and API key authentication, permission validation

**Key Functions**:
- `create_access_token(data, expires_delta)`: Generates JWT tokens
- `get_current_user(token, db)`: Validates JWT and retrieves user
- `hash_api_key(api_key)`: Creates SHA256 hash of API keys
- `get_user_from_api_key(api_key, db)`: Validates API key and retrieves user with permissions
- `get_current_user_with_permissions(authorization, x_api_key, db)`: Unified auth dependency supporting both JWT and API keys
- `check_permission(required_permission, permissions)`: Validates user has required permission

**Interface**:
```python
async def get_current_user_with_permissions(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Tuple[User, List[str]]
```

### 2. Wallet Service (`wallet_service.py`)

**Purpose**: Encapsulates wallet business logic with transaction safety

**Key Functions**:
- `credit_wallet(db, transaction)`: Atomically credits wallet from webhook
- `transfer_funds(db, sender_user_id, recipient_wallet_number, amount)`: Atomically transfers between wallets

**Interface**:
```python
async def credit_wallet(db: AsyncSession, transaction: Transaction) -> None
async def transfer_funds(
    db: AsyncSession,
    sender_user_id: str,
    recipient_wallet_number: str,
    amount: int
) -> Tuple[Wallet, Wallet]
```

### 3. Authentication Router (`routers/auth.py`)

**Endpoints**:
- `GET /auth/google`: Returns Google OAuth URL
- `GET /auth/google/callback`: Handles OAuth callback, creates/updates user, returns JWT

**Flow**:
1. User requests `/auth/google` → receives Google consent URL
2. User authenticates with Google → redirected to `/auth/google/callback?code=...`
3. System exchanges code for Google access token
4. System fetches user info from Google
5. System creates or updates user record
6. System creates wallet for new users
7. System returns JWT token

### 4. API Key Router (`routers/keys.py`)

**Endpoints**:
- `POST /keys/create`: Creates new API key (JWT auth only)
- `POST /keys/rollover`: Rolls over expired key (JWT auth only)
- `GET /keys/`: Lists all user's API keys (JWT auth only)
- `DELETE /keys/{key_id}`: Revokes API key (JWT auth only)

**Key Generation**:
```python
random_part = secrets.token_urlsafe(32)  # Cryptographically secure
plain_api_key = f"{prefix}_{random_part}"
key_prefix = random_part[:8]  # For database lookup
key_hash = sha256(plain_api_key)  # Stored in database
```

### 5. Wallet Router (`routers/wallet.py`)

**Endpoints**:
- `POST /wallet/deposit`: Initializes Paystack deposit (JWT or API key with deposit permission)
- `POST /wallet/paystack/webhook`: Receives Paystack webhooks (signature verified)
- `GET /wallet/deposit/{reference}/status`: Checks deposit status (JWT or API key with read permission)
- `GET /wallet/balance`: Returns wallet balance (JWT or API key with read permission)
- `POST /wallet/transfer`: Transfers between wallets (JWT or API key with transfer permission)
- `GET /wallet/transactions`: Returns transaction history (JWT or API key with read permission)

## Data Models

### User Model
```python
class User:
    id: UUID (PK)
    email: String (unique, indexed)
    name: String (nullable)
    picture: String (nullable)
    google_id: String (unique, indexed)
    created_at: DateTime
    updated_at: DateTime
    
    # Relationships
    wallet: Wallet (one-to-one)
    api_keys: List[ApiKey] (one-to-many)
    transactions: List[Transaction] (one-to-many)
```

### Wallet Model
```python
class Wallet:
    id: UUID (PK)
    user_id: UUID (FK to User, unique)
    wallet_number: String (unique, indexed)
    balance: BigInteger (in kobo, default 0)
    created_at: DateTime
    updated_at: DateTime
    
    # Relationships
    user: User
    transactions: List[Transaction]
```

### Transaction Model
```python
class Transaction:
    id: UUID (PK)
    wallet_id: UUID (FK to Wallet)
    user_id: UUID (FK to User)
    type: Enum[DEPOSIT, TRANSFER]
    amount: BigInteger (in kobo)
    status: Enum[PENDING, SUCCESS, FAILED]
    reference: String (unique, indexed)
    description: String (nullable)
    authorization_url: String (nullable)
    paid_at: DateTime (nullable)
    created_at: DateTime
    updated_at: DateTime
```

### ApiKey Model
```python
class ApiKey:
    id: UUID (PK)
    user_id: UUID (FK to User)
    key_hash: String (unique, SHA256 of plain key)
    key_prefix: String (indexed, first 8 chars for lookup)
    name: String
    permissions: JSON (array of: deposit, transfer, read)
    expires_at: DateTime
    is_active: Boolean (default True)
    created_at: DateTime
    updated_at: DateTime
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Wallet creation accompanies user creation
*For any* new User created through Google authentication, a Wallet should be created with a unique wallet_number and zero balance.
**Validates: Requirements 2.1, 2.2, 2.3**

### Property 2: Deposit reference uniqueness
*For any* two deposit transactions, their references should be different and follow the "dep_" prefix pattern.
**Validates: Requirements 16.1, 16.3, 16.4**

### Property 3: Transfer reference uniqueness
*For any* two transfer operations, their references should be different and follow the "xfer_" prefix pattern.
**Validates: Requirements 16.2, 16.3, 16.4**

### Property 4: Webhook idempotency
*For any* webhook event received multiple times with the same reference, the wallet should only be credited once.
**Validates: Requirements 4.6**

### Property 5: Transfer atomicity and balance consistency
*For any* valid transfer of amount A from sender to recipient, either both the sender's debit and recipient's credit complete successfully (and the sum of balance changes equals zero), or neither occurs.
**Validates: Requirements 7.6, 7.7, 7.10**

### Property 6: Insufficient balance rejection
*For any* transfer request where the sender's balance is less than the transfer amount, the transfer should be rejected and no balances should change.
**Validates: Requirements 7.3**

### Property 7: API key count limit enforcement
*For any* User, the count of active non-expired API keys should never exceed 5, and attempts to create a 6th key should be rejected.
**Validates: Requirements 9.2**

### Property 8: API key hash verification
*For any* API key authentication attempt, the SHA256 hash of the provided key should match the stored key_hash for authentication to succeed.
**Validates: Requirements 9.7, 13.4**

### Property 9: Expired API key rejection
*For any* API key where expires_at is in the past, authentication attempts should fail with a forbidden error.
**Validates: Requirements 13.6**

### Property 10: Inactive API key rejection
*For any* API key where is_active is false, authentication attempts should fail with a forbidden error.
**Validates: Requirements 13.5**

### Property 11: Permission enforcement for deposit operations
*For any* deposit endpoint request authenticated with an API key lacking deposit permission, the request should be rejected with a forbidden error.
**Validates: Requirements 15.1**

### Property 12: Permission enforcement for transfer operations
*For any* transfer endpoint request authenticated with an API key lacking transfer permission, the request should be rejected with a forbidden error.
**Validates: Requirements 15.2**

### Property 13: Permission enforcement for read operations
*For any* read endpoint request authenticated with an API key lacking read permission, the request should be rejected with a forbidden error.
**Validates: Requirements 15.3**

### Property 14: JWT grants all permissions
*For any* request authenticated with a valid JWT, the user should have all permissions (deposit, transfer, read).
**Validates: Requirements 14.4**

### Property 15: API key permissions are scoped
*For any* API key authentication, only the permissions explicitly assigned to that API key should be granted.
**Validates: Requirements 14.5**

### Property 16: Webhook signature validation
*For any* webhook request, if the computed HMAC SHA512 signature does not match the x-paystack-signature header, the request should be rejected.
**Validates: Requirements 4.3**

### Property 17: Transaction history ordering
*For any* transaction history request, transactions should be ordered by created_at in descending order (newest first).
**Validates: Requirements 8.2**

### Property 18: Deposit status read-only
*For any* deposit status check, the Transaction and Wallet balance should remain unchanged after the operation.
**Validates: Requirements 5.3**

### Property 19: Transaction ownership verification
*For any* deposit status request, only the User who owns the Transaction should be able to view it.
**Validates: Requirements 5.1**

### Property 20: API key rollover preserves permissions
*For any* API key rollover operation, the new API key should have the same name and permissions as the expired key.
**Validates: Requirements 10.5**

### Property 21: Expiry duration conversion accuracy
*For any* API key creation with expiry duration (1H, 1D, 1M, 1Y), the expires_at datetime should be correctly calculated from the current time.
**Validates: Requirements 9.5**

### Property 22: Positive amount validation for deposits
*For any* deposit request with amount less than or equal to zero, the request should be rejected.
**Validates: Requirements 3.1**

### Property 23: Positive amount validation for transfers
*For any* transfer request with amount less than or equal to zero, the request should be rejected.
**Validates: Requirements 7.1**

### Property 24: Transfer creates dual transaction records
*For any* successful transfer, exactly two Transaction records should be created: one debit for the sender and one credit for the recipient.
**Validates: Requirements 7.8**

### Property 25: API key authorization for rollover
*For any* API key rollover request, the expired_key_id must belong to the requesting User, otherwise the request should be rejected.
**Validates: Requirements 10.2**

### Property 26: API key authorization for revocation
*For any* API key revocation request, the key_id must belong to the requesting User, otherwise the request should be rejected.
**Validates: Requirements 12.2**

## Error Handling

### Error Categories

1. **Authentication Errors (401)**
   - Invalid JWT token
   - Invalid API key
   - Missing authentication credentials

2. **Authorization Errors (403)**
   - Expired API key
   - Inactive API key
   - Insufficient permissions

3. **Validation Errors (400)**
   - Invalid amount (zero or negative)
   - Insufficient balance
   - Same wallet transfer
   - API key not expired (for rollover)
   - Maximum API keys reached

4. **Not Found Errors (404)**
   - User not found
   - Wallet not found
   - Transaction not found
   - API key not found

5. **Payment Errors (402)**
   - Paystack initialization failure
   - Paystack API errors

6. **External Service Errors (502)**
   - Google OAuth communication failure

### Error Response Format

All errors follow FastAPI's HTTPException format:
```json
{
  "detail": "Descriptive error message"
}
```

### Idempotency Strategy

1. **Webhook Processing**: Check transaction status before crediting
2. **Transaction References**: Use UUID-based unique references
3. **Database Constraints**: Unique constraints on references and wallet numbers
4. **Row Locking**: Use `with_for_update()` for concurrent operations

## Testing Strategy

### Unit Testing

**Framework**: pytest with pytest-asyncio

**Coverage Areas**:
1. **Authentication Functions**
   - JWT token creation and validation
   - API key hashing and verification
   - Permission checking logic

2. **Wallet Service Functions**
   - Credit wallet logic
   - Transfer funds logic
   - Balance calculations

3. **Utility Functions**
   - Expiry duration calculation
   - Reference generation
   - Signature verification

**Example Unit Tests**:
- Test JWT token contains correct user ID
- Test API key hash matches expected SHA256
- Test permission check rejects missing permissions
- Test expiry calculation for each duration (1H, 1D, 1M, 1Y)

### Property-Based Testing

**Framework**: Hypothesis (Python property-based testing library)

**Configuration**: Each property test should run a minimum of 100 iterations

**Test Tagging**: Each property-based test must include a comment with the format:
```python
# Feature: paystack-wallet-compliance, Property X: <property description>
```

**Property Tests to Implement**:

1. **Property 1: Wallet creation accompanies user creation**
   - Generate random user data
   - Create user through auth flow
   - Verify wallet exists with unique wallet_number and zero balance

2. **Property 2 & 3: Transaction reference uniqueness**
   - Generate multiple transactions
   - Verify all references are unique
   - Verify references follow correct prefix pattern

3. **Property 4: Webhook idempotency**
   - Create pending transaction
   - Send same webhook multiple times
   - Verify wallet credited only once

4. **Property 5 & 6: Transfer atomicity and balance consistency**
   - Generate random sender and recipient wallets with random balances
   - Perform transfer
   - Verify sum of balance changes equals zero
   - Verify both transaction records created or neither

5. **Property 7: Insufficient balance rejection**
   - Generate wallet with random balance
   - Attempt transfer of amount greater than balance
   - Verify rejection and no balance change

6. **Property 8: API key count limit**
   - Create user
   - Attempt to create 6 API keys
   - Verify 6th creation fails

7. **Property 9: API key hash verification**
   - Generate random API key
   - Verify stored hash matches SHA256 of plain key

8. **Property 10: Expired API key rejection**
   - Create API key with past expiry date
   - Attempt authentication
   - Verify rejection with forbidden error

9. **Property 11: Permission enforcement**
   - Create API key with random subset of permissions
   - Attempt operations requiring each permission
   - Verify only authorized operations succeed

10. **Property 12: JWT grants all permissions**
    - Authenticate with JWT
    - Verify all permissions granted

11. **Property 13: Webhook signature validation**
    - Generate random webhook payload
    - Send with incorrect signature
    - Verify rejection

12. **Property 14: Same wallet transfer rejection**
    - Create wallet
    - Attempt transfer to same wallet_number
    - Verify rejection

13. **Property 15: Transaction history ordering**
    - Create multiple transactions with different timestamps
    - Retrieve history
    - Verify descending order by created_at

### Integration Testing

**Scope**: End-to-end API testing with test database

**Test Scenarios**:
1. Complete Google OAuth flow
2. Deposit initialization and webhook processing
3. Transfer between two users
4. API key lifecycle (create, use, rollover, revoke)
5. Permission-based access control across endpoints

### Manual Testing Checklist

1. Google OAuth flow in browser
2. Paystack payment page redirect
3. Webhook delivery from Paystack test environment
4. API documentation (Swagger UI at `/docs`)

## Security Considerations

### Authentication Security

1. **JWT Tokens**
   - Signed with HS256 algorithm
   - Include expiration time
   - Subject (sub) contains user ID

2. **API Keys**
   - Generated with `secrets.token_urlsafe(32)` (cryptographically secure)
   - Stored as SHA256 hash (never plain text)
   - Prefix-based lookup for performance
   - Expiration enforced on every request

3. **Password Security**
   - No passwords stored (Google OAuth only)

### Payment Security

1. **Webhook Verification**
   - HMAC SHA512 signature validation
   - Constant-time comparison to prevent timing attacks
   - Reject unsigned requests

2. **Paystack Integration**
   - Secret keys stored in environment variables
   - HTTPS-only communication
   - Reference-based idempotency

### Data Security

1. **Database**
   - Connection string in environment variables
   - Row-level locking for concurrent operations
   - Unique constraints on critical fields

2. **CORS**
   - Configured for specific origins in production
   - Credentials support enabled

### Concurrency Safety

1. **Row Locking**: `SELECT ... FOR UPDATE` on wallet operations
2. **Nested Transactions**: Use `db.begin_nested()` for atomic operations
3. **Idempotency**: Status checks before state changes

## Known Issues and Gaps

### Issue 1: Transfer Reference Collision Risk

**Current Implementation**:
```python
reference = f"xfer_{sender_wallet.id}_to_{recipient_wallet.id}"
```

**Problem**: If the same users transfer multiple times, the reference will be identical, causing a unique constraint violation.

**Impact**: Prevents repeat transfers between same users

**Solution**: Use UUID in reference generation:
```python
reference = f"xfer_{uuid.uuid4().hex}"
```

### Issue 2: Missing Paystack Verify Endpoint Fallback

**Current Implementation**: Only webhook updates transaction status

**Gap**: No manual verification endpoint that calls Paystack's verify API

**Impact**: If webhook fails, no way to manually verify payment

**Solution**: Add optional verification logic in status endpoint or separate endpoint

### Issue 3: Transaction Amount Sign Inconsistency

**Current Implementation**: Transfer debits stored as negative amounts

**Gap**: API response examples show positive amounts for all transactions

**Impact**: Frontend may need to handle negative amounts unexpectedly

**Solution**: Consider storing absolute amounts and using transaction type to determine debit/credit

### Issue 4: Missing Config Attributes

**Current Implementation**: `settings.secret_key` and `settings.algorithm` used but not defined in Settings class

**Problem**: Will cause AttributeError at runtime

**Solution**: Add to Settings class:
```python
secret_key: str = Field(alias="app_secret_key")
algorithm: str = "HS256"
access_token_expire_minutes: int = 60
api_key_prefix: str = "sk_live"
```

## Deployment Considerations

### Environment Variables Required

```
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=https://yourdomain.com/auth/google/callback
PAYSTACK_SECRET_KEY=sk_live_...
PAYSTACK_WEBHOOK_SECRET=...
APP_SECRET_KEY=... (for JWT signing)
```

### Database Migrations

Use Alembic for schema migrations (already configured in project)

### Webhook Configuration

Register webhook URL with Paystack: `https://yourdomain.com/wallet/paystack/webhook`

### Health Checks

- `GET /health`: Returns `{"status": "healthy"}`
- Database connection check can be added

### Monitoring Recommendations

1. Log all webhook events
2. Monitor failed transactions
3. Alert on authentication failures
4. Track API key usage by permission
