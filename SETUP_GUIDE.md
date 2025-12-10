# Detailed Setup Guide

This guide provides a comprehensive walkthrough for setting up the Paystack Wallet API project, including details on acquiring the necessary credentials.

## 1. Prerequisites

- **Python 3.10+**: Ensure you have a modern version of Python installed.
- **PostgreSQL**: A running PostgreSQL server is required. You can run this locally, via Docker, or use a cloud provider.
- **Git**: For cloning the repository.
- **Virtual Environment**: It is highly recommended to use a Python virtual environment (`venv`) to manage dependencies.

## 2. Initial Project Setup

### Clone the Repository
```bash
git clone <repository_url>
cd paystack_wallet
```

### Create and Activate Virtual Environment
```bash
# Create the virtual environment
python -m venv .venv

# Activate it
# On Windows
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
```

### Install Dependencies
```bash
pip install -r requirements.txt
```

## 3. Environment Variable Configuration (`.env`)

Create a `.env` file from the example:
```bash
cp .env.example .env
```

Open the `.env` file and configure the following variables:

| Variable                  | Description                                                                                                                               | Example                                                              |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `DATABASE_URL`            | **Required.** Your full PostgreSQL connection string.                                                                                     | `postgresql+asyncpg://postgres:mysecretpassword@localhost:5432/walletdb` |
| `SECRET_KEY`              | **Required.** A strong, secret key for signing JWTs. Generate one with `openssl rand -hex 32`.                                             | `09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7`     |
| `ALGORITHM`               | The algorithm used for JWT signing.                                                                                                       | `HS256`                                                              |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | The lifetime of a JWT access token in minutes.                                                                                            | `30`                                                                 |
| `API_KEY_PREFIX`          | The prefix for all generated API keys.                                                                                                    | `sk_live`                                                            |
| `GOOGLE_CLIENT_ID`        | **Required.** The client ID for your Google OAuth 2.0 application. See below for instructions.                                            | `1234567890-abc.apps.googleusercontent.com`                          |
| `GOOGLE_CLIENT_SECRET`    | **Required.** The client secret for your Google OAuth 2.0 application.                                                                    | `GOCSPX-abcdef123456`                                                |
| `GOOGLE_REDIRECT_URI`     | **Required.** The callback URL for Google OAuth. Must be authorized in your Google project. For local testing, this points to your backend. | `http://localhost:8000/auth/google/callback`                         |
| `PAYSTACK_SECRET_KEY`     | **Required.** Your secret key from the Paystack dashboard.                                                                                | `sk_test_...` or `sk_live_...`                                       |
| `PAYSTACK_WEBHOOK_SECRET` | **Required.** The secret used to verify incoming webhooks from Paystack.                                                                   | `sk_test_...` or any custom string you set in the dashboard.         |

### How to Get Credentials

#### Google OAuth (Client ID & Secret)
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing one.
3. Navigate to **APIs & Services -> Credentials**.
4. Click **+ CREATE CREDENTIALS** and choose **OAuth client ID**.
5. Select **Web application** as the application type.
6. Under **Authorized redirect URIs**, add your backend callback URL (e.g., `http://localhost:8000/auth/google/callback`).
7. Click **Create**. Your Client ID and Client Secret will be displayed. Copy these into your `.env` file.

#### Paystack (Secret Key & Webhook Secret)
1. Log in to your [Paystack Dashboard](https://dashboard.paystack.com/).
2. Go to **Settings -> API Keys & Webhooks**.
3. You will find your **Test Secret Key** and **Live Secret Key**. Copy the appropriate one into `PAYSTACK_SECRET_KEY`.
4. In the **Webhook URL** section, add the URL where your application will be publicly accessible to receive webhooks. For local testing, you'll need a tool like **ngrok** to expose your `localhost:8000` to the internet.
   - Example with ngrok: `https://<your-ngrok-subdomain>.ngrok.io/wallet/paystack/webhook`
5. The **Secret** field on the Paystack dashboard is what you should use for `PAYSTACK_WEBHOOK_SECRET`.

## 4. Database Setup

Ensure your PostgreSQL server is running and that the database specified in your `DATABASE_URL` exists. The application does not create the database for you.

Then, apply the database migrations to create the tables:
```bash
alembic upgrade head
```

## 5. Running the Application

You can now start the FastAPI server:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
The `--reload` flag enables hot-reloading, which is useful for development. The API is now available at `http://localhost:8000`.