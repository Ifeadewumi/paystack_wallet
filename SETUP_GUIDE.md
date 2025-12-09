# Complete Setup Guide - Step by Step

This guide walks you through every step needed to get your FastAPI application running.

## STEP 1: Install Python and PostgreSQL

### Windows:
1. **Install Python**:
   - Download Python 3.9+ from https://www.python.org/downloads/
   - During installation, CHECK "Add Python to PATH"
   - Verify: `python --version`

2. **Install PostgreSQL**:
   - Download from https://www.postgresql.org/download/windows/
   - During installation, remember the password you set for user "postgres"
   - Default port: 5432
   - Verify: `psql --version`

## STEP 2: Set Up Project Directory

```bash
# Navigate to your project folder
cd c:\Code\hng_stage_8

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# You should see (venv) in your terminal prompt
```

## STEP 3: Install Dependencies

```bash
# Make sure virtual environment is activated (you see "venv" in prompt)
pip install -r requirements.txt

# This installs:
# - FastAPI (web framework)
# - Uvicorn (ASGI server)
# - SQLAlchemy (database ORM)
# - Pydantic (data validation)
# - httpx (HTTP client for API calls)
# - asyncpg (PostgreSQL async driver)
# - And more...
```

## STEP 4: Create PostgreSQL Database

```bash
# Open Command Prompt and connect to PostgreSQL
psql -U postgres

# Enter your PostgreSQL password when prompted

# Create the database
CREATE DATABASE hng_stage_8;

# Verify it was created
\l

# Exit psql
\q
```

## STEP 5: Set Up Google OAuth Credentials

### Detailed Steps:

1. **Go to Google Cloud Console**:
   - Visit: https://console.cloud.google.com/

2. **Create a Project**:
   - Click "Select a project" → "New Project"
   - Name it: "HNG Stage 8"
   - Click "Create"

3. **Enable Google+ API**:
   - In the left menu: "APIs & Services" → "Library"
   - Search for "Google+ API"
   - Click on it and press "Enable"

4. **Configure OAuth Consent Screen**:
   - Go to "APIs & Services" → "OAuth consent screen"
   - Choose "External" (for testing)
   - Fill in:
     - App name: "HNG Stage 8"
     - User support email: your email
     - Developer contact: your email
   - Click "Save and Continue"
   - Skip Scopes (click "Save and Continue")
   - Add test users: add your Gmail address
   - Click "Save and Continue"

5. **Create OAuth Credentials**:
   - Go to "APIs & Services" → "Credentials"
   - Click "+ CREATE CREDENTIALS" → "OAuth 2.0 Client ID"
   - Choose "Web application"
   - Name: "HNG Stage 8 Web Client"
   - Under "Authorized redirect URIs", click "+ ADD URI"
   - Add: `http://localhost:8000/auth/google/callback`
   - Click "Create"

6. **Save Your Credentials**:
   - A popup shows your Client ID and Client Secret
   - COPY BOTH - you'll need them for .env file
   - You can also download the JSON (optional)

## STEP 6: Set Up Paystack Account

### Detailed Steps:

1. **Sign Up for Paystack**:
   - Visit: https://paystack.com/
   - Click "Get Started" and create account
   - Verify your email

2. **Get Test API Keys**:
   - Log into your Paystack dashboard
   - Go to "Settings" (bottom left) → "API Keys & Webhooks"
   - Copy your **Test Secret Key** (starts with `sk_test_...`)
   - NEVER use live keys for development!

3. **Get Webhook Secret** (Optional but recommended):
   - In same section, scroll to "Webhooks"
   - The webhook secret is shown there
   - Copy it for later use

Note: For development/testing, we'll use Paystack's test mode. No real money will be charged.

## STEP 7: Configure Environment Variables

```bash
# Copy the example file
cp .env.example .env

# Now edit .env file with a text editor
# Replace ALL placeholder values with your actual credentials
```

### Your .env file should look like this:

```env
# Database - Update password if you set a different one
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_POSTGRES_PASSWORD@localhost:5432/hng_stage_8

# Google OAuth - Paste values from Google Cloud Console
GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-your_actual_secret_here
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Paystack - Paste your test keys from Paystack dashboard
PAYSTACK_SECRET_KEY=sk_test_your_actual_test_key_here
PAYSTACK_WEBHOOK_SECRET=your_webhook_secret_here

# Application - Generate a random string
APP_SECRET_KEY=some_random_long_string_here_12345
```

### Generate APP_SECRET_KEY:
```bash
# In Python terminal:
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## STEP 8: Run the Application

```bash
# Make sure you're in project root and venv is activated
cd c:\Code\hng_stage_8
venv\Scripts\activate

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

## STEP 9: Test the API

### Option 1: Using Browser

1. **Open your browser** and go to: http://localhost:8000/docs
   - This opens the interactive API documentation (Swagger UI)

