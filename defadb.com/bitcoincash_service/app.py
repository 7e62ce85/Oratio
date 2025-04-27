from flask import Flask, jsonify, send_from_directory, render_template
import os
import traceback
import werkzeug.exceptions
import requests

# 설정 모듈 가져오기
from config import (
    FLASK_SECRET_KEY, logger, MOCK_MODE, TESTNET, DIRECT_MODE,
    FORWARD_PAYMENTS, DB_PATH
)

# 라우트 모듈 가져오기
from routes.invoice import invoice_bp
from routes.api import api_bp

# 서비스 모듈 가져오기
from services.background_tasks import start_background_tasks
from services.electron_cash import electron_cash

# Flask 애플리케이션 초기화
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# 외부에서 electron_cash를 참조할 수 있도록 전역으로 노출
# 이를 통해 `from app import electron_cash` 구문이 동작합니다
globals()['electron_cash'] = electron_cash

# 외부에서 사용할 수 있는 함수들 노출
def forward_to_payout_wallet():
    """출금 지갑으로 자금을 전송하는 함수"""
    return electron_cash.forward_to_payout_wallet()

# Blueprint 등록
app.register_blueprint(invoice_bp)
app.register_blueprint(api_bp)

# 정적 파일 제공
@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory('static', path)

# 메인 페이지
@app.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')

# 전역 예외 처리
@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler for the app"""
    logger.error(f"Unhandled exception: {str(e)}")
    logger.error(traceback.format_exc())
    
    if isinstance(e, requests.exceptions.RequestException):
        # Handle connection errors to ElectronCash
        error_message = str(e)
        if "401" in error_message:
            logger.error("ElectronCash authentication failed. Check RPC username and password.")
            return jsonify({"error": "Authentication to payment service failed. Please try again."}), 503
        return jsonify({"error": "Service temporarily unavailable, please try again later"}), 503
    
    if isinstance(e, werkzeug.exceptions.NotFound):
        return "Page not found", 404
    
    return jsonify({"error": "An unexpected error occurred"}), 500

if __name__ == "__main__":
    # 데이터 디렉토리 생성
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    # 백그라운드 작업 시작
    start_background_tasks()
    
    # 주기적으로 자금을 출금 지갑으로 전송 (시작 시 한 번 실행)
    if FORWARD_PAYMENTS:
        electron_cash.forward_to_payout_wallet()
    
    # 앱 실행
    debug_mode = os.environ.get('FLASK_ENV', 'production') == 'development'
    app.run(host="0.0.0.0", port=8081, debug=debug_mode)