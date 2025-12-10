# Requirements Document

## Introduction

This document specifies the requirements for a Paystack-integrated wallet system that enables users to authenticate via Google OAuth, manage digital wallets, perform deposits through Paystack payment gateway, transfer funds between users, and access wallet operations via API keys with granular permissions. The system is designed for service-to-service integration while maintaining security and idempotency.

## Glossary

- **System**: The Paystack Wallet Application backend API
- **User**: An individual authenticated via Google OAuth who owns a wallet
- **Wallet**: A digital account that holds a balance in kobo (Nigerian currency lowest unit)
- **JWT**: JSON Web Token used for user authentication
- **API Key**: A service-to-service authentication credential with specific permissions
- **Paystack**: Third-party payment gateway for processing deposits
- **Transaction**: A record of a financial operation (deposit or transfer)
- **Reference**: A unique identifier for each transaction
- **Webhook**: An HTTP callback from Paystack to notify transaction status
- **Kobo**: The lowest unit of Nigerian Naira currency (100 kobo = 1 Naira)
- **Active API Key**: An API key that is not revoked and has not expired
- **Permission**: A specific operation that an API key is authorized to perform

## Requirements

### Requirement 1: Google OAuth Authentication

**User Story:** As a user, I want to sign in using my Google account, so that I can securely access my wallet without managing separate credentials.

#### Acceptance Criteria

1. WHEN a user requests the Google sign-in URL, THE System SHALL return a valid Google OAuth consent page URL
2. WHEN a user completes Google authentication and returns with an authorization code, THE System SHALL exchange the code for user information from Google
3. WHEN Google authentication succeeds, THE System SHALL create a new User record if the google_id does not exist
4. WHEN Google authentication succeeds for an existing User, THE System SHALL update the User's email, name, and picture fields
5. WHEN a User is successfully authenticated, THE System SHALL generate and return a JWT token with the User's ID as the subject

### Requirement 2: Automatic Wallet Creation

**User Story:** As a new user, I want a wallet to be automatically created when I sign up, so that I can immediately start using wallet features.

#### Acceptance Criteria

1. WHEN a new User is created during Google authentication, THE System SHALL create a Wallet for that User
2. WHEN creating a Wallet, THE System SHALL generate a unique wallet_number
3. WHEN creating a Wallet, THE System SHALL initialize the balance to zero kobo
4. WHEN a Wallet is created, THE System SHALL ensure the wallet_number is unique across all Wallets

### Requirement 3: Paystack Deposit Initialization

**User Story:** As a user, I want to deposit funds into my wallet using Paystack, so that I can increase my wallet balance.

#### Acceptance Criteria

1. WHEN a User or service with deposit permission requests a deposit, THE System SHALL validate that the amount is greater than zero
2. WHEN a deposit request is valid, THE System SHALL generate a unique reference with prefix "dep_"
3. WHEN initiating a deposit, THE System SHALL create a Transaction record with status PENDING
4. WHEN initiating a deposit, THE System SHALL call Paystack's initialize transaction API with the amount, email, reference, and currency
5. WHEN Paystack initialization succeeds, THE System SHALL return the reference and authorization_url to the client
6. WHEN Paystack initialization fails, THE System SHALL delete the pending Transaction record and return an error

### Requirement 4: Paystack Webhook Processing

**User Story:** As the system, I want to receive and process Paystack webhooks securely, so that wallet balances are updated when payments are confirmed.

#### Acceptance Criteria

1. WHEN a webhook request is received, THE System SHALL verify the x-paystack-signature header is present
2. WHEN verifying a webhook, THE System SHALL compute an HMAC SHA512 signature using the webhook secret and request body
3. WHEN the computed signature does not match the provided signature, THE System SHALL reject the webhook with an error
4. WHEN a webhook signature is valid and event type is "charge.success", THE System SHALL locate the Transaction by reference
5. WHEN a Transaction is found and status is PENDING, THE System SHALL credit the Wallet and update the Transaction status to SUCCESS
6. WHEN a Transaction status is already SUCCESS, THE System SHALL not credit the Wallet again (idempotency)
7. WHEN crediting a Wallet, THE System SHALL use row-level locking to prevent race conditions

### Requirement 5: Deposit Status Verification

**User Story:** As a user, I want to check the status of my deposit transaction, so that I can confirm whether my payment was successful.

#### Acceptance Criteria

