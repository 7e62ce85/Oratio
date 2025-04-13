# from flask import Flask, jsonify, request, render_template, redirect, url_for, session
# import uuid
# import time
# import json
# import os
# import requests
# from datetime import datetime, timedelta
# import qrcode
# from io import BytesIO
# import base64
# import sqlite3
# import hashlib
# import hmac
# import threading
# import logging
# from functools import wraps
# from werkzeug.exceptions import BadRequest
# from direct_payment import direct_payment_handler

# # 로깅 설정 - 먼저 로거를 초기화해야 함
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
#     handlers=[
#         logging.StreamHandler(),
#         logging.FileHandler('bch_payment.log')
#     ]
# )
# logger = logging.getLogger('bch_payment')

# # 직접 결제 모듈 가져오기
# try:
#     from direct_payment import direct_payment_handler
#     DIRECT_MODE = True
#     logger.info("직접 결제 모드 활성화")
# except ImportError:
#     DIRECT_MODE = False
#     logger.warning("직접 결제 모듈을 불러올 수 없습니다. ElectronCash 모드만 사용합니다.")

# # 환경 변수에서 지갑 주소 가져오기
# PAYOUT_WALLET = os.environ.get('PAYOUT_WALLET', 'bitcoincash:qz394b323707f3488f84112542799648')

# app = Flask(__name__)
# app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))

# # 환경 설정
# MOCK_MODE = os.environ.get('MOCK_MODE', 'false').lower() == 'true'
# ELECTRON_CASH_URL = os.environ.get('ELECTRON_CASH_URL', 'http://electron-cash:7777')
# ELECTRON_CASH_USER = os.environ.get('ELECTRON_CASH_USER', 'bchrpc')
# ELECTRON_CASH_PASSWORD = os.environ.get('ELECTRON_CASH_PASSWORD', '')
# LEMMY_API_URL = os.environ.get('LEMMY_API_URL', 'http://lemmy:8536')
# LEMMY_API_KEY = os.environ.get('LEMMY_API_KEY', '')
# TESTNET = os.environ.get('TESTNET', 'true').lower() == 'true'
# MIN_CONFIRMATIONS = int(os.environ.get('MIN_CONFIRMATIONS', '1'))
# # 환경 변수에서 지갑 주소 가져오기
# PAYOUT_WALLET = os.environ.get('PAYOUT_WALLET', 'bitcoincash:qz394b323707f3488f84112542799648')
# MIN_PAYOUT_AMOUNT = float(os.environ.get('MIN_PAYOUT_AMOUNT', '0.01'))  # 최소 출금 금액
# FORWARD_PAYMENTS = os.environ.get('FORWARD_PAYMENTS', 'true').lower() == 'true'

# # 데이터베이스 설정
# DB_PATH = os.environ.get('DB_PATH', '/data/payments.db')

# def init_db():
#     """데이터베이스 초기화"""
#     # ...existing code...

# # 데이터베이스 초기화
# init_db()

# # API 인증 데코레이터
# def require_api_key(f):
#     # ...existing code...

# # Electron Cash JSON-RPC 클라이언트
# class ElectronCashClient:
#     def __init__(self, url=ELECTRON_CASH_URL):
#         # ...existing code...
        
#     def call_method(self, method, params=None):
#         # ...existing code...
    
#     def get_new_address(self):
#         """새 BCH 주소 생성"""
#         # 직접 결제 모드에서는 Coinomi 주소를 사용
#         if DIRECT_MODE:
#             logger.info(f"직접 결제 모드: Coinomi 지갑 주소 사용 ({PAYOUT_WALLET})")
#             return PAYOUT_WALLET

#         # ElectronCash 실패시 직접 처리기 사용
#         direct_address = direct_payment_handler.get_address()
#         logger.info(f"직접 결제 주소 사용: {direct_address}")
#         return direct_address

#     def check_address_balance(self, address):
#         """주소의 잔액 확인"""
#         try:
#             # 직접 결제 모드에서는 API를 통해 잔액 확인
#             if DIRECT_MODE:
#                 return direct_payment_handler.check_address_balance(address)
                
