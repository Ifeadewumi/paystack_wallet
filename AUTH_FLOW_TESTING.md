# Authentication Flow Testing Guide

This document outlines the steps to manually test the different authentication flows supported by the API: Google OAuth2, JWT Bearer Tokens, and API Keys.

You can perform these tests using the interactive API docs at `http://localhost:8000/docs` or a tool like `curl` or Postman.

## Flow 1: Google OAuth2 and JWT Generation

This flow describes how a user signs in for the first time and gets a JWT access token.

1.  **Initiate Google Sign-In**
    -   Make a `GET` request to `/auth/google`.
    -   The response will be a JSON object containing a URL.
    ```json
    {
      "google_auth_url": "https://accounts.google.com/o/oauth2/v2/auth?..."
    }
    ```

2.  **Authorize via Browser**
    -   Copy the `google_auth_url` and paste it into your web browser.
    -   Log in with a valid Google account and grant the requested permissions.

3.  **Handle the Callback**
    -   After authorization, Google will redirect your browser to the `redirect_uri` specified in your configuration (`http://localhost:8000/auth/google/callback`) with a `code` in the query string.
    -   Since this is a backend service, your browser will likely show a "Not Found" or similar error if you are not running a frontend, but the backend will have already processed the request.
    -   The backend exchanges this code for user information, creates a user and wallet (if new), and generates a JWT.
    -   **To capture the token**, you can either:
        -   Use browser developer tools to inspect the network response of the `/auth/google/callback` request.
        -   Temporarily modify the `google_callback` function in `app/routers/auth.py` to print the token or return it in a more accessible way for testing.

    The final response from the callback is a JSON object with your access token:
    ```json
    {
      "user_id": "some-uuid-string",
      "email": "user@example.com",
      "name": "Test User",
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "token_type": "bearer"
    }
    ```

## Flow 2: Accessing Protected Endpoints with a JWT

Once you have an `access_token`, you can use it to authenticate as a user.

1.  **Prepare the Request**
    -   Choose a protected endpoint, for example, `GET /wallet/balance`.
    -   Create an `Authorization` header with the value `Bearer <your_access_token>`.

2.  **Make the API Call**
    -   Using `curl`:
    ```bash
    curl -X GET "http://localhost:8000/wallet/balance" \
         -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    ```
    -   Using the API docs (`/docs`), click the "Authorize" button and paste your token in the format `Bearer <token>`. Then, you can use the "Try it out" feature on any endpoint.

## Flow 3: API Key Generation and Usage

This flow describes how to create and use an API key for service-to-service authentication.

1.  **Create an API Key**
    -   First, authenticate as a user with a JWT (as described in Flow 2).
    -   Make a `POST` request to `/keys/create` with a request body specifying the key's name and permissions.
    ```bash
    curl -X POST "http://localhost:8000/keys/create" \
         -H "Authorization: Bearer <your_jwt>" \
         -H "Content-Type: application/json" \
         -d '{
               "name": "MyTestService",
               "permissions": ["read", "deposit"],
               "expiry": "1D"
             }'
    ```
    -   The response will contain your new API key. **Save this key immediately, as it will not be shown again.**
    ```json
    {
      "api_key": "sk_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ...",
      "expires_at": "2025-12-11T18:30:00.123Z"
    }
    ```

2.  **Accessing Endpoints with the API Key**
    -   Choose an endpoint that the key has permission for (e.g., `GET /wallet/balance` with the `read` permission).
    -   Create an `x-api-key` header with the API key you just received.
    -   Make the API call.
    ```bash
    curl -X GET "http://localhost:8000/wallet/balance" \
         -H "x-api-key: sk_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ..."
    ```
    -   This request should succeed. If you try to access an endpoint the key does not have permission for (e.g., `POST /wallet/transfer` without the `transfer` permission), you will receive a `403 Forbidden` error.