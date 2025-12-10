# Implementation Plan

- [x] 1. Fix critical bugs in existing implementation




  - Fix transfer reference generation to prevent collisions
  - Fix missing config attributes in Settings class
  - _Requirements: 16.2, 16.3_

- [x] 1.1 Fix transfer reference collision bug


  - Update `wallet_service.py` to use UUID-based references instead of wallet ID pattern
  - Change from `f"xfer_{sender_wallet.id}_to_{recipient_wallet.id}"` to `f"xfer_{uuid.uuid4().hex}"`
  - _Requirements: 16.2, 16.3_

- [x] 1.2 Fix missing Settings attributes


  - Add `secret_key`, `algorithm`, `access_token_expire_minutes`, and `api_key_prefix` to Settings class
  - Update `auth_utils.py` to use correct settings attributes
  - _Requirements: 1.5, 9.6_

- [x] 1.3 Write property test for transfer reference uniqueness



  - **Property 3: Transfer reference uniqueness**
  - **Validates: Requirements 16.2, 16.3, 16.4**

- [x] 2. Set up property-based testing framework










  - Install Hypothesis library
  - Create test fixtures for database and authentication
  - Create generators for User, Wallet, Transaction, and ApiKey models
  - _Requirements: All_

- [x] 2.1 Install and configure Hypothesis


  - Add `hypothesis` and `pytest-asyncio` to requirements.txt
  - Configure Hypothesis settings for minimum 100 iterations per test
  - _Requirements: All_

- [x] 2.2 Create test database fixtures


  - Create async test database session fixture
  - Create fixture for test client with database
  - Create cleanup fixtures for test isolation
  - _Requirements: All_

- [x] 2.3 Create data generators for models



  - Write Hypothesis strategy for generating random User data
  - Write Hypothesis strategy for generating random Wallet data
  - Write Hypothesis strategy for generating random Transaction data
  - Write Hypothesis strategy for generating random ApiKey data
  - _Requirements: All_

- [x] 3. Implement property tests for authentication and authorization




  - Test JWT token generation and validation
  - Test API key creation, hashing, and validation
  - Test permission enforcement
  - _Requirements: 1.5, 9.1-9.10, 13.1-13.7, 14.1-14.5, 15.1-15.4_

- [x] 3.1 Write property test for JWT contains correct user ID


  - **Property 14: JWT grants all permissions**
  - **Validates: Requirements 14.4**


- [x] 3.2 Write property test for API key hash verification

  - **Property 8: API key hash verification**
  - **Validates: Requirements 9.7, 13.4**



- [x] 3.3 Write property test for expired API key rejection

  - **Property 9: Expired API key rejection**

  - **Validates: Requirements 13.6**

- [x] 3.4 Write property test for inactive API key rejection

  - **Property 10: Inactive API key rejection**
  - **Validates: Requirements 13.5**


- [x] 3.5 Write property test for API key count limit





  - **Property 7: API key count limit enforcement**
  - **Validates: Requirements 9.2**


- [x] 3.6 Write property test for deposit permission enforcement





  - **Property 11: Permission enforcement for deposit operations**

  - **Validates: Requirements 15.1**

- [x] 3.7 Write property test for transfer permission enforcement

  - **Property 12: Permission enforcement for transfer operations**
  - **Validates: Requirements 15.2**


- [x] 3.8 Write property test for read permission enforcement





  - **Property 13: Permission enforcement for read operations**
  - **Validates: Requirements 15.3**

- [x] 3.9 Write property test for API key permissions scoping





  - **Property 15: API key permissions are scoped**
  - **Validates: Requirements 14.5**

- [x] 3.10 Write property test for expiry duration conversion




  - **Property 21: Expiry duration conversion accuracy**
  - **Validates: Requirements 9.5**

- [x] 4. Implement property tests for wallet and user creation





  - Test wallet creation on user registration
  - Test wallet number uniqueness
  - Test initial balance is zero
  - _Requirements: 2.1-2.4_

- [x] 4.1 Write property test for wallet creation with user


  - **Property 1: Wallet creation accompanies user creation**
  - **Validates: Requirements 2.1, 2.2, 2.3**

- [x] 5. Implement property tests for deposit operations





  - Test deposit reference uniqueness
  - Test deposit amount validation
  - Test pending transaction creation
  - _Requirements: 3.1-3.3, 16.1_

- [x] 5.1 Write property test for deposit reference uniqueness


  - **Property 2: Deposit reference uniqueness**
  - **Validates: Requirements 16.1, 16.3, 16.4**

- [x] 5.2 Write property test for positive amount validation


  - **Property 22: Positive amount validation for deposits**
  - **Validates: Requirements 3.1**

- [x] 6. Implement property tests for webhook processing





  - Test webhook signature validation
  - Test webhook idempotency
  - Test wallet crediting logic
  - _Requirements: 4.1-4.6_

