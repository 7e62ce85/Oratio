"""
Upload Quota Service
Manages user upload quotas, overage charging, and file size validation.

Version: 1.0
Created: 2025-11-04
"""

import sqlite3
import logging
import time
import uuid
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class UploadQuotaService:
    """Service for managing upload quotas and overage charging"""
    
    # Constants
    FREE_USER_LIMIT_BYTES = 256_000  # 250KB
    MEMBER_ANNUAL_QUOTA_BYTES = 21_474_836_480  # 20GB
    OVERAGE_USD_PER_4GB = 1.0
    BYTES_PER_4GB = 4_294_967_296  # 4GB in bytes
    MIN_CHARGE_USD = 0.01
    
    def __init__(self, db_path: str):
        """Initialize the upload quota service
        
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables if they don't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Read and execute migration SQL
            import os
            migration_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'migrations',
                'upload_quota_system.sql'
            )
            
            if os.path.exists(migration_path):
                with open(migration_path, 'r') as f:
                    cursor.executescript(f.read())
                conn.commit()
                logger.info("✅ Upload quota database initialized")
            else:
                logger.warning(f"⚠️  Migration file not found: {migration_path}")
            
            conn.close()
        except Exception as e:
            logger.error(f"❌ Failed to initialize upload quota database: {e}")
            raise
    
    def get_user_quota(self, user_id: str, username: str = None) -> Dict:
        """Get user's upload quota information
        
        Args:
            user_id: User ID
            username: Optional username for display
            
        Returns:
            Dict with quota information
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get or create quota record
            cursor.execute("""
                SELECT * FROM user_upload_quotas WHERE user_id = ?
            """, (user_id,))
            quota = cursor.fetchone()
            
            if not quota:
                # Check if user has membership
                cursor.execute("""
                    SELECT * FROM user_memberships 
                    WHERE user_id = ? AND is_active = TRUE
                """, (user_id,))
                membership = cursor.fetchone()
                
                # Create quota record
                is_member = membership is not None
                annual_quota = self.MEMBER_ANNUAL_QUOTA_BYTES if is_member else 0
                membership_type = 'annual' if is_member else 'free'
                
                now = int(time.time())
                quota_start = membership['purchased_at'] if is_member else now
                quota_end = membership['expires_at'] if is_member else now + 31536000  # 1 year
                
                cursor.execute("""
                    INSERT INTO user_upload_quotas (
                        user_id, username, annual_quota_bytes, used_bytes,
                        quota_start_date, quota_end_date, membership_type,
                        created_at, updated_at, is_active
                    ) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?, TRUE)
                """, (user_id, username or user_id, annual_quota, 
                      quota_start, quota_end, membership_type, now, now))
                conn.commit()
                
                # Fetch the newly created quota
                cursor.execute("""
                    SELECT * FROM user_upload_quotas WHERE user_id = ?
                """, (user_id,))
                quota = cursor.fetchone()
            
            conn.close()
            
            # Format response
            result = {
                'user_id': quota['user_id'],
                'username': quota['username'],
                'membership_type': quota['membership_type'],
                'is_member': quota['membership_type'] == 'annual',
                'annual_quota_bytes': quota['annual_quota_bytes'],
                'annual_quota_gb': round(quota['annual_quota_bytes'] / 1_073_741_824, 2),
                'used_bytes': quota['used_bytes'],
                'used_gb': round(quota['used_bytes'] / 1_073_741_824, 2),
                'remaining_bytes': quota['annual_quota_bytes'] - quota['used_bytes'],
                'remaining_gb': round((quota['annual_quota_bytes'] - quota['used_bytes']) / 1_073_741_824, 2),
                'usage_percentage': round((quota['used_bytes'] / quota['annual_quota_bytes'] * 100), 2) if quota['annual_quota_bytes'] > 0 else 0,
                'quota_start_date': quota['quota_start_date'],
                'quota_end_date': quota['quota_end_date'],
                'is_active': quota['is_active']
            }
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Failed to get user quota for {user_id}: {e}")
            raise
    
    def validate_upload(self, user_id: str, file_size_bytes: int, 
                       filename: str = None, username: str = None) -> Dict:
        """Validate if upload is allowed and calculate charges
        
        Args:
            user_id: User ID
            file_size_bytes: Size of file to upload
            filename: Optional filename
            username: Optional username
            
        Returns:
            Dict with validation result and pricing info
        """
        try:
            quota = self.get_user_quota(user_id, username)
            is_member = quota['is_member']
            
            # Check file size limits
            if not is_member:
                # Free users: 250KB limit per upload
                if file_size_bytes > self.FREE_USER_LIMIT_BYTES:
                    return {
                        'allowed': False,
                        'reason': 'file_too_large',
                        'message': f'File size ({self._format_bytes(file_size_bytes)}) exceeds free user limit of {self._format_bytes(self.FREE_USER_LIMIT_BYTES)}. Purchase annual membership for 20GB quota.',
                        'max_size_bytes': self.FREE_USER_LIMIT_BYTES,
                        'requires_membership': True
                    }
                
                return {
                    'allowed': True,
                    'reason': 'within_free_limit',
                    'message': 'Upload allowed within free user limit',
                    'will_charge': False,
                    'charge_amount_usd': 0.0,
                    'charge_amount_bch': 0.0
                }
            
            # Member users: Check quota
            remaining = quota['remaining_bytes']
            
            if file_size_bytes <= remaining:
                # Within quota
                return {
                    'allowed': True,
                    'reason': 'within_quota',
                    'message': f'Upload allowed. Remaining quota: {self._format_bytes(remaining - file_size_bytes)}',
                    'will_charge': False,
                    'charge_amount_usd': 0.0,
                    'charge_amount_bch': 0.0,
                    'remaining_after_upload_bytes': remaining - file_size_bytes,
                    'remaining_after_upload_gb': round((remaining - file_size_bytes) / 1_073_741_824, 2)
                }
            else:
                # Overage - calculate charge
                overage_bytes = file_size_bytes - remaining
                charge_usd = self._calculate_overage_charge(overage_bytes)
                
                # Get BCH price
                from .price_service import PriceService
                price_service = PriceService()
                bch_usd_rate = price_service.get_bch_usd_price()
                charge_bch = round(charge_usd / bch_usd_rate, 8)
                
                # Check if user has enough credit
                import sys
                import os
                sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
                import models
                user_credit = models.get_user_credit(user_id) or 0.0
                
                if user_credit < charge_bch:
                    return {
                        'allowed': False,
                        'reason': 'insufficient_credit',
                        'message': f'Upload requires {charge_bch:.8f} BCH (${charge_usd:.2f}) but you only have {user_credit:.8f} BCH. Please add more credit.',
                        'overage_bytes': overage_bytes,
                        'overage_gb': round(overage_bytes / 1_073_741_824, 2),
                        'charge_amount_usd': charge_usd,
                        'charge_amount_bch': charge_bch,
                        'user_credit_bch': user_credit,
                        'requires_credit': True
                    }
                
                return {
                    'allowed': True,
                    'reason': 'overage_charged',
                    'message': f'Upload allowed. Overage of {self._format_bytes(overage_bytes)} will cost {charge_bch:.8f} BCH (${charge_usd:.2f})',
                    'will_charge': True,
                    'overage_bytes': overage_bytes,
                    'overage_gb': round(overage_bytes / 1_073_741_824, 2),
                    'charge_amount_usd': charge_usd,
                    'charge_amount_bch': charge_bch,
                    'user_credit_bch': user_credit,
                    'remaining_credit_after_bch': round(user_credit - charge_bch, 8)
                }
            
        except Exception as e:
            logger.error(f"❌ Failed to validate upload for {user_id}: {e}")
            raise
    
    def record_upload(self, user_id: str, username: str, filename: str,
                     file_size_bytes: int, file_type: str = None,
                     upload_url: str = None, post_id: int = None,
                     comment_id: int = None, use_credit: bool = False) -> Dict:
        """Record an upload transaction and charge if necessary
        
        Args:
            user_id: User ID
            username: Username
            filename: Uploaded filename
            file_size_bytes: File size in bytes
            file_type: MIME type or extension
            upload_url: URL where file was uploaded
            post_id: Associated post ID
            comment_id: Associated comment ID
            use_credit: Whether to use credit for overage
            
        Returns:
            Dict with transaction details
        """
        try:
            # Validate first
            validation = self.validate_upload(user_id, file_size_bytes, filename, username)
            
            if not validation['allowed']:
                raise ValueError(validation['message'])
            
            # If charging is required but user didn't consent, reject
            if validation['will_charge'] and not use_credit:
                raise ValueError("Upload requires credit charge. Please check 'Use Credit to Post' to proceed.")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create transaction record
            tx_id = str(uuid.uuid4())
            now = int(time.time())
            
            was_within_quota = not validation.get('will_charge', False)
            overage_bytes = validation.get('overage_bytes', 0)
            credit_charged = validation.get('charge_amount_bch', 0.0)
            
            cursor.execute("""
                INSERT INTO upload_transactions (
                    id, user_id, username, filename, file_size_bytes, file_type,
                    upload_url, was_within_quota, overage_bytes, credit_charged,
                    usd_per_4gb, status, post_id, comment_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?)
            """, (tx_id, user_id, username, filename, file_size_bytes, file_type,
                  upload_url, was_within_quota, overage_bytes, credit_charged,
                  self.OVERAGE_USD_PER_4GB, post_id, comment_id, now))
            
            # Charge credit if needed
            if validation['will_charge'] and credit_charged > 0:
                import sys
                import os
                sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
                import models
                
                success = models.deduct_credit(
                    user_id=user_id,
                    amount=credit_charged,
                    description=f"Upload overage charge for {filename} ({self._format_bytes(overage_bytes)})",
                    tx_id=tx_id
                )
                
                if not success:
                    raise ValueError("Failed to charge credit for upload overage")
                    
                logger.info(f"💰 Charged {credit_charged:.8f} BCH for upload overage: {user_id}")
            
            conn.commit()
            conn.close()
            
            # Get updated quota
            updated_quota = self.get_user_quota(user_id, username)
            
            return {
                'transaction_id': tx_id,
                'success': True,
                'charged': validation['will_charge'],
                'charge_amount_bch': credit_charged,
                'charge_amount_usd': validation.get('charge_amount_usd', 0.0),
                'quota': updated_quota
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to record upload for {user_id}: {e}")
            raise
    
    def get_user_uploads(self, user_id: str, limit: int = 50) -> list:
        """Get user's upload history
        
        Args:
            user_id: User ID
            limit: Maximum number of records to return
            
        Returns:
            List of upload transaction dicts
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    id, filename, file_size_bytes, file_type,
                    was_within_quota, overage_bytes, credit_charged,
                    status, created_at
                FROM upload_transactions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            
            uploads = []
            for row in cursor.fetchall():
                uploads.append({
                    'id': row['id'],
                    'filename': row['filename'],
                    'file_size_bytes': row['file_size_bytes'],
                    'file_size_mb': round(row['file_size_bytes'] / 1_048_576, 2),
                    'file_type': row['file_type'],
                    'was_within_quota': row['was_within_quota'],
                    'overage_bytes': row['overage_bytes'],
                    'overage_mb': round(row['overage_bytes'] / 1_048_576, 2) if row['overage_bytes'] else 0,
                    'credit_charged': row['credit_charged'],
                    'status': row['status'],
                    'created_at': row['created_at'],
                    'uploaded_at': datetime.fromtimestamp(row['created_at']).isoformat()
                })
            
            conn.close()
            return uploads
            
        except Exception as e:
            logger.error(f"❌ Failed to get uploads for {user_id}: {e}")
            raise
    
    def reset_quota_if_expired(self, user_id: str) -> bool:
        """Reset user's quota if the annual period has expired
        
        Args:
            user_id: User ID
            
        Returns:
            True if quota was reset, False otherwise
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = int(time.time())
            
            # Check if quota period has expired
            cursor.execute("""
                SELECT * FROM user_upload_quotas
                WHERE user_id = ? AND quota_end_date < ? AND is_active = TRUE
            """, (user_id, now))
            
            expired_quota = cursor.fetchone()
            
            if expired_quota:
                # Check if user still has active membership
                cursor.execute("""
                    SELECT * FROM user_memberships
                    WHERE user_id = ? AND is_active = TRUE
                """, (user_id,))
                membership = cursor.fetchone()
                
                if membership:
                    # Reset quota for new period
                    cursor.execute("""
                        UPDATE user_upload_quotas
                        SET used_bytes = 0,
                            quota_start_date = ?,
                            quota_end_date = ?,
                            updated_at = ?
                        WHERE user_id = ?
                    """, (membership[3], membership[4], now, user_id))  # purchased_at, expires_at
                    
                    conn.commit()
                    logger.info(f"🔄 Reset upload quota for user {user_id}")
                    conn.close()
                    return True
            
            conn.close()
            return False
            
        except Exception as e:
            logger.error(f"❌ Failed to reset quota for {user_id}: {e}")
            return False
    
    def _calculate_overage_charge(self, overage_bytes: int) -> float:
        """Calculate USD charge for overage bytes
        
        Args:
            overage_bytes: Number of bytes over quota
            
        Returns:
            Charge amount in USD
        """
        # $1 per 4GB, proportional for smaller amounts
        charge = (overage_bytes / self.BYTES_PER_4GB) * self.OVERAGE_USD_PER_4GB
        
        # Minimum charge
        if charge < self.MIN_CHARGE_USD:
            charge = self.MIN_CHARGE_USD
        
        return round(charge, 2)
    
    def _format_bytes(self, bytes_value: int) -> str:
        """Format bytes to human-readable string
        
        Args:
            bytes_value: Number of bytes
            
        Returns:
            Formatted string (e.g., "1.5 MB")
        """
        if bytes_value < 1024:
            return f"{bytes_value} B"
        elif bytes_value < 1_048_576:
            return f"{round(bytes_value / 1024, 2)} KB"
        elif bytes_value < 1_073_741_824:
            return f"{round(bytes_value / 1_048_576, 2)} MB"
        else:
            return f"{round(bytes_value / 1_073_741_824, 2)} GB"
    
    def get_pricing_config(self) -> Dict:
        """Get current pricing configuration
        
        Returns:
            Dict with pricing info
        """
        return {
            'free_user_limit_bytes': self.FREE_USER_LIMIT_BYTES,
            'free_user_limit_kb': round(self.FREE_USER_LIMIT_BYTES / 1024, 2),
            'member_annual_quota_bytes': self.MEMBER_ANNUAL_QUOTA_BYTES,
            'member_annual_quota_gb': round(self.MEMBER_ANNUAL_QUOTA_BYTES / 1_073_741_824, 2),
            'overage_usd_per_4gb': self.OVERAGE_USD_PER_4GB,
            'min_charge_usd': self.MIN_CHARGE_USD,
            'recommended_formats': ['jpg', 'jpeg']
        }
