#!/usr/bin/env python3
"""
Resend API를 사용한 이메일 발송 프록시 서버
SendGrid보다 더 간단하고 현대적인 API
"""

import os
import logging
from flask import Flask, request, jsonify
import requests
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
import threading
import time

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Resend API 키 (환경변수에서 가져옴)
RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
FROM_EMAIL = os.environ.get('SMTP_FROM_ADDRESS', 'noreply@oratio.space')

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
            payload["text"] = content_text
            
        headers = {
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(url, json=payload, headers=headers)
        
        if response.status_code in [200, 201]:
            logger.info(f"이메일 발송 성공: {to_email}")
            return True
        else:
            logger.error(f"이메일 발송 실패: {response.status_code}, {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"Resend 에러: {str(e)}")
        return False

class FakeSMTPServer:
    """가짜 SMTP 서버 - HTTP API로 이메일을 전달"""
    
    def __init__(self, host='localhost', port=1025):
        self.host = host
        self.port = port
        self.running = False
        
    def start(self):
        """서버 시작"""
        import socket
        import socketserver
        import email
        from email.parser import Parser
        
        class SMTPHandler(socketserver.BaseRequestHandler):
            def handle(self):
                logger.info(f"SMTP 연결: {self.client_address}")
                
                # SMTP 프로토콜 시뮬레이션
                self.request.sendall(b"220 localhost ESMTP\r\n")
                
                mail_from = None
                rcpt_to = []
                data_mode = False
                email_data = b""
                
                while True:
                    try:
                        data = self.request.recv(1024)
                        if not data:
                            break
                            
                        command = data.decode('utf-8', errors='ignore').strip()
                        logger.info(f"SMTP 명령: {command}")
                        
                        if command.startswith('EHLO') or command.startswith('HELO'):
                            self.request.sendall(b"250 Hello\r\n")
                        elif command.startswith('MAIL FROM:'):
                            mail_from = command.split(':', 1)[1].strip().strip('<>')
                            self.request.sendall(b"250 OK\r\n")
                        elif command.startswith('RCPT TO:'):
                            rcpt = command.split(':', 1)[1].strip().strip('<>')
                            rcpt_to.append(rcpt)
                            self.request.sendall(b"250 OK\r\n")
                        elif command == 'DATA':
                            self.request.sendall(b"354 Start mail input\r\n")
                            data_mode = True
                        elif data_mode:
                            if command == '.':
                                # 이메일 처리
                                self.process_email(mail_from, rcpt_to, email_data)
                                self.request.sendall(b"250 OK\r\n")
                                data_mode = False
                                email_data = b""
                            else:
                                email_data += data
                        elif command == 'QUIT':
                            self.request.sendall(b"221 Bye\r\n")
                            break
                        else:
                            self.request.sendall(b"250 OK\r\n")
                            
                    except Exception as e:
                        logger.error(f"SMTP 처리 에러: {e}")
                        break
                        
            def process_email(self, mail_from, rcpt_to, email_data):
                """이메일 데이터를 파싱하고 Resend로 발송"""
                try:
                    # 이메일 파싱
                    email_str = email_data.decode('utf-8', errors='ignore')
                    msg = email.message_from_string(email_str)
                    
                    subject = msg.get('Subject', '제목 없음')
                    
                    # 본문 추출
                    body_text = ""
                    body_html = ""
                    
                    if msg.is_multipart():
                        for part in msg.walk():
                            content_type = part.get_content_type()
                            if content_type == "text/plain":
                                body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                            elif content_type == "text/html":
                                body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    else:
                        body_text = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
                    
                    # 각 수신자에게 발송
                    for to_email in rcpt_to:
                        success = send_email_via_resend(
                            to_email=to_email,
                            subject=subject,
                            content_text=body_text,
                            content_html=body_html if body_html else None
                        )
                        
                        if success:
                            logger.info(f"이메일 발송 완료: {mail_from} -> {to_email}")
                        else:
                            logger.error(f"이메일 발송 실패: {mail_from} -> {to_email}")
                            
                except Exception as e:
                    logger.error(f"이메일 처리 에러: {e}")
        
        # TCP 서버 시작
        server = socketserver.TCPServer((self.host, self.port), SMTPHandler)
        server.allow_reuse_address = True
        
        self.running = True
        logger.info(f"가짜 SMTP 서버 시작: {self.host}:{self.port}")
        
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("SMTP 서버 중지")
        finally:
            self.running = False
            server.shutdown()

@app.route('/health')
def health():
    return jsonify({"status": "ok", "service": "email-proxy-resend"})

@app.route('/send', methods=['POST'])
def send_email():
    """HTTP API로 직접 이메일 발송"""
    try:
        data = request.json
        to_email = data.get('to')
        subject = data.get('subject')
        content = data.get('content')
        content_type = data.get('content_type', 'text/plain')
        
        if not all([to_email, subject, content]):
            return jsonify({"error": "Missing required fields"}), 400
        
        if content_type == 'text/html':
            success = send_email_via_resend(to_email, subject, "", content)
        else:
            success = send_email_via_resend(to_email, subject, content)
        
        if success:
            return jsonify({"status": "sent"})
        else:
            return jsonify({"error": "Failed to send email"}), 500
            
    except Exception as e:
        logger.error(f"API 에러: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    if not RESEND_API_KEY:
        logger.error("RESEND_API_KEY 환경변수가 설정되지 않았습니다!")
        exit(1)
    
    # SMTP 서버를 별도 스레드에서 실행
    smtp_server = FakeSMTPServer(host='0.0.0.0', port=1025)
    smtp_thread = threading.Thread(target=smtp_server.start)
    smtp_thread.daemon = True
    smtp_thread.start()
    
    # Flask HTTP API 서버 시작
    app.run(host='0.0.0.0', port=8025, debug=False)