- [x] 6.1 Write property test for webhook signature validation


  - **Property 16: Webhook signature validation**
  - **Validates: Requirements 4.3**

- [x] 6.2 Write property test for webhook idempotency


  - **Property 4: Webhook idempotency**
  - **Validates: Requirements 4.6**

- [x] 7. Implement property tests for deposit status checking





  - Test transaction ownership verification
  - Test read-only behavior (no state changes)
  - Test response format
  - _Requirements: 5.1-5.3_

- [x] 7.1 Write property test for transaction ownership verification


  - **Property 19: Transaction ownership verification**
  - **Validates: Requirements 5.1**

- [x] 7.2 Write property test for deposit status read-only


  - **Property 18: Deposit status read-only**
  - **Validates: Requirements 5.3**

- [x] 8. Implement property tests for wallet transfers





  - Test transfer amount validation
  - Test insufficient balance rejection
  - Test balance consistency
  - Test atomicity
  - Test dual transaction record creation
  - _Requirements: 7.1, 7.3, 7.6-7.10_

- [x] 8.1 Write property test for transfer amount validation


  - **Property 23: Positive amount validation for transfers**
  - **Validates: Requirements 7.1**

- [x] 8.2 Write property test for insufficient balance rejection


  - **Property 6: Insufficient balance rejection**
  - **Validates: Requirements 7.3**


- [x] 8.3 Write property test for transfer atomicity and balance consistency

  - **Property 5: Transfer atomicity and balance consistency**
  - **Validates: Requirements 7.6, 7.7, 7.10**

- [x] 8.4 Write property test for dual transaction record creation


  - **Property 24: Transfer creates dual transaction records**
  - **Validates: Requirements 7.8**

- [x] 9. Implement property tests for transaction history




  - Test transaction ordering
  - Test response format
  - Test filtering by wallet
  - _Requirements: 8.1-8.3_

- [x] 9.1 Write property test for transaction history ordering


  - **Property 17: Transaction history ordering**
  - **Validates: Requirements 8.2**

- [x] 10. Implement property tests for API key management





  - Test API key rollover preserves permissions
  - Test API key authorization for rollover
  - Test API key authorization for revocation
  - _Requirements: 10.2, 10.5, 12.2_

- [x] 10.1 Write property test for API key rollover preserves permissions


  - **Property 20: API key rollover preserves permissions**
  - **Validates: Requirements 10.5**

- [x] 10.2 Write property test for API key rollover authorization


  - **Property 25: API key authorization for rollover**
  - **Validates: Requirements 10.2**

- [x] 10.3 Write property test for API key revocation authorization




  - **Property 26: API key authorization for revocation**
  - **Validates: Requirements 12.2**

- [x] 11. Checkpoint - Ensure all tests pass





  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Add optional Paystack verify endpoint fallback





  - Create endpoint that calls Paystack verify API
  - Implement as alternative to webhook for manual verification
  - _Requirements: 5.1-5.4_

- [x] 12.1 Implement Paystack verify API integration


  - Add function to call Paystack's transaction verify endpoint
  - Parse and return verification response
  - _Requirements: 5.1-5.4_

- [x] 12.2 Add verify endpoint or enhance status endpoint


  - Either create new `/wallet/deposit/{reference}/verify` endpoint
  - Or enhance existing status endpoint to optionally call Paystack verify
  - Ensure endpoint does not credit wallet (read-only)
  - _Requirements: 5.1-5.4_

- [x] 12.3 Write unit test for Paystack verify integration


  - Mock Paystack verify API
  - Test successful verification response
  - Test failed verification response
  - _Requirements: 5.1-5.4_

- [x] 13. Add comprehensive error handling tests





  - Test all error scenarios return correct status codes
  - Test error messages are descriptive
  - _Requirements: 17.1-17.6_

- [x] 13.1 Write unit tests for error responses



  - Test insufficient balance returns 400 with correct message
  - Test invalid API key returns 401 with correct message
  - Test expired API key returns 403 with correct message
  - Test missing permission returns 403 with permission name
  - Test not found returns 404 with descriptive message
  - Test Paystack failure returns 402 with details
  - _Requirements: 17.1-17.6_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Documentation and deployment preparation
  - Update README with setup instructions
  - Document environment variables
  - Document API endpoints
  - Create deployment checklist
  - _Requirements: All_

- [ ] 15.1 Update README documentation
  - Add comprehensive setup instructions
  - Document all environment variables with examples
  - Add API endpoint documentation with examples
  - Add troubleshooting section
  - _Requirements: All_

- [ ] 15.2 Create deployment checklist
  - Document Paystack webhook registration steps
  - Document database migration steps
  - Document environment configuration for production
  - Add health check and monitoring recommendations
  - _Requirements: All_
