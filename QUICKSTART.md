# Quick Start - Get Running in 5 Minutes

Follow these steps to get the API running quickly:

## 1. Install Dependencies (2 minutes)

```bash
cd c:\Code\hng_stage_8
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Create Database (1 minute)

```bash
psql -U postgres
# Enter password when prompted
```

In psql:
```sql
CREATE DATABASE hng_stage_8;
\q
```

## 3. Configure .env (2 minutes)

Create `.env` file from `.env.example`:

```bash
cp .env.example .env
```

Edit `.env` and update:
- `DATABASE_URL`: Change password to your PostgreSQL password
- `GOOGLE_CLIENT_ID`: Get from Google Cloud Console
- `GOOGLE_CLIENT_SECRET`: Get from Google Cloud Console
- `PAYSTACK_SECRET_KEY`: Get from Paystack dashboard
- `PAYSTACK_WEBHOOK_SECRET`: Get from Paystack dashboard

**Quick way to get credentials:**

### Google (5 min setup):
1. Go to https://console.cloud.google.com/
2. Create project → Enable Google+ API
3. Create OAuth 2.0 Client ID
4. Add redirect: `http://localhost:8000/auth/google/callback`
5. Copy Client ID and Secret

### Paystack (2 min setup):
1. Sign up at https://paystack.com/
2. Go to Settings → API Keys
3. Copy Test Secret Key (starts with `sk_test_`)

## 4. Run the Server

```bash
uvicorn app.main:app --reload
```

## 5. Test It

Open browser: http://localhost:8000/docs

### Test Google Login:
1. Click on "GET /auth/google"
2. Try it out → Execute
3. Copy the URL from response
4. Open in browser → Sign in with Google

### Test Payment:
1. Click on "POST /payments/paystack/initiate"
2. Try it out
3. Enter amount: `5000` (50 NGN)
4. Execute
5. Copy authorization_url
6. Open in browser → Complete payment with test card:
   - Card: `4084 0840 8408 4081`
   - Expiry: `12/25`
   - CVV: `408`
   - PIN: `0000`
   - OTP: `123456`

## Project Structure Overview

```
app/
├── main.py          → FastAPI app entry point
├── config.py        → Environment variables
├── database.py      → DB connection
├── models.py        → User & Transaction tables
├── schemas.py       → Request/Response formats
└── routers/
    ├── auth.py      → Google OAuth endpoints
    └── payments.py  → Paystack endpoints
```

## All Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/auth/google` | Get Google sign-in URL |
| GET | `/auth/google/callback` | Handle Google callback |
| POST | `/payments/paystack/initiate` | Start payment |
| POST | `/payments/paystack/webhook` | Receive Paystack updates |
| GET | `/payments/{ref}/status` | Check payment status |

## Test Commands

```bash
# Get Google auth URL
curl http://localhost:8000/auth/google

# Initiate payment
curl -X POST http://localhost:8000/payments/paystack/initiate \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000}'

# Check status
curl http://localhost:8000/payments/TXN_REF_HERE/status
```

## Common Errors

| Error | Fix |
|-------|-----|
| Module not found | Activate venv: `venv\Scripts\activate` |
| Database error | Check PostgreSQL is running |
| Port in use | Use different port: `--port 8001` |
| OAuth error | Check redirect URI matches exactly |

## What Happens Step-by-Step

### Google Sign-In:
1. User hits `/auth/google` → Gets OAuth URL
2. User visits URL → Signs in with Google
3. Google redirects to `/auth/google/callback?code=...`
4. Server exchanges code for user info
5. Server saves user to database
6. Returns user data

### Paystack Payment:
1. User hits `/payments/paystack/initiate` with amount
2. Server calls Paystack API → Gets checkout URL
3. Server saves transaction (status: pending)
4. Returns checkout URL to user
5. User completes payment on Paystack
6. Paystack sends webhook → Server updates status
7. User checks `/payments/{ref}/status` → Gets status

## Database Tables

### users
- `id`: UUID
- `email`: User's email
- `name`: Full name
- `google_id`: Google user ID

### transactions
- `reference`: Unique transaction ID
- `amount`: Amount in kobo
- `status`: pending | success | failed
- `authorization_url`: Paystack checkout link

## Need More Detail?

See `SETUP_GUIDE.md` for complete step-by-step instructions.

## Ready to Deploy?

See `README.md` for production deployment checklist.
