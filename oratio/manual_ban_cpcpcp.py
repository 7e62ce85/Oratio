#!/usr/bin/env python3
"""
Manually ban user cpcpcp in Lemmy (admin ban)
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, '/app')

from lemmy_integration import LemmyAPI
import time

def main():
    # Get person_id for cpcpcp
    person_id = 71  # From database query
    username = "cpcpcp"
    
    # Calculate ban end (3 months from now)
    now = int(time.time())
    ban_duration = 90 * 24 * 60 * 60  # 3 months
    ban_end = now + ban_duration
    
    print(f"🔧 Manually banning user: {username} (person_id: {person_id})")
    print(f"⏰ Ban duration: 3 months")
    print(f"📅 Ban expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ban_end))}")
    print()
    
    # Setup Lemmy API
    lemmy_api_url = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
    lemmy_admin_username = os.environ.get('LEMMY_ADMIN_USER', 'admin')
    lemmy_admin_password = os.environ.get('LEMMY_ADMIN_PASS', '')
    
    if not lemmy_admin_password:
        print("❌ ERROR: No admin password set!")
        return False
    
    lemmy_api = LemmyAPI(lemmy_api_url)
    lemmy_api.set_admin_credentials(lemmy_admin_username, lemmy_admin_password)
    
    print("🔐 Logging in as admin...")
    if not lemmy_api.login_as_admin():
        print("❌ ERROR: Failed to login as admin")
        return False
    
    print("✅ Admin login successful")
    print()
    
    print("🚫 Banning user in Lemmy...")
    success = lemmy_api.ban_person(
        person_id=person_id,
        ban=True,
        reason="CP violation - Child pornography content",
        expires=ban_end,
        remove_data=False
    )
    
    if success:
        print(f"✅ SUCCESS: User {username} banned in Lemmy!")
        print(f"📅 Ban expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ban_end))}")
        return True
    else:
        print(f"❌ ERROR: Failed to ban user {username}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