1. WHEN a User requests deposit status by reference, THE System SHALL verify the Transaction belongs to the requesting User
2. WHEN a deposit status request is made, THE System SHALL return the reference, status, amount, and paid_at timestamp
3. WHEN checking deposit status, THE System SHALL not modify the Transaction or Wallet balance
4. WHEN a Transaction reference does not exist for the User, THE System SHALL return a not found error

### Requirement 6: Wallet Balance Retrieval

**User Story:** As a user, I want to view my current wallet balance, so that I know how much money I have available.

#### Acceptance Criteria

1. WHEN a User or service with read permission requests wallet balance, THE System SHALL return the current balance in kobo
2. WHEN a User does not have a Wallet, THE System SHALL return a not found error

### Requirement 7: Wallet-to-Wallet Transfer

**User Story:** As a user, I want to transfer funds from my wallet to another user's wallet, so that I can send money to other users.

#### Acceptance Criteria

1. WHEN a User requests a transfer, THE System SHALL validate that the amount is greater than zero
2. WHEN processing a transfer, THE System SHALL lock both sender and recipient Wallet rows to prevent race conditions
3. WHEN the sender's balance is less than the transfer amount, THE System SHALL reject the transfer with an insufficient funds error
4. WHEN the recipient wallet_number does not exist, THE System SHALL reject the transfer with a not found error
5. WHEN the sender and recipient are the same Wallet, THE System SHALL reject the transfer with an error
6. WHEN a transfer is valid, THE System SHALL deduct the amount from the sender's Wallet balance
7. WHEN a transfer is valid, THE System SHALL add the amount to the recipient's Wallet balance
8. WHEN a transfer completes, THE System SHALL create two Transaction records: one for the sender (debit) and one for the recipient (credit)
9. WHEN creating transfer Transaction records, THE System SHALL generate a unique reference for the transfer operation
10. WHEN a transfer completes, THE System SHALL commit all changes atomically or rollback on failure

### Requirement 8: Transaction History

**User Story:** As a user, I want to view my transaction history, so that I can track all deposits and transfers in my wallet.

#### Acceptance Criteria

1. WHEN a User or service with read permission requests transaction history, THE System SHALL return all Transactions for the User's Wallet
2. WHEN returning transaction history, THE System SHALL order Transactions by created_at in descending order (newest first)
3. WHEN returning transaction history, THE System SHALL include transaction id, type, amount, status, description, and created_at

### Requirement 9: API Key Creation

**User Story:** As a user, I want to create API keys with specific permissions, so that services can access my wallet on my behalf.

#### Acceptance Criteria

1. WHEN a User requests API key creation, THE System SHALL require JWT authentication (not API key authentication)
2. WHEN creating an API key, THE System SHALL validate that the User has fewer than 5 active API keys
3. WHEN the User has 5 or more active API keys, THE System SHALL reject the creation request
4. WHEN creating an API key, THE System SHALL accept expiry values of 1H, 1D, 1M, or 1Y
5. WHEN creating an API key, THE System SHALL convert the expiry duration to an absolute expires_at datetime
6. WHEN creating an API key, THE System SHALL generate a secure random key with the configured prefix
7. WHEN creating an API key, THE System SHALL store a SHA256 hash of the key (not the plain key)
8. WHEN creating an API key, THE System SHALL store the first 8 characters of the random part as key_prefix for lookup
9. WHEN an API key is created, THE System SHALL return the plain API key and expires_at (this is the only time the plain key is shown)
10. WHEN creating an API key, THE System SHALL store the specified permissions as a JSON array

### Requirement 10: API Key Rollover

**User Story:** As a user, I want to rollover an expired API key into a new one with the same permissions, so that I can maintain service continuity.

#### Acceptance Criteria

1. WHEN a User requests API key rollover, THE System SHALL require JWT authentication
2. WHEN rolling over an API key, THE System SHALL verify the expired_key_id belongs to the requesting User
3. WHEN the specified API key is not expired, THE System SHALL reject the rollover request
4. WHEN rolling over an API key, THE System SHALL deactivate the old API key by setting is_active to false
5. WHEN rolling over an API key, THE System SHALL create a new API key with the same name and permissions as the expired key
6. WHEN rolling over an API key, THE System SHALL apply the new expiry duration to calculate the new expires_at
7. WHEN rollover completes, THE System SHALL return the new plain API key and expires_at

### Requirement 11: API Key Listing

