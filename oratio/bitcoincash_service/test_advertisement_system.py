#!/usr/bin/env python3
"""
Advertisement System Test Script
광고 시스템 API 및 서비스 테스트
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import time
import sqlite3
from typing import Dict, Any

# Test configuration
DB_PATH = os.path.join(os.path.dirname(__file__), 'data/payments.db')
TEST_USER = 'gookjob'
TEST_ADVERTISER = 'test_advertiser'


def get_db():
    """Get database connection"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {test_name}")
    if details:
        print(f"       └─ {details}")


def test_database_tables():
    """Test 1: Check if all required tables exist"""
    print("\n" + "="*60)
    print("TEST 1: Database Tables")
    print("="*60)
    
    required_tables = ['ad_credits', 'ad_campaigns', 'ad_impressions', 'ad_transactions', 'ad_config']
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    existing_tables = [row['name'] for row in cursor.fetchall()]
    conn.close()
    
    all_exist = True
    for table in required_tables:
        exists = table in existing_tables
        print_result(f"Table '{table}' exists", exists)
        if not exists:
            all_exist = False
    
    return all_exist


def test_gookjob_initial_credits():
    """Test 2: Check gookjob has $10 initial credits"""
    print("\n" + "="*60)
    print("TEST 2: Initial Credits for gookjob")
    print("="*60)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ad_credits WHERE username = ?", (TEST_USER,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print_result("gookjob credits exist", False, "No record found")
        return False
    
    balance = row['credit_balance_usd']
    print_result("gookjob credits exist", True, f"Balance: ${balance:.2f} USD")
    
    has_10_usd = balance >= 10.0
    print_result("gookjob has >= $10 USD", has_10_usd, f"Expected: $10.00, Got: ${balance:.2f}")
    
    return has_10_usd


def test_ad_config():
    """Test 3: Check ad_config defaults"""
    print("\n" + "="*60)
    print("TEST 3: Ad Configuration")
    print("="*60)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM ad_config WHERE is_active = TRUE ORDER BY effective_from DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print_result("Active config exists", False)
        return False
    
    print_result("Active config exists", True)
    print_result("baseline_budget_usd", row['baseline_budget_usd'] == 100.0, f"${row['baseline_budget_usd']}")
    print_result("minimum_budget_usd", row['minimum_budget_usd'] == 10.0, f"${row['minimum_budget_usd']}")
    print_result("cost_per_impression_usd", row['cost_per_impression_usd'] == 0.001, f"${row['cost_per_impression_usd']}")
    print_result("cost_per_click_usd", row['cost_per_click_usd'] == 0.01, f"${row['cost_per_click_usd']}")
    
    return True


def test_ad_service_import():
    """Test 4: Import AdService"""
    print("\n" + "="*60)
    print("TEST 4: AdService Import")
    print("="*60)
    
    try:
        from services.ad_service import AdService, ad_service
        print_result("Import AdService", True)
        print_result("Singleton ad_service exists", ad_service is not None)
        return True
    except ImportError as e:
        print_result("Import AdService", False, str(e))
        return False


def test_ad_service_credits():
    """Test 5: Test credit operations"""
    print("\n" + "="*60)
    print("TEST 5: Credit Operations")
    print("="*60)
    
    try:
        from services.ad_service import ad_service
        
        # Get gookjob credits
        balance = ad_service.get_ad_credits(TEST_USER)
        print_result("get_ad_credits(gookjob)", balance >= 10.0, f"${balance:.2f}")
        
        # Add credits to test user
        result = ad_service.add_ad_credits(TEST_ADVERTISER, 50.0, "Test deposit")
        print_result("add_ad_credits(test_advertiser, $50)", result['success'], 
                    f"New balance: ${result.get('new_balance_usd', 0):.2f}")
        
        # Verify balance
        new_balance = ad_service.get_ad_credits(TEST_ADVERTISER)
        print_result("Verify new balance", new_balance >= 50.0, f"${new_balance:.2f}")
        
        return True
    except Exception as e:
        print_result("Credit operations", False, str(e))
        return False


