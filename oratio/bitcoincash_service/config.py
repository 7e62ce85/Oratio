import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('bch-payment-service')

# Flask configuration
DEBUG = True
SECRET_KEY = 'your-secret-key'  # Replace with a real secret key in production
FLASK_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'secure_random_key')
SQLALCHEMY_DATABASE_URI = 'sqlite:///data/payments.db'
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Database path
DB_PATH = os.environ.get('DB_PATH', '/data/payments.db')

# Electron-Cash configuration
ELECTRON_CASH_URL = os.environ.get('ELECTRON_CASH_URL', 'http://electron-cash:7777')
ELECTRON_CASH_USER = os.environ.get('ELECTRON_CASH_USER', 'bchrpc')
ELECTRON_CASH_PASSWORD = os.environ.get('ELECTRON_CASH_PASSWORD', 'secure_password_change_me')
EC_AVAILABLE = True  # Flag to indicate if Electron Cash is available

# Bitcoin Cash configuration
CONFIRMATIONS_REQUIRED = int(os.environ.get('MIN_CONFIRMATIONS', 1))  # Number of confirmations required for a payment to be considered valid
# Add MIN_CONFIRMATIONS as alias for CONFIRMATIONS_REQUIRED for backward compatibility
MIN_CONFIRMATIONS = CONFIRMATIONS_REQUIRED
PAYOUT_WALLET = os.environ.get('PAYOUT_WALLET', 'bitcoincash:qr2u4f2psj0enj83l3s8qx53p6nhlrmcfcdhgphl4d')  # Valid BCH wallet address

# Application settings
MOCK_MODE = os.environ.get('MOCK_MODE', 'false').lower() == 'true'
TESTNET = os.environ.get('TESTNET', 'false').lower() == 'true'
DIRECT_MODE = os.environ.get('DIRECT_MODE', 'false').lower() == 'true'
FORWARD_PAYMENTS = os.environ.get('FORWARD_PAYMENTS', 'true').lower() == 'true'

# Lemmy API configuration
LEMMY_API_URL = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
LEMMY_API_KEY = os.environ.get('LEMMY_API_KEY', 'changeme')
LEMMY_ADMIN_USER = os.environ.get('LEMMY_ADMIN_USER', '')
LEMMY_ADMIN_PASS = os.environ.get('LEMMY_ADMIN_PASS', '')
