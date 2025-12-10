# Quickstart Guide

This guide provides the essential steps to get the Paystack Wallet API running on your local machine for development and testing.

## Prerequisites

- Python 3.10+
- A running PostgreSQL database instance.
- An active virtual environment (e.g., using `venv`).

## 1. Clone the Repository

```bash
git clone <repository_url>
cd paystack_wallet
```

## 2. Install Dependencies

Install all the required Python packages.

```bash
pip install -r requirements.txt
```

## 3. Configure Environment Variables

Create a `.env` file in the project root by copying the example file.

```bash
cp .env.example .env
```

Now, edit the `.env` file and fill in the required values, especially:

- `DATABASE_URL`: Your PostgreSQL connection string.
  - Format: `postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB_NAME`
- `SECRET_KEY`: A long, random string for signing JWTs. You can generate one with `openssl rand -hex 32`.
- `GOOGLE_CLIENT_ID` & `GOOGLE_CLIENT_SECRET`: Your Google OAuth credentials.
- `PAYSTACK_SECRET_KEY`: Your Paystack secret key.
- `PAYSTACK_WEBHOOK_SECRET`: The secret for verifying Paystack webhooks.

## 4. Run Database Migrations

Apply the latest database schema to your PostgreSQL database.

```bash
alembic upgrade head
```

This will create all the necessary tables (`users`, `wallets`, `transactions`, `api_keys`).

## 5. Run the Application

Start the FastAPI server using Uvicorn.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will now be running at `http://localhost:8000`.

## 6. Access the API Docs

Once the server is running, you can access the interactive OpenAPI documentation in your browser at:

[http://localhost:8000/docs](http://localhost:8000/docs)

From the docs, you can explore and test all the API endpoints directly.