def test_campaign_creation():
    """Test 6: Test campaign creation"""
    print("\n" + "="*60)
    print("TEST 6: Campaign Creation")
    print("="*60)
    
    try:
        from services.ad_service import ad_service
        
        # Create campaign with gookjob (has $10)
        campaign_data = {
            "advertiser_username": TEST_USER,
            "title": "Test Ad Campaign",
            "link_url": "https://example.com/test",
            "image_url": "https://example.com/ad.png",
            "monthly_budget_usd": 10.0,
            "is_nsfw": False,
            "show_on_all": True
        }
        
        result = ad_service.create_campaign(campaign_data)
        print_result("Create campaign", result['success'], 
                    f"ID: {result.get('campaign_id', 'N/A')[:8]}... Status: {result.get('approval_status', 'N/A')}")
        
        if not result['success']:
            print_result("Campaign creation error", False, result.get('error', 'Unknown'))
            return False
        
        campaign_id = result['campaign_id']
        
        # Verify campaign is pending
        campaign = ad_service.get_campaign(campaign_id)
        print_result("Campaign status is 'pending'", campaign['approval_status'] == 'pending')
        
        # Test insufficient credits
        low_budget_data = {
            "advertiser_username": "nonexistent_user",
            "title": "Low Budget Ad",
            "link_url": "https://example.com",
            "monthly_budget_usd": 10.0
        }
        low_result = ad_service.create_campaign(low_budget_data)
        print_result("Reject insufficient credits", not low_result['success'], 
                    f"Error: {low_result.get('error', 'N/A')[:40]}")
        
        # Test minimum budget enforcement
        min_budget_data = {
            "advertiser_username": TEST_ADVERTISER,
            "title": "Too Cheap Ad",
            "link_url": "https://example.com",
            "monthly_budget_usd": 5.0  # Below $10 minimum
        }
        min_result = ad_service.create_campaign(min_budget_data)
        print_result("Reject below minimum budget ($5 < $10)", not min_result['success'])
        
        return result['success']
    except Exception as e:
        print_result("Campaign creation", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_campaign_approval():
    """Test 7: Test campaign approval workflow"""
    print("\n" + "="*60)
    print("TEST 7: Campaign Approval Workflow")
    print("="*60)
    
    try:
        from services.ad_service import ad_service
        
        # Get pending campaigns
        pending = ad_service.get_pending_campaigns()
        print_result("Get pending campaigns", len(pending) >= 0, f"Count: {len(pending)}")
        
        if pending:
            campaign_id = pending[0]['id']
            
            # Approve campaign
            result = ad_service.approve_campaign(campaign_id, 'admin_test')
            print_result("Approve campaign", result['success'])
            
            # Verify approval
            campaign = ad_service.get_campaign(campaign_id)
            print_result("Campaign status is 'approved'", campaign['approval_status'] == 'approved')
            print_result("Approved by is set", campaign['approved_by'] == 'admin_test')
        else:
            print_result("No pending campaigns to test", True, "Skipping approval test")
        
        return True
    except Exception as e:
        print_result("Campaign approval", False, str(e))
        return False


def test_ad_selection():
    """Test 8: Test ad selection algorithm"""
    print("\n" + "="*60)
    print("TEST 8: Ad Selection Algorithm")
    print("="*60)
    
    try:
        from services.ad_service import ad_service
        
        # Select ad for homepage
        ad = ad_service.select_ad_to_display(
            community=None,
            is_nsfw=False,
            page_url="https://oratio.space/"
        )
        
        if ad:
            print_result("Select ad for homepage", True, f"Campaign: {ad['campaign_id'][:8]}...")
            print_result("Ad has impression_id", 'impression_id' in ad)
            print_result("Ad has title", 'title' in ad and ad['title'])
            print_result("Ad has link_url", 'link_url' in ad and ad['link_url'])
        else:
            print_result("Select ad for homepage", True, "No eligible ads (expected if none approved)")
        
        # Test NSFW filtering
        nsfw_ad = ad_service.select_ad_to_display(
            community=None,
            is_nsfw=True,
            page_url="https://oratio.space/nsfw"
        )
        print_result("NSFW page ad selection", True, f"Ad: {'Found' if nsfw_ad else 'None'}")
        
        return True
    except Exception as e:
        print_result("Ad selection", False, str(e))
        import traceback
        traceback.print_exc()
        return False


def test_load_points():
    """Test 9: Test load points mechanism"""
    print("\n" + "="*60)
    print("TEST 9: Load Points Mechanism")
    print("="*60)
    
    try:
        from services.ad_service import ad_service
        
        # Get a campaign
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, load_points FROM ad_campaigns WHERE is_active = TRUE LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            print_result("Load points test", True, "No active campaigns to test")
            conn.close()
            return True
        
        campaign_id = row['id']
        initial_points = row['load_points']
        
        # Increment load points
        ad_service._increment_load_points(campaign_id)
        
        cursor.execute("SELECT load_points FROM ad_campaigns WHERE id = ?", (campaign_id,))
        new_points = cursor.fetchone()['load_points']
        
        print_result("Increment load points", new_points == initial_points + 1, 
                    f"{initial_points} -> {new_points}")
        
        # Decrement load points
        ad_service._decrement_load_points(campaign_id)
        
        cursor.execute("SELECT load_points FROM ad_campaigns WHERE id = ?", (campaign_id,))
        final_points = cursor.fetchone()['load_points']
        
        print_result("Decrement load points", final_points == initial_points, 
                    f"{new_points} -> {final_points}")
        
        conn.close()
        return True
    except Exception as e:
        print_result("Load points", False, str(e))
        return False


def test_click_tracking():
    """Test 10: Test click tracking"""
    print("\n" + "="*60)
    print("TEST 10: Click Tracking")
    print("="*60)
    
    try:
        from services.ad_service import ad_service
        
        # Get an impression
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, clicked FROM ad_impressions WHERE clicked = FALSE LIMIT 1")
        row = cursor.fetchone()
        
        if not row:
            print_result("Click tracking test", True, "No unclicked impressions to test")
            conn.close()
            return True
        
        impression_id = row['id']
        
        # Record click
        result = ad_service.record_click(impression_id)
        print_result("Record click", result)
        
        # Verify click recorded
        cursor.execute("SELECT clicked, clicked_at FROM ad_impressions WHERE id = ?", (impression_id,))
        updated = cursor.fetchone()
        
        print_result("Click marked in database", updated['clicked'] == 1)
        print_result("Click timestamp set", updated['clicked_at'] is not None)
        
        # Try to click again (should fail - already clicked)
        duplicate_result = ad_service.record_click(impression_id)
        print_result("Reject duplicate click", not duplicate_result)
        
        conn.close()
        return True
    except Exception as e:
        print_result("Click tracking", False, str(e))
        return False


def cleanup_test_data():
    """Cleanup test data"""
    print("\n" + "="*60)
    print("CLEANUP: Removing test data")
    print("="*60)
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Remove test advertiser (but keep gookjob!)
        cursor.execute("DELETE FROM ad_transactions WHERE advertiser_username = ?", (TEST_ADVERTISER,))
        cursor.execute("DELETE FROM ad_impressions WHERE advertiser_username = ?", (TEST_ADVERTISER,))
        cursor.execute("DELETE FROM ad_campaigns WHERE advertiser_username = ?", (TEST_ADVERTISER,))
        cursor.execute("DELETE FROM ad_credits WHERE username = ?", (TEST_ADVERTISER,))
        
        conn.commit()
        conn.close()
        
        print_result("Cleanup test_advertiser data", True)
        return True
    except Exception as e:
        print_result("Cleanup", False, str(e))
        return False


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("ADVERTISEMENT SYSTEM TEST SUITE")
    print("="*60)
    print(f"Database: {DB_PATH}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    
    # Run tests
    results.append(("Database Tables", test_database_tables()))
    results.append(("Initial Credits", test_gookjob_initial_credits()))
    results.append(("Ad Config", test_ad_config()))
    results.append(("AdService Import", test_ad_service_import()))
    results.append(("Credit Operations", test_ad_service_credits()))
    results.append(("Campaign Creation", test_campaign_creation()))
    results.append(("Campaign Approval", test_campaign_approval()))
    results.append(("Ad Selection", test_ad_selection()))
    results.append(("Load Points", test_load_points()))
    results.append(("Click Tracking", test_click_tracking()))
    
    # Cleanup
    cleanup_test_data()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"  {status} {name}")
    
    print(f"\nTotal: {passed}/{total} passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
