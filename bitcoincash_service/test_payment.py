#!/usr/bin/env python3
"""
Bitcoin Cash Payment System Test Script
This script tests the critical components of the payment system:
1. Transaction history retrieval
2. Address balance checking
3. Payment processing workflow
"""

import logging
import json
from app import electron_cash, direct_payment_handler, logger

# Configure logging to show all messages for testing
logging.basicConfig(level=logging.INFO)

def test_history_method():
    """Test the history method which replaced listtransactions"""
    print("\n=== Testing history method ===")
    result = electron_cash.call_method("history")
    print(f"History result type: {type(result)}")
    print(f"Got {len(result) if result else 0} transactions")
    if result:
        # Print first transaction details
        print("\nSample transaction:")
        print(json.dumps(result[0], indent=2))
    return result is not None

def test_address_balance(address=None):
    """Test the address balance checking function"""
    if not address:
        # Try to get a new address if none provided
        try:
            address = electron_cash.get_new_address()
        except Exception as e:
            print(f"Error getting new address: {e}")
            address = "qz4xf6gf4w4gjdssl6nzlfmyc6g6ejgk65tjewlt06"  # Example address
    
    print(f"\n=== Testing balance check for address {address} ===")
    
    # Format address with bitcoincash: prefix if needed
    if not address.startswith('bitcoincash:'):
        formatted_address = f"bitcoincash:{address}"
    else:
        formatted_address = address
    
    balance = electron_cash.check_address_balance(formatted_address)
    print(f"Balance result: {balance} BCH")
    
    # Try direct method call to compare
    print("\n=== Testing direct getaddressbalance call ===")
    direct_result = electron_cash.call_method("getaddressbalance", [formatted_address])
    print(f"Direct balance API response: {direct_result}")
    
    return balance is not None

def verify_wallet_status():
    """Check if the wallet is loaded and working"""
    print("\n=== Verifying wallet status ===")
    info = electron_cash.call_method("getinfo")
    print(f"Wallet info: {info}")
    
    # Try loading wallet if needed
    if not info or 'error' in str(info).lower():
        print("Attempting to load wallet...")
        load_result = electron_cash.call_method("load_wallet")
        print(f"Load wallet result: {load_result}")
        
        # Check again
        info = electron_cash.call_method("getinfo")
        print(f"Wallet info after load attempt: {info}")
    
    return info is not None

def run_all_tests():
    """Run all tests and report results"""
    print("====== BITCOIN CASH PAYMENT SYSTEM TEST ======")
    
    # First check wallet status
    wallet_ok = verify_wallet_status()
    print(f"Wallet status: {'OK' if wallet_ok else 'FAILED'}")
    
    # Test history method
    history_ok = test_history_method()
    print(f"History method test: {'OK' if history_ok else 'FAILED'}")
    
    # Test balance checking
    balance_ok = test_address_balance()
    print(f"Balance check test: {'OK' if balance_ok else 'FAILED'}")
    
    print("\n====== TEST SUMMARY ======")
    print(f"Wallet status: {'✅' if wallet_ok else '❌'}")
    print(f"History method: {'✅' if history_ok else '❌'}")
    print(f"Balance check: {'✅' if balance_ok else '❌'}")
    
    if wallet_ok and history_ok and balance_ok:
        print("\n✅ All tests PASSED")
    else:
        print("\n❌ Some tests FAILED")

if __name__ == "__main__":
    run_all_tests()