**User Story:** As a user, I want to list all my API keys, so that I can manage and track my service credentials.

#### Acceptance Criteria

1. WHEN a User requests their API keys list, THE System SHALL require JWT authentication
2. WHEN listing API keys, THE System SHALL return all API keys for the User (both active and inactive)
3. WHEN listing API keys, THE System SHALL include id, name, permissions, expires_at, is_active, created_at, and updated_at
4. WHEN listing API keys, THE System SHALL not include the plain API key or key hash

### Requirement 12: API Key Revocation

**User Story:** As a user, I want to revoke an API key, so that it can no longer be used to access my wallet.

#### Acceptance Criteria

1. WHEN a User requests API key revocation, THE System SHALL require JWT authentication
2. WHEN revoking an API key, THE System SHALL verify the key_id belongs to the requesting User
3. WHEN an API key does not exist for the User, THE System SHALL return a not found error
4. WHEN revoking an API key, THE System SHALL set is_active to false
5. WHEN an API key is revoked, THE System SHALL return a success response with no content

### Requirement 13: API Key Authentication

**User Story:** As a service, I want to authenticate using an API key, so that I can access wallet operations without user interaction.

#### Acceptance Criteria

1. WHEN a request includes an x-api-key header, THE System SHALL authenticate using the API key
2. WHEN authenticating with an API key, THE System SHALL verify the key starts with the configured prefix
3. WHEN authenticating with an API key, THE System SHALL lookup the ApiKey by key_prefix
4. WHEN authenticating with an API key, THE System SHALL verify the SHA256 hash matches the stored key_hash
5. WHEN an API key is not active, THE System SHALL reject authentication with a forbidden error
6. WHEN an API key is expired, THE System SHALL reject authentication with a forbidden error
7. WHEN API key authentication succeeds, THE System SHALL load the associated User and permissions

### Requirement 14: Dual Authentication Support

**User Story:** As a developer, I want endpoints to support both JWT and API key authentication, so that users and services can access the same operations.

#### Acceptance Criteria

1. WHEN a request includes an Authorization header with Bearer token, THE System SHALL authenticate using JWT
2. WHEN a request includes an x-api-key header, THE System SHALL authenticate using the API key
3. WHEN a request includes neither authentication method, THE System SHALL reject with an unauthorized error
4. WHEN JWT authentication succeeds, THE System SHALL grant all permissions (deposit, transfer, read)
5. WHEN API key authentication succeeds, THE System SHALL grant only the permissions assigned to that API key

### Requirement 15: Permission-Based Access Control

**User Story:** As the system, I want to enforce permission-based access control, so that API keys can only perform authorized operations.

#### Acceptance Criteria

1. WHEN an endpoint requires deposit permission, THE System SHALL verify the authenticated user has deposit permission
2. WHEN an endpoint requires transfer permission, THE System SHALL verify the authenticated user has transfer permission
3. WHEN an endpoint requires read permission, THE System SHALL verify the authenticated user has read permission
4. WHEN a user lacks the required permission, THE System SHALL reject the request with a forbidden error and specify the missing permission

### Requirement 16: Transaction Reference Uniqueness

**User Story:** As the system, I want all transaction references to be unique, so that transactions can be reliably identified and idempotency is maintained.

#### Acceptance Criteria

1. WHEN creating a deposit Transaction, THE System SHALL generate a reference using "dep_" prefix and a unique identifier
2. WHEN creating a transfer Transaction, THE System SHALL generate a reference using "xfer_" prefix and a unique identifier
3. WHEN a Transaction reference already exists, THE System SHALL prevent creation due to unique constraint
4. WHEN generating transaction references, THE System SHALL ensure uniqueness across all transaction types

### Requirement 17: Error Handling and Validation

**User Story:** As a user or service, I want clear error messages when operations fail, so that I can understand and correct issues.

#### Acceptance Criteria

1. WHEN a request has insufficient balance, THE System SHALL return a 400 error with message "Insufficient funds"
2. WHEN an API key is invalid, THE System SHALL return a 401 error with message "Could not validate credentials"
3. WHEN an API key is expired, THE System SHALL return a 403 error with message "API key has expired"
4. WHEN an API key lacks required permission, THE System SHALL return a 403 error specifying the missing permission
5. WHEN a resource is not found, THE System SHALL return a 404 error with a descriptive message
6. WHEN Paystack initialization fails, THE System SHALL return a 402 error with details from Paystack