#             if MOCK_MODE:
#                 # Mock 모드: 지불 시뮬레이션
#                 conn = sqlite3.connect(DB_PATH)
#                 cursor = conn.cursor()
#                 cursor.execute(
#                     "SELECT id, amount, created_at FROM invoices WHERE payment_address = ? AND status = 'pending'", 
#                     (address,)
#                 )
#                 result = cursor.fetchone()
#                 conn.close()
                
#                 if result:
#                     invoice_id, amount, created_at = result
#                     # 1분 후 지불 시뮬레이션
#                     if time.time() - created_at > 60:
#                         return amount
#                 return 0.0
#             else:
#                 # 실제 잔액 확인
#                 result = self.call_method("getaddressbalance", [address])
#                 if result and "confirmed" in result:
#                     # satoshi를 BCH로 변환
#                     return float(result["confirmed"]) / 100000000.0
#                 return 0.0
                    
#         except Exception as e:
#             logger.error(f"잔액 확인 오류: {str(e)}")
#             return 0.0    

#     def get_transaction_confirmations(self, tx_hash):
#         """트랜잭션 확인 수 확인"""
#         # 직접 결제 모드에서는 API를 통해 확인
#         if DIRECT_MODE:
#             return direct_payment_handler.get_transaction_confirmations(tx_hash)
        
#         # ElectronCash 실패시 직접 처리기 사용
#         return direct_payment_handler.get_transaction_confirmations(tx_hash)

# # Electron Cash 클라이언트 초기화
# electron_cash = ElectronCashClient()

# @app.route('/')
# def index():
#     # ...existing code...

# # ...existing code...

# @app.route('/check_payment/<invoice_id>', methods=['GET'])
# def check_payment(invoice_id):
#     """결제 상태 확인"""
#     # ...existing code...
    
#     # 대기 중인 경우: 잔액 확인
#     balance = electron_cash.check_address_balance(invoice["payment_address"])
    
#     # 직접 결제 모드에서 트랜잭션 확인
#     if DIRECT_MODE and invoice["status"] == "pending":
#         # 트랜잭션 검색
#         tx_info = direct_payment_handler.find_payment_transaction(
#             invoice["payment_address"], 
#             invoice["amount"],
#             invoice["created_at"]
#         )
        
#         if tx_info:
#             # 지불 확인
#             paid_at = int(time.time())
#             tx_hash = tx_info["txid"]
            
#             cursor.execute(
#                 "UPDATE invoices SET status = 'paid', paid_at = ?, tx_hash = ?, confirmations = ? WHERE id = ?",
#                 (paid_at, tx_hash, tx_info["confirmations"], invoice_id)
#             )
            
#             invoice["status"] = "paid"
#             invoice["paid_at"] = paid_at
#             invoice["tx_hash"] = tx_hash
#             invoice["confirmations"] = tx_info["confirmations"]
            
#             # 충분한 확인이 있으면 완료로 처리
#             if tx_info["confirmations"] >= MIN_CONFIRMATIONS:
#                 cursor.execute(
#                     "UPDATE invoices SET status = 'completed' WHERE id = ?",
#                     (invoice_id,)
#                 )
#                 invoice["status"] = "completed"
                
#                 # 사용자 크레딧 추가
#                 if invoice["user_id"]:
#                     credit_user(invoice["user_id"], invoice["amount"], invoice_id)

#     if balance >= invoice["amount"]:
#         # 지불 확인
#         paid_at = int(time.time())
#         tx_hash = "mock_tx_" + invoice_id if MOCK_MODE else None  # 실제에서는 트랜잭션 해시 확인 필요
        
#         cursor.execute(
#             "UPDATE invoices SET status = 'paid', paid_at = ?, tx_hash = ? WHERE id = ?",
#             (paid_at, tx_hash, invoice_id)
#         )
        
#         invoice["status"] = "paid"
#         invoice["paid_at"] = paid_at
#         invoice["tx_hash"] = tx_hash
        
#     conn.commit()
#     conn.close()
#     return jsonify(invoice)

# # ...existing code...

# if __name__ == "__main__":
#     # ...existing code...