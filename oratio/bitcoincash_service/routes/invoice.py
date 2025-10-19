from flask import Blueprint, jsonify, request, render_template, redirect, url_for, make_response
import uuid
import time
import qrcode
from io import BytesIO
import base64
from config import logger, TESTNET, MIN_CONFIRMATIONS
import models
from services.electron_cash import electron_cash
from services.payment import process_payment, format_invoice_for_display
from jwt_utils import get_user_id_from_request

# Blueprint 생성
invoice_bp = Blueprint('invoice', __name__)

@invoice_bp.route('/generate_invoice', methods=['GET'])
def generate_invoice():
    """새 인보이스 생성"""
    # 파라미터 가져오기 (JWT에서 자동으로 추출하거나 URL 파라미터 사용)
    amount = request.args.get('amount', type=float)
    user_id = get_user_id_from_request()
    
    if not amount or amount <= 0:
        return jsonify({"error": "Invalid amount"}), 400
    
    # 사용자 ID 검증
    if not user_id:
        return jsonify({"error": "User ID is required. Please login first."}), 400
    
    # 최소 금액 확인 (실제 구현 시 조정)
    min_amount = 0.0001  # BCH
    if amount < min_amount:
        return jsonify({"error": f"Amount must be at least {min_amount} BCH"}), 400
    
    # Generate a new address with direct ElectronCash command
    try:
        # Try to force ElectronCash to give us a new address
        logger.info("ElectronCash에서 확실한 새 주소 생성 시도 중...")
        # Make direct call to ensure we get a new address
        payment_address = electron_cash.get_new_address()
        logger.info(f"새 주소 생성 성공: {payment_address}")
    except Exception as e:
        logger.error(f"주소 생성 오류: {str(e)}")
        return jsonify({"error": "주소 생성 중 오류가 발생했습니다."}), 500
    
    # 인보이스 생성
    invoice_data = models.create_invoice(payment_address, amount, user_id)
    
    # 응답 반환
    if request.headers.get('Accept', '').find('application/json') != -1:
        return jsonify(invoice_data)
    else:
        return redirect(url_for('invoice.view_invoice', invoice_id=invoice_data['invoice_id']))

@invoice_bp.route('/invoice/<invoice_id>')
def view_invoice(invoice_id):
    """인보이스 조회 페이지"""
    invoice = models.get_invoice(invoice_id)
    
    if not invoice:
        return render_template('error.html', message="인보이스를 찾을 수 없습니다"), 404
    
    # QR 코드 생성
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    
    # BCH URI 스키마
    # Add 'bitcoincash:' prefix if it's not already included
    payment_address = invoice['payment_address']
    if not payment_address.startswith('bitcoincash:'):
        payment_address = f"bitcoincash:{payment_address.replace('bitcoincash:', '')}"
    
    qr_content = f"{payment_address}?amount={invoice['amount']}"
    qr.add_data(qr_content)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    # 인보이스 정보 포맷팅
    formatted_invoice = format_invoice_for_display(invoice)
    
    return render_template(
        'invoice.html', 
        invoice=formatted_invoice,
        qr_code=img_str,
        min_confirmations=MIN_CONFIRMATIONS,
        testnet=TESTNET
    )

@invoice_bp.route('/check_payment/<invoice_id>', methods=['GET'])
def check_payment(invoice_id):
    """결제 상태 확인"""
    max_retries = 3
    retry_count = 0
    retry_delay = 2  # seconds
    
    while retry_count < max_retries:
        try:
            # 결제 처리 로직 실행
            invoice = process_payment(invoice_id)
            
            if not invoice:
                return jsonify({"error": "Invoice not found"}), 404
            
            return jsonify(invoice)
            
        except Exception as e:
            retry_count += 1
            logger.error(f"결제 확인 중 오류 발생 (시도 {retry_count}/{max_retries}): {str(e)}")
            
            if retry_count < max_retries:
                time.sleep(retry_delay)
            else:
                return jsonify({"error": "결제 확인 중 오류가 발생했습니다"}), 500

@invoice_bp.route('/payment_success/<invoice_id>')
def payment_success(invoice_id):
    """결제 성공 페이지 렌더링"""
    invoice = models.get_invoice(invoice_id)
    
    if not invoice or invoice['status'] != 'completed':
        return render_template('error.html', message="완료된 결제를 찾을 수 없습니다"), 404
    
    # 템플릿에 전달할 데이터 준비
    tx_hash = invoice['tx_hash']
    
    # 디버깅을 위해 tx_hash가 None이면 샘플 값 설정
    if not tx_hash:
        tx_hash = "debug_sample_tx_hash_for_testing"
        logger.info(f"인보이스 {invoice_id}에 샘플 tx_hash 적용: {tx_hash}")
    
    amount = invoice['amount']
    user_id = invoice['user_id']
    
    # 크레딧 정보 가져오기 (사용자 ID가 있는 경우)
    credit_added = False
    total_credit = 0
    if user_id:
        # get_user_credit는 float 값을 반환하므로 바로 사용
        total_credit = models.get_user_credit(user_id)
        if total_credit > 0:
            credit_added = True
    
    # 디버깅 로그 추가
    logger.info(f"payment_success 렌더링: invoice_id={invoice_id}, tx_hash={tx_hash}, amount={amount}")
    
    # Prevent caching of this page
    response = make_response(render_template(
        'payment_success.html', 
        invoice_id=invoice_id, 
        tx_hash=tx_hash,
        amount=amount,
        user_id=user_id,
        credit_added=credit_added,
        total_credit=total_credit
    ))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response