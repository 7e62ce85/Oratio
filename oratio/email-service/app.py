#!/usr/bin/env python3
"""
Resend API를 사용한 이메일 발송 프록시 서버
- aiosmtpd: 안정적인 SMTP 서버 (포트 1025)
- Flask: HTTP API (포트 8025)
"""

import os
import sys
import logging
import email
import email.policy
import asyncio
import threading
import time

from flask import Flask, request, jsonify
import requests
from aiosmtpd.controller import Controller

app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('email-service')

# Resend API 키 (환경변수에서 가져옴)
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
FROM_EMAIL = os.environ.get('SMTP_FROM_ADDRESS', 'noreply@oratio.space')

# ── Resend 발송 ──────────────────────────────────────────────

def send_email_via_resend(to_email, subject, content_text, content_html=None):
    """Resend API를 사용해서 이메일 발송"""
    try:
        url = "https://api.resend.com/emails"

        payload = {
            "from": FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
        }

        if content_html:
            payload["html"] = content_html
        else:
            payload["text"] = content_text or "(no body)"

        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        }

        response = requests.post(url, json=payload, headers=headers, timeout=15)

        if response.status_code in [200, 201]:
            logger.info(f"Resend OK -> {to_email} (subject={subject!r})")
            return True
        else:
            logger.error(
                f"Resend FAIL: HTTP {response.status_code} -> {response.text}"
            )
            return False

    except Exception as e:
        logger.error(f"Resend exception: {e}")
        return False


# ── aiosmtpd 핸들러 ──────────────────────────────────────────

class ResendSMTPHandler:
    """aiosmtpd 메시지 핸들러 - 수신한 이메일을 Resend API로 전달"""

    async def handle_DATA(self, server, session, envelope):
        mail_from = envelope.mail_from
        rcpt_tos = envelope.rcpt_tos
        raw = envelope.content

        logger.info(f"SMTP DATA: from={mail_from} to={rcpt_tos}")

        try:
            if isinstance(raw, bytes):
                msg = email.message_from_bytes(raw, policy=email.policy.default)
            else:
                msg = email.message_from_string(raw, policy=email.policy.default)

            subject = msg.get('Subject', '(no subject)')

            # 본문 추출
            body_text = ""
            body_html = ""

            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    if ct == "text/plain" and not body_text:
                        body_text = part.get_content()
                    elif ct == "text/html" and not body_html:
                        body_html = part.get_content()
            else:
                ct = msg.get_content_type()
                content = msg.get_content()
                if ct == "text/html":
                    body_html = content
                else:
                    body_text = content

            # 각 수신자에게 발송
            for to_addr in rcpt_tos:
                success = send_email_via_resend(
                    to_email=to_addr,
                    subject=subject,
                    content_text=body_text,
                    content_html=body_html or None,
                )
                if not success:
                    logger.warning(f"Send failed but returning 250 anyway (to={to_addr})")

        except Exception as e:
            logger.error(f"Email processing error: {e}", exc_info=True)

        # Lemmy(lettre)가 타임아웃 없이 정상 응답을 받도록 항상 250 반환
        return '250 OK'


# ── SMTP 서버 시작 (별도 스레드) ──────────────────────────────

def run_smtp_server():
    """aiosmtpd SMTP 서버를 asyncio 이벤트 루프에서 실행"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    handler = ResendSMTPHandler()
    controller = Controller(
        handler,
        hostname='0.0.0.0',
        port=1025,
        ready_timeout=10,
    )
    controller.start()
    logger.info("SMTP server started on 0.0.0.0:1025")

    # 컨트롤러가 별도 스레드에서 돌므로 여기서 무한 대기
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        controller.stop()


# ── Flask HTTP API ────────────────────────────────────────────

@app.route('/health')
def health():
    return jsonify({"status": "ok", "service": "email-proxy-resend"})


@app.route('/send', methods=['POST'])
def send_email_api():
    """HTTP API로 직접 이메일 발송"""
    try:
        data = request.json
        to_email = data.get('to')
        subject = data.get('subject')
        content = data.get('content')
        content_type = data.get('content_type', 'text/plain')

        if not all([to_email, subject, content]):
            return jsonify({"error": "Missing required fields: to, subject, content"}), 400

        if content_type == 'text/html':
            success = send_email_via_resend(to_email, subject, "", content)
        else:
            success = send_email_via_resend(to_email, subject, content)

        if success:
            return jsonify({"status": "sent"})
        else:
            return jsonify({"error": "Failed to send email via Resend"}), 500

    except Exception as e:
        logger.error(f"API error: {e}")
        return jsonify({"error": str(e)}), 500


# ── main ──────────────────────────────────────────────────────

if __name__ == '__main__':
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY is not set!")
        sys.exit(1)

    logger.info(f"FROM_EMAIL = {FROM_EMAIL}")
    logger.info(f"RESEND_API_KEY = {RESEND_API_KEY[:8]}...")

    # SMTP 서버를 데몬 스레드로 실행
    smtp_thread = threading.Thread(target=run_smtp_server, daemon=True, name='smtp-server')
    smtp_thread.start()

    # SMTP 서버가 바인드될 시간을 잠시 대기
    time.sleep(1)

    # Flask HTTP API 서버 시작
    logger.info("Flask HTTP API started on 0.0.0.0:8025")
    app.run(host='0.0.0.0', port=8025, debug=False)
