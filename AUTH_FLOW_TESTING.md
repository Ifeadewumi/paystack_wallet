# Authentication Flow Testing Guide

## Complete Flow with JWT Authentication

### Step 1: Google Sign-In (Get JWT Token)

**Request:**
```bash
curl http://localhost:8000/auth/google
```

**Response:**
```json
{
  "google_auth_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
}
```

**Action:** Open the URL in browser and sign in with Google

**After redirect, you'll get:**
```json
{
  "user_id": "uuid",
  "email": "user@gmail.com",
  "name": "User Name",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**SAVE THE `access_token`** - you'll need it for payment!

---

### Step 2: Initiate Payment (Protected - Requires Token)

**Request:**
```bash
curl -X POST http://localhost:8000/payments/paystack/initiate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN_HERE" \
  -d '{"amount": 5000}'
```

**Notice:**
- ✅ Only needs `amount` (no email!)
- ✅ Requires `Authorization` header with JWT token
- ✅ Email automatically taken from authenticated user

**Response:**
```json
{
  "reference": "txn_abc123",
  "authorization_url": "https://checkout.paystack.com/..."
}
```

---

### Step 3: Test Without Authentication (Should Fail)

**Request:**
```bash
curl -X POST http://localhost:8000/payments/paystack/initiate \
  -H "Content-Type: application/json" \
  -d '{"amount": 5000}'
```

**Expected Response (401 Unauthorized):**
```json
{
  "detail": "Not authenticated"
}
```

This proves the endpoint is **protected**! ✅

---

## Using Swagger UI (http://localhost:8000/docs)

### Step 1: Sign in with Google
1. Expand `GET /auth/google`
2. Try it out → Execute
3. Copy the URL and open in browser
4. Sign in with Google
5. **Copy the `access_token` from response**

### Step 2: Authorize in Swagger
1. Click the **"Authorize"** button (🔒 icon) at top right
2. Enter: `YOUR_ACCESS_TOKEN_HERE` (just the token, no "Bearer")
3. Click "Authorize"
4. Click "Close"

### Step 3: Make Authenticated Payment
1. Expand `POST /payments/paystack/initiate`
2. Try it out
3. Enter only: `{"amount": 5000}`
4. Execute
5. ✅ Success! Email automatically used from your account

---

## What Changed

### Before (Broken):
- ❌ No authentication
- ❌ Anyone could initiate payment
- ❌ Had to manually provide email
- ❌ No session management

### After (Fixed):
- ✅ JWT token authentication
- ✅ Protected payment endpoint
- ✅ Email from authenticated user
- ✅ Proper session management
- ✅ Tokens expire after 30 minutes

---

## Testing Checklist

- [ ] Sign in with Google → Get JWT token
- [ ] Use token to initiate payment (only amount)
- [ ] Try payment without token → Get 401 error
- [ ] Check transaction is linked to user in database
- [ ] Token expires after 30 minutes

---

## Database Check

```sql
-- See user and their transactions
SELECT u.email, t.reference, t.amount, t.status 
FROM users u 
LEFT JOIN transactions t ON u.id = t.user_id;
```

Now transactions are **linked to users**! ✅