2. **Test Google Auth**:
   - Find "GET /auth/google" endpoint
   - Click "Try it out" → "Execute"
   - Copy the `google_auth_url` from response
   - Open that URL in a new tab
   - Sign in with Google
   - You'll be redirected back with user data

3. **Test Payment**:
   - Find "POST /payments/paystack/initiate" endpoint
   - Click "Try it out"
   - Enter amount: `5000` (this is 50 NGN in kobo)
   - Click "Execute"
   - Copy the `authorization_url`
   - Open it in browser to see Paystack checkout page

### Option 2: Using cURL (Command Line)

```bash
# Test Google Auth URL
curl http://localhost:8000/auth/google

# Test Payment Initiation
curl -X POST http://localhost:8000/payments/paystack/initiate \
  -H "Content-Type: application/json" \
  -d "{\"amount\": 5000}"

# Check transaction status (replace {reference} with actual reference)
curl http://localhost:8000/payments/{reference}/status
```

### Option 3: Using Postman or Insomnia

Import these requests:

**Request 1: Get Google Auth URL**
- Method: GET
- URL: http://localhost:8000/auth/google

**Request 2: Initiate Payment**
- Method: POST
- URL: http://localhost:8000/payments/paystack/initiate
- Body (JSON):
```json
{
  "amount": 5000
}
```

**Request 3: Check Status**
- Method: GET
- URL: http://localhost:8000/payments/{reference}/status?refresh=true

## STEP 10: Understanding the Database

After running the app, check your database:

```bash
# Connect to PostgreSQL
psql -U postgres -d hng_stage_8

# View tables
\dt

# You should see:
# - users
# - transactions

# View users
SELECT * FROM users;

# View transactions
SELECT * FROM transactions;

# Exit
\q
```

## Common Issues and Fixes

### Issue 1: "Module not found" error
**Solution**: Make sure virtual environment is activated and dependencies are installed
```bash
venv\Scripts\activate
pip install -r requirements.txt
```

### Issue 2: Database connection error
**Solution**: Check PostgreSQL is running and credentials in .env are correct
```bash
# Check if PostgreSQL is running
pg_isready

# Test connection
psql -U postgres -d hng_stage_8
```

### Issue 3: Google OAuth error "redirect_uri_mismatch"
**Solution**: Make sure redirect URI in Google Console exactly matches:
`http://localhost:8000/auth/google/callback`

### Issue 4: Port 8000 already in use
**Solution**: Use a different port or kill the process
```bash
# Use different port
uvicorn app.main:app --reload --port 8001

# Or find and kill process on port 8000 (Windows)
netstat -ano | findstr :8000
taskkill /PID <process_id> /F
```

### Issue 5: Paystack webhook not receiving events
**Solution**: For local testing, you need to expose your local server to internet using tools like:
- ngrok: https://ngrok.com/
- localtunnel: https://localtunnel.github.io/www/

```bash
# Using ngrok (after installing)
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
# Update Paystack webhook URL to: https://abc123.ngrok.io/payments/paystack/webhook
```

## Testing Payment Flow End-to-End

1. **Start your server**: `uvicorn app.main:app --reload`

2. **Initiate payment** via API or Swagger docs

3. **Get authorization URL** from response

4. **Open URL in browser** - you'll see Paystack checkout page

5. **Use Paystack test card**:
   - Card Number: `4084 0840 8408 4081`
   - Expiry: Any future date (e.g., 12/25)
   - CVV: `408`
   - PIN: `0000`
   - OTP: `123456`

6. **Complete payment** - Paystack will process it

7. **Check status** via API:
   ```bash
   curl http://localhost:8000/payments/{reference}/status?refresh=true
   ```

8. **Status should be "success"**

## What Each File Does

- **`app/main.py`**: Entry point, creates FastAPI app, includes routers
- **`app/config.py`**: Loads environment variables from .env
- **`app/database.py`**: Sets up database connection and sessions
- **`app/models.py`**: Defines database tables (User, Transaction)
- **`app/schemas.py`**: Defines API request/response formats
- **`app/routers/auth.py`**: Handles Google OAuth endpoints
- **`app/routers/payments.py`**: Handles Paystack payment endpoints
- **`requirements.txt`**: Lists all Python packages needed
- **`.env`**: Stores secret credentials (never commit to Git!)

## Next Steps

1. ✅ Read through the code to understand how it works
2. ✅ Test all endpoints thoroughly
3. ✅ Try error scenarios (invalid amount, wrong reference, etc.)
4. ✅ Check database after each operation
5. ✅ Deploy to a cloud platform (Heroku, Railway, DigitalOcean)

## Need Help?

- FastAPI Documentation: https://fastapi.tiangolo.com/
- SQLAlchemy Docs: https://docs.sqlalchemy.org/
- Paystack API Docs: https://paystack.com/docs/api/
- Google OAuth Docs: https://developers.google.com/identity/protocols/oauth2

Good luck with your HNG Stage 8 task! 🚀
