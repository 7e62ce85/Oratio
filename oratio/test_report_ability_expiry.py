#!/usr/bin/env python3
"""
Test script to check report_ability_revoked_at column and verify auto-restore logic.
Run from inside the Docker container or with DB mounted at /data/payments.db
"""

import sqlite3
import time
import os

DB_PATH = os.environ.get('PAYMENT_DB_PATH', '/data/payments.db')

def test_report_ability_expiry():
    print("=" * 80)
    print("TESTING REPORT ABILITY EXPIRY & AUTO-RESTORE")
    print("=" * 80)
    
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cursor = conn.cursor()
    
    # 1. Check if column exists
    print("\n1️⃣  Checking if report_ability_revoked_at column exists...")
    cursor.execute("PRAGMA table_info(user_cp_permissions)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'report_ability_revoked_at' in columns:
        print("   ✅ Column exists!")
    else:
        print("   ❌ Column NOT found!")
        conn.close()
        return
    
    # 2. Find users with revoked report ability
    print("\n2️⃣  Finding users with revoked report ability...")
    cursor.execute('''
        SELECT username, can_report_cp, report_ability_revoked_at, 
               datetime(report_ability_revoked_at, 'unixepoch') as expire_date
        FROM user_cp_permissions
        WHERE report_ability_revoked_at IS NOT NULL
        ORDER BY report_ability_revoked_at DESC
        LIMIT 20
    ''')
    
    rows = cursor.fetchall()
    if rows:
        print(f"   Found {len(rows)} users with revoked report ability:\n")
        for row in rows:
            username, can_report, revoked_at, expire_date = row
            now = int(time.time())
            if revoked_at > now:
                days_left = (revoked_at - now) / (24 * 60 * 60)
                status = f"⏳ Expires in {int(days_left)} days"
            else:
                days_past = (now - revoked_at) / (24 * 60 * 60)
                status = f"🔓 EXPIRED {int(days_past)} days ago"
            
            print(f"   - {username:20s} | can_report={can_report} | {status} | {expire_date}")
    else:
        print("   ℹ️  No users found with revoked report ability")
    
    # 3. Check for users who should be auto-restored (expired)
    print("\n3️⃣  Checking for expired revocations that should be auto-restored...")
    now = int(time.time())
    cursor.execute('''
        SELECT username, can_report_cp, report_ability_revoked_at
        FROM user_cp_permissions
        WHERE can_report_cp = 0 
          AND report_ability_revoked_at IS NOT NULL 
          AND report_ability_revoked_at <= ?
    ''', (now,))
    
    expired_rows = cursor.fetchall()
    if expired_rows:
        print(f"   ⚠️  Found {len(expired_rows)} users with EXPIRED revocations:")
        for row in expired_rows:
            username, can_report, revoked_at = row
            expire_date = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(revoked_at))
            print(f"      - {username} (expired on {expire_date})")
        print("\n   💡 These users should be auto-restored by background task!")
    else:
        print("   ✅ No expired revocations found")
    
    # 4. Test: Manually set a test user with expired revocation (if not exists)
    print("\n4️⃣  Creating test user with expired revocation for verification...")
    test_username = "test_expired_report_ban"
    
    # Check if test user exists
    cursor.execute('SELECT user_id FROM user_cp_permissions WHERE username = ?', (test_username,))
    if not cursor.fetchone():
        try:
            # Create test user
            now = int(time.time())
            one_day_ago = now - (24 * 60 * 60)  # Expired 1 day ago
            cursor.execute('''
                INSERT INTO user_cp_permissions 
                (user_id, person_id, username, can_report_cp, report_ability_revoked_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (test_username, 9999, test_username, False, one_day_ago, now, now))
            conn.commit()
            print(f"   ✅ Created test user '{test_username}' with EXPIRED revocation (1 day ago)")
            print(f"      - This user should be auto-restored by background task")
        except sqlite3.IntegrityError as e:
            print(f"   ⚠️  Could not create test user: {e}")
    else:
        print(f"   ℹ️  Test user '{test_username}' already exists")
    
    # 5. Show summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    cursor.execute('SELECT COUNT(*) FROM user_cp_permissions WHERE can_report_cp = 0')
    total_revoked = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT COUNT(*) FROM user_cp_permissions 
        WHERE can_report_cp = 0 AND report_ability_revoked_at IS NOT NULL AND report_ability_revoked_at <= ?
    ''', (now,))
    expired_count = cursor.fetchone()[0]
    
    print(f"   Total users with revoked report ability: {total_revoked}")
    print(f"   Users with EXPIRED revocations (should auto-restore): {expired_count}")
    
    if expired_count > 0:
        print("\n   🔄 Run background task to restore expired users:")
        print("      docker-compose exec bitcoincash-service python -c \"from services.cp_moderation import check_expired_report_ability_bans; print('Restored:', check_expired_report_ability_bans())\"")
    
    conn.close()
    print("\n✅ Test complete!\n")

if __name__ == "__main__":
    test_report_ability_expiry()
