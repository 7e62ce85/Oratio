"""
Membership Sync Service
Syncs membership data from bitcoincash service SQLite DB to Lemmy PostgreSQL DB
This enables the vote multiplier triggers to work correctly
"""

import sqlite3
import psycopg2
import time
import logging
from typing import List, Dict, Any
import os

logger = logging.getLogger('membership_sync')

class MembershipSyncService:
    """Service to sync membership data between databases"""
    
    def __init__(self, 
                 sqlite_db_path: str,
                 postgres_config: Dict[str, Any]):
        """
        Initialize the sync service
        
        Args:
            sqlite_db_path: Path to the bitcoincash service SQLite database
            postgres_config: PostgreSQL connection configuration
        """
        self.sqlite_db_path = sqlite_db_path
        self.postgres_config = postgres_config
        self.last_sync_time = 0
        
    def get_active_memberships(self) -> List[Dict[str, Any]]:
        """
        Get all active memberships from bitcoincash service database
        
        Returns:
            List of membership records
        """
        try:
            conn = sqlite3.connect(self.sqlite_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    user_id,
                    membership_type,
                    purchased_at,
                    expires_at,
                    amount_paid,
                    is_active
                FROM user_memberships
                WHERE is_active = 1
            """)
            
            memberships = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            logger.info(f"Retrieved {len(memberships)} active memberships from SQLite")
            return memberships
            
        except Exception as e:
            logger.error(f"Error reading from SQLite database: {str(e)}")
            return []
    
    def sync_to_postgres(self, memberships: List[Dict[str, Any]]) -> int:
        """
        Sync membership data to PostgreSQL
        
        Args:
            memberships: List of membership records to sync
            
        Returns:
            Number of records synced
        """
        if not memberships:
            logger.info("No memberships to sync")
            return 0
        
        try:
            conn = psycopg2.connect(**self.postgres_config)
            cursor = conn.cursor()
            
            # First, create the table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_memberships (
                    user_id TEXT PRIMARY KEY,
                    membership_type TEXT DEFAULT 'annual',
                    purchased_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    amount_paid REAL NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    synced_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # Create index if not exists
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_memberships_active 
                    ON user_memberships(user_id, is_active, expires_at)
            """)
            
            # Sync each membership
            synced_count = 0
            for membership in memberships:
                try:
                    # Convert SQLite integer (0/1) to PostgreSQL boolean (True/False)
                    is_active_bool = bool(membership['is_active'])
                    
                    cursor.execute("""
                        INSERT INTO user_memberships 
                            (user_id, membership_type, purchased_at, expires_at, amount_paid, is_active, synced_at)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (user_id) 
                        DO UPDATE SET
                            membership_type = EXCLUDED.membership_type,
                            purchased_at = EXCLUDED.purchased_at,
                            expires_at = EXCLUDED.expires_at,
                            amount_paid = EXCLUDED.amount_paid,
                            is_active = EXCLUDED.is_active,
                            synced_at = NOW()
                    """, (
                        membership['user_id'],
                        membership['membership_type'],
                        membership['purchased_at'],
                        membership['expires_at'],
                        membership['amount_paid'],
                        is_active_bool
                    ))
                    synced_count += 1
                except Exception as e:
                    logger.error(f"Error syncing membership for user {membership['user_id']}: {str(e)}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
            logger.info(f"Successfully synced {synced_count} memberships to PostgreSQL")
            return synced_count
            
        except Exception as e:
            logger.error(f"Error syncing to PostgreSQL: {str(e)}")
            return 0
    
    def cleanup_expired_memberships(self) -> int:
        """
        Remove expired memberships from PostgreSQL
        
        Returns:
            Number of records cleaned up
        """
        try:
            conn = psycopg2.connect(**self.postgres_config)
            cursor = conn.cursor()
            
            current_time = int(time.time())
            
            cursor.execute("""
                UPDATE user_memberships
                SET is_active = FALSE
                WHERE expires_at < %s AND is_active = TRUE
                RETURNING user_id
            """, (current_time,))
            
            expired_users = cursor.fetchall()
            expired_count = len(expired_users)
            
            conn.commit()
            cursor.close()
            conn.close()
            
            if expired_count > 0:
                logger.info(f"Marked {expired_count} memberships as expired in PostgreSQL")
            
            return expired_count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired memberships: {str(e)}")
            return 0
    
    def run_sync(self) -> Dict[str, int]:
        """
        Run a full sync cycle
        
        Returns:
            Dictionary with sync statistics
        """
        logger.info("Starting membership sync cycle...")
        
        # Get active memberships from SQLite
        memberships = self.get_active_memberships()
        
        # Sync to PostgreSQL
        synced_count = self.sync_to_postgres(memberships)
        
        # Cleanup expired memberships
        expired_count = self.cleanup_expired_memberships()
        
        self.last_sync_time = time.time()
        
        stats = {
            'synced': synced_count,
            'expired': expired_count,
            'total_active': len(memberships)
        }
        
        logger.info(f"Sync cycle completed: {stats}")
        return stats
    
    def start_periodic_sync(self, interval_seconds: int = 60):
        """
        Start periodic sync in a background thread
        
        Args:
            interval_seconds: Sync interval in seconds (default: 60)
        """
        import threading
        
        def sync_loop():
            while True:
                try:
                    self.run_sync()
                except Exception as e:
                    logger.error(f"Error in sync loop: {str(e)}")
                
                time.sleep(interval_seconds)
        
        thread = threading.Thread(target=sync_loop, daemon=True)
        thread.start()
        logger.info(f"Started periodic membership sync (interval: {interval_seconds}s)")


def setup_membership_sync() -> MembershipSyncService:
    """
    Setup and initialize the membership sync service
    
    Returns:
        Initialized MembershipSyncService instance
    """
    # Get SQLite database path
    sqlite_db_path = os.environ.get('DB_PATH', '/app/data/payment.db')
    
    # Get PostgreSQL configuration
    postgres_config = {
        'host': os.environ.get('POSTGRES_HOST', 'postgres'),
        'port': int(os.environ.get('POSTGRES_PORT', 5432)),
        'user': os.environ.get('POSTGRES_USER', 'lemmy'),
        'password': os.environ.get('POSTGRES_PASSWORD', ''),
        'database': os.environ.get('POSTGRES_DB', 'lemmy')
    }
    
    # Create and return sync service
    sync_service = MembershipSyncService(sqlite_db_path, postgres_config)
    
    logger.info("Membership sync service initialized")
    return sync_service


if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Test the sync service
    sync_service = setup_membership_sync()
    stats = sync_service.run_sync()
    print(f"Sync completed: {stats}")
