# HNG Stage 8 - Paystack Wallet API

This project is a robust backend API for a wallet system that integrates Google Sign-In for user authentication and Paystack for payment processing. It provides a secure and scalable foundation for managing user wallets, deposits, transfers, and programmatic access via API keys.

## Key Features

- **Google OAuth 2.0:** Secure user authentication and registration using Google accounts, with JWTs for session management.
- **Wallet System:** Each user is provided with a unique wallet to store and manage funds.
- **Paystack Integration:** Seamlessly handle wallet deposits using Paystack's payment infrastructure.
- **Webhook Driven:** Wallet balances are updated via mandatory Paystack webhooks, ensuring a reliable and secure transaction flow.
- **Internal Transfers:** Users can instantly transfer funds to other wallets within the system.
- **API Key Management:** Users can generate, manage, and revoke API keys for service-to-service access.
- **Permission System:** API keys can be scoped with specific permissions (`deposit`, `transfer`, `read`) for granular access control.
- **Async Architecture:** Built with FastAPI and SQLAlchemy's async support for high performance.
- **Database Migrations:** Uses Alembic to manage database schema changes.

## API Endpoints

### Authentication
- `GET /auth/google`: Initiate Google sign-in.
- `GET /auth/google/callback`: Handle Google OAuth callback and issue JWT.

### API Key Management
- `POST /keys/create`: Create a new API key.
- `GET /keys`: List all API keys for the user.
- `POST /keys/rollover`: Rollover an expired API key.
- `DELETE /keys/{key_id}`: Revoke an API key.

### Wallet Operations
- `POST /wallet/deposit`: Initiate a deposit into the user's wallet.
- `GET /wallet/deposit/{reference}/status`: Check the status of a deposit.
- `POST /wallet/transfer`: Transfer funds to another user's wallet.
- `GET /wallet/balance`: Get the current wallet balance.
- `GET /wallet/transactions`: Get the user's transaction history.

### Webhooks
- `POST /wallet/paystack/webhook`: Endpoint for receiving Paystack transaction events.

## Tech Stack

- **Framework:** FastAPI
- **Database:** PostgreSQL (with asyncpg)
- **ORM:** SQLAlchemy (async)
- **Migrations:** Alembic
- **Authentication:** python-jose (JWT), Google OAuth
- **Payments:** Paystack

---

For setup and usage instructions, please refer to `SETUP_GUIDE.md` and `QUICKSTART.md`.