"""
Test Script for HNG Stage 8 API
This script tests all endpoints to verify everything works correctly.
"""

import httpx
import asyncio
import json
from datetime import datetime


BASE_URL = "http://localhost:8000"


async def test_health_check():
    """Test if server is running"""
    print("\n" + "="*60)
    print("TEST 1: Health Check")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/health")
            print(f"✅ Status: {response.status_code}")
            print(f"Response: {response.json()}")
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            print("Make sure the server is running: uvicorn app.main:app --reload")
            return False


async def test_google_auth_url():
    """Test Google OAuth URL generation"""
    print("\n" + "="*60)
    print("TEST 2: Google OAuth URL Generation")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/auth/google")
            print(f"✅ Status: {response.status_code}")
            data = response.json()
            print(f"Google Auth URL generated: {data.get('google_auth_url', '')[:80]}...")
            
            # Verify URL structure
            url = data.get('google_auth_url', '')
            if 'accounts.google.com' in url and 'client_id' in url:
                print("✅ URL structure is valid")
                return True
            else:
                print("❌ URL structure invalid")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_payment_initiation():
    """Test Paystack payment initiation"""
    print("\n" + "="*60)
    print("TEST 3: Paystack Payment Initiation")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        try:
            payload = {"amount": 5000}
            response = await client.post(
                f"{BASE_URL}/payments/paystack/initiate",
                json=payload
            )
            print(f"Status: {response.status_code}")
            
            if response.status_code == 201:
                data = response.json()
                print(f"✅ Payment initiated successfully!")
                print(f"   Reference: {data.get('reference')}")
                print(f"   Authorization URL: {data.get('authorization_url', '')[:60]}...")
                return data.get('reference')
            else:
                print(f"❌ Failed: {response.text}")
                return None
        except Exception as e:
            print(f"❌ Error: {e}")
            return None


async def test_transaction_status(reference):
    """Test transaction status check"""
    print("\n" + "="*60)
    print("TEST 4: Transaction Status Check")
    print("="*60)
    
    if not reference:
        print("⚠️  Skipped: No reference from previous test")
        return False
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BASE_URL}/payments/{reference}/status"
            )
            print(f"✅ Status: {response.status_code}")
            data = response.json()
            print(f"   Reference: {data.get('reference')}")
            print(f"   Status: {data.get('status')}")
            print(f"   Amount: {data.get('amount')} kobo")
            print(f"   Paid At: {data.get('paid_at', 'Not paid yet')}")
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_transaction_status_with_refresh(reference):
    """Test transaction status check with refresh from Paystack"""
    print("\n" + "="*60)
    print("TEST 5: Transaction Status Check (with refresh)")
    print("="*60)
    
    if not reference:
        print("⚠️  Skipped: No reference from previous test")
        return False
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BASE_URL}/payments/{reference}/status?refresh=true"
            )
            print(f"✅ Status: {response.status_code}")
            data = response.json()
            print(f"   Reference: {data.get('reference')}")
            print(f"   Status: {data.get('status')}")
            print(f"   Amount: {data.get('amount')} kobo")
            return True
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_invalid_payment():
    """Test payment with invalid amount"""
    print("\n" + "="*60)
    print("TEST 6: Invalid Payment (Error Handling)")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        try:
            payload = {"amount": -1000}  # Negative amount
            response = await client.post(
                f"{BASE_URL}/payments/paystack/initiate",
                json=payload
            )
            print(f"Status: {response.status_code}")
            
            if response.status_code == 400 or response.status_code == 422:
                print(f"✅ Correctly rejected invalid amount")
                print(f"   Error: {response.json()}")
                return True
            else:
                print(f"❌ Should have rejected negative amount")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_nonexistent_transaction():
    """Test fetching non-existent transaction"""
    print("\n" + "="*60)
    print("TEST 7: Non-existent Transaction (Error Handling)")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                f"{BASE_URL}/payments/fake_reference_12345/status"
            )
            print(f"Status: {response.status_code}")
            
            if response.status_code == 404:
                print(f"✅ Correctly returned 404 for non-existent transaction")
                return True
            else:
                print(f"❌ Should have returned 404")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def test_api_docs():
    """Test if API documentation is accessible"""
    print("\n" + "="*60)
    print("TEST 8: API Documentation Accessibility")
    print("="*60)
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{BASE_URL}/docs")
            if response.status_code == 200:
                print(f"✅ API docs accessible at {BASE_URL}/docs")
                return True
            else:
                print(f"❌ API docs not accessible")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False


async def run_all_tests():
    """Run all tests"""
    print("\n" + "🚀 " * 20)
    print("HNG STAGE 8 - API TEST SUITE")
    print("🚀 " * 20)
    print(f"\nTesting API at: {BASE_URL}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    results = []
    
    # Test 1: Health Check (must pass to continue)
    health_ok = await test_health_check()
    results.append(("Health Check", health_ok))
    
    if not health_ok:
        print("\n❌ Server is not running. Please start it with:")
        print("   uvicorn app.main:app --reload")
        return
    
    # Test 2: Google Auth URL
    results.append(("Google Auth URL", await test_google_auth_url()))
    
    # Test 3: Payment Initiation
    reference = await test_payment_initiation()
    results.append(("Payment Initiation", reference is not None))
    
    # Test 4: Transaction Status
    results.append(("Transaction Status", await test_transaction_status(reference)))
    
    # Test 5: Transaction Status with Refresh
    results.append(("Status with Refresh", await test_transaction_status_with_refresh(reference)))
    
    # Test 6: Invalid Payment
    results.append(("Invalid Payment", await test_invalid_payment()))
    
    # Test 7: Non-existent Transaction
    results.append(("Non-existent Transaction", await test_nonexistent_transaction()))
    
    # Test 8: API Docs
    results.append(("API Documentation", await test_api_docs()))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{'='*60}")
    print(f"Results: {passed}/{total} tests passed ({(passed/total)*100:.1f}%)")
    print(f"{'='*60}\n")
    
    if passed == total:
        print("🎉 All tests passed! Your API is working correctly!")
        print("\nNext steps:")
        print("1. Test Google OAuth manually by visiting the URL from Test 2")
        print("2. Test Paystack payment by completing a transaction")
        print("3. Check the database to see stored data")
        print(f"4. Visit {BASE_URL}/docs for interactive testing")
    else:
        print("⚠️  Some tests failed. Please check:")
        print("1. Is PostgreSQL running?")
        print("2. Is .env file configured correctly?")
        print("3. Are all dependencies installed?")
        print("4. Check the error messages above for details")
    
    print("\n" + "🚀 " * 20 + "\n")


if __name__ == "__main__":
    asyncio.run(run_all_tests())
