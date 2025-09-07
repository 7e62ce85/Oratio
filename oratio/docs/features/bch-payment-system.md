# Bitcoin Cash 결제 시스템 개발 문서

## 📋 개요
Lemmy UI의 디자인 시스템을 참조하여 Bitcoin Cash 결제 서비스의 UI/UX를 현대적이고 일관된 디자인으로 개선한 프로젝트입니다.

## 🎯 프로젝트 목표
- Rust-Lemmy 포럼과 BCH 결제 시스템의 완벽한 통합
- 사용자 친화적인 결제 인터페이스 제공
- 환불 불가 정책에 대한 명확한 안내
- 모바일 반응형 디자인 지원

## 🏗️ 시스템 아키텍처

### 컴포넌트 구조
```
┌─────────────────────┐    ┌─────────────────────┐
│   Lemmy Frontend    │    │   BCH Payment UI    │
│   (Custom UI)       │────│   (Flask Backend)   │
│                     │    │                     │
└─────────────────────┘    └─────────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐    ┌─────────────────────┐
│   Lemmy Backend     │    │   ElectronCash      │
│   (Rust)            │    │   Wallet            │
│                     │    │                     │
└─────────────────────┘    └─────────────────────┘
           │                           │
           ▼                           ▼
┌─────────────────────┐    ┌─────────────────────┐
│   PostgreSQL        │    │   SQLite            │
│   (Forum Data)      │    │   (Payment Data)    │
└─────────────────────┘    └─────────────────────┘
```

## ✨ 주요 기능

### 1. UI/UX 개선사항

#### 1.1 디자인 시스템 통합
- **CSS 변수 시스템**: Lemmy UI와 동일한 색상 체계 적용
- **타이포그래피**: Apple 시스템 폰트 스택 적용
  ```css
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, 
               "Helvetica Neue", Arial, sans-serif;
  ```
- **컴포넌트 일관성**: 카드, 버튼, 알림 등 UI 컴포넌트 스타일 통일
- **반응형 디자인**: 모바일 우선 접근법으로 다양한 화면 크기 지원

#### 1.2 네비게이션 개선
- **상단 네비게이션 바**: 모든 페이지에 defadb 브랜딩 일관성 유지
- **브레드크럼**: 사용자 위치 파악 및 네비게이션 향상
- **명확한 CTA 버튼**: 주요 액션 버튼 시각적 강조

#### 1.3 사용자 경험 개선
- **직관적인 상태 표시**: 배지 시스템으로 결제 상태 시각화
- **진행 상황 표시**: 결제 과정별 명확한 안내
- **향상된 피드백**: 버튼 상태, 로딩 인디케이터, 성공/실패 메시지

### 2. 보안 및 정책 강화

#### 2.1 환불 불가 정책 구현
- **메인 페이지**: 상단에 눈에 띄는 경고 배너 추가
- **결제 페이지**: 결제 진행 전 재확인 경고
- **완료 페이지**: 정책 재안내 및 증빙 자료 보관 안내

#### 2.2 사용자 안전 조치
- **주소 복사 개선**: 클립보드 API 사용으로 안전한 주소 복사
- **QR 코드 스타일링**: 명확한 스캔 가이드 제공
- **트랜잭션 추적**: Blockchair 링크로 투명성 증대

## 🔧 기술 스택

### 백엔드
- **언어**: Python 3.9+
- **프레임워크**: Flask
- **지갑 통합**: ElectronCash JSON-RPC
- **데이터베이스**: SQLite (결제 데이터)
- **인증**: API 키 기반 인증

### 프론트엔드
- **기본**: Lemmy UI (Inferno.js 기반)
- **스타일링**: Bootstrap 5 + Custom CSS
- **아이콘**: Bootstrap Icons
- **반응형**: Mobile-first 디자인

### 인프라
- **컨테이너**: Docker Compose
- **웹서버**: Nginx (리버스 프록시)
- **SSL**: Let's Encrypt 인증서
- **모니터링**: Docker 내장 헬스체크

## 📁 프로젝트 구조

```
bitcoincash_service/
├── app.py                 # Flask 메인 애플리케이션
├── config.py             # 설정 관리
├── models.py             # 데이터베이스 모델
├── requirements.txt      # Python 패키지 목록
├── routes/
│   ├── payment.py        # 결제 관련 라우트
│   ├── api.py           # API 엔드포인트
│   └── dashboard.py     # 관리자 대시보드
├── services/
│   ├── electron_cash.py  # ElectronCash 통합
│   ├── blockchain.py    # 블록체인 조회
│   └── notification.py  # 알림 서비스
├── static/
│   ├── css/             # 스타일시트
│   ├── js/              # JavaScript 파일
│   └── images/          # 이미지 리소스
├── templates/
│   ├── base.html        # 기본 템플릿
│   ├── payment/         # 결제 관련 템플릿
│   └── admin/           # 관리자 템플릿
└── data/
    └── payment.db       # SQLite 데이터베이스
```

## 🚀 API 엔드포인트

### 공개 API
```
GET  /health                        # 서비스 상태 확인
GET  /api/user_credit/<user_id>     # 사용자 크레딧 조회 (ID)
GET  /api/user_credit/<username>    # 사용자 크레딧 조회 (사용자명)
GET  /api/transactions/<user_id>    # 거래 내역 조회 (ID)
GET  /api/transactions/<username>   # 거래 내역 조회 (사용자명)
```

### 결제 인터페이스
```
GET  /                             # 메인 페이지
POST /create_invoice               # 인보이스 생성
GET  /payment/<invoice_id>         # 결제 페이지
POST /check_payment/<invoice_id>   # 결제 상태 확인
GET  /success/<invoice_id>         # 결제 완료 페이지
```

### 관리자 API
```
GET  /admin                        # 관리자 대시보드
GET  /admin/invoices              # 인보이스 관리
GET  /admin/users                 # 사용자 관리
POST /admin/manual_credit         # 수동 크레딧 추가
```

## 💳 결제 처리 플로우

### 1. 인보이스 생성
```python
def create_invoice(amount, user_id, description):
    # 1. ElectronCash에서 새 주소 생성
    address = electron_cash.get_new_address()
    
    # 2. 인보이스 데이터베이스 저장
    invoice = Invoice(
        amount=amount,
        address=address,
        user_id=user_id,
        description=description,
        status='pending'
    )
    db.session.add(invoice)
    db.session.commit()
    
    # 3. QR 코드 생성
    qr_code = generate_qr_code(f"bitcoincash:{address}?amount={amount}")
    
    return invoice, qr_code
```

### 2. 결제 모니터링
```python
def monitor_payment(invoice_id):
    invoice = Invoice.query.get(invoice_id)
    
    # 1. 블록체인에서 트랜잭션 확인
    transactions = blockchain.get_address_transactions(invoice.address)
    
    for tx in transactions:
        if tx['amount'] >= invoice.amount and tx['confirmations'] >= 1:
            # 2. 결제 확인됨
            invoice.status = 'confirmed'
            invoice.tx_hash = tx['hash']
            
            # 3. 사용자 크레딧 추가
            add_user_credit(invoice.user_id, invoice.amount)
            
            # 4. 알림 발송
            send_payment_notification(invoice)
            
            break
    
    return invoice.status
```

### 3. 사용자 크레딧 관리
```python
def add_user_credit(user_id, amount):
    # Lemmy API를 통해 사용자 정보 조회
    user = lemmy_api.get_user(user_id)
    
    # 크레딧 기록 생성
    credit = UserCredit(
        user_id=user_id,
        username=user['name'],
        amount=amount,
        transaction_type='payment',
        created_at=datetime.utcnow()
    )
    
    db.session.add(credit)
    db.session.commit()
    
    return credit
```

## 🎨 UI 컴포넌트

### 1. 결제 버튼 (Lemmy UI 통합)
```javascript
// 네비게이션 바에 BCH 결제 버튼 추가
const bchPaymentButton = () => {
    return (
        <a 
            href="https://payments.defadb.com"
            className="btn btn-outline-warning btn-sm ms-2"
            target="_blank"
            rel="noopener noreferrer"
        >
            <i className="bi bi-currency-bitcoin"></i>
            BCH 결제
        </a>
    );
};
```

### 2. 크레딧 표시
```javascript
// 사용자 크레딧 실시간 표시
const userCreditDisplay = (userId) => {
    const [credit, setCredit] = useState(0);
    
    useEffect(() => {
        fetch(`https://payments.defadb.com/api/user_credit/${userId}`)
            .then(res => res.json())
            .then(data => setCredit(data.total_credit));
    }, [userId]);
    
    return (
        <span className="badge bg-success">
            💰 {credit} BCH
        </span>
    );
};
```

### 3. QR 코드 컴포넌트
```html
<!-- QR 코드 표시 템플릿 -->
<div class="qr-code-container text-center">
    <div class="qr-code-wrapper">
        <img src="{{ qr_code_url }}" alt="BCH Payment QR Code" class="qr-code-image">
        <div class="qr-overlay">
            <i class="bi bi-qr-code"></i>
        </div>
    </div>
    <p class="qr-instructions">
        모바일 BCH 지갑으로 QR 코드를 스캔하세요
    </p>
</div>
```

## 🔒 보안 구현

### 1. API 키 인증
```python
from functools import wraps

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != app.config['LEMMY_API_KEY']:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated_function

@api_bp.route('/api/user_credit/<user_id>')
@require_api_key
def get_user_credit(user_id):
    # API 구현
    pass
```

### 2. CORS 설정
```python
from flask_cors import CORS

# Lemmy UI 도메인만 허용
CORS(app, origins=['https://defadb.com'])
```

### 3. 입력 검증
```python
from marshmallow import Schema, fields, validate

class InvoiceSchema(Schema):
    amount = fields.Float(required=True, validate=validate.Range(min=0.0001, max=1.0))
    user_id = fields.Integer(required=True, validate=validate.Range(min=1))
    description = fields.String(validate=validate.Length(max=200))

@payment_bp.route('/create_invoice', methods=['POST'])
def create_invoice():
    schema = InvoiceSchema()
    try:
        data = schema.load(request.json)
    except ValidationError as err:
        return jsonify({'errors': err.messages}), 400
    
    # 인보이스 생성 로직
    pass
```

## 📊 데이터베이스 스키마

### 인보이스 테이블
```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount DECIMAL(10, 8) NOT NULL,
    address VARCHAR(100) NOT NULL,
    user_id INTEGER NOT NULL,
    username VARCHAR(50),
    description TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    tx_hash VARCHAR(64),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    confirmed_at DATETIME,
    INDEX idx_user_id (user_id),
    INDEX idx_address (address),
    INDEX idx_status (status)
);
```

### 사용자 크레딧 테이블
```sql
CREATE TABLE user_credits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username VARCHAR(50) NOT NULL,
    amount DECIMAL(10, 8) NOT NULL,
    transaction_type VARCHAR(20) NOT NULL,
    invoice_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (invoice_id) REFERENCES invoices(id),
    INDEX idx_user_id (user_id),
    INDEX idx_username (username)
);
```

## 🧪 테스트

### 단위 테스트
```python
import unittest
from app import create_app, db

class PaymentTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(testing=True)
        self.client = self.app.test_client()
        
    def test_create_invoice(self):
        response = self.client.post('/create_invoice', json={
            'amount': 0.001,
            'user_id': 1,
            'description': 'Test payment'
        })
        self.assertEqual(response.status_code, 200)
        
    def test_api_authentication(self):
        response = self.client.get('/api/user_credit/1')
        self.assertEqual(response.status_code, 401)
        
        response = self.client.get('/api/user_credit/1', 
                                 headers={'X-API-Key': 'valid-key'})
        self.assertEqual(response.status_code, 200)
```

### 통합 테스트
```python
def test_payment_flow():
    # 1. 인보이스 생성
    invoice = create_test_invoice()
    
    # 2. 테스트넷에서 결제 시뮬레이션
    simulate_payment(invoice.address, invoice.amount)
    
    # 3. 결제 확인
    check_payment_status(invoice.id)
    
    # 4. 크레딧 확인
    credit = get_user_credit(invoice.user_id)
    assert credit >= invoice.amount
```

## 📈 성능 최적화

### 1. 데이터베이스 인덱스
```sql
-- 성능 향상을 위한 인덱스
CREATE INDEX idx_invoices_user_id ON invoices(user_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_created_at ON invoices(created_at);
CREATE INDEX idx_user_credits_user_id ON user_credits(user_id);
```

### 2. 캐싱 구현
```python
from flask_caching import Cache

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

@cache.memoize(timeout=300)  # 5분 캐시
def get_user_total_credit(user_id):
    return db.session.query(func.sum(UserCredit.amount))\
             .filter_by(user_id=user_id).scalar() or 0
```

### 3. 비동기 처리
```python
import asyncio
import aiohttp

async def check_blockchain_async(address):
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://blockchair.com/bitcoin-cash/address/{address}') as resp:
            return await resp.json()
```

## 🔄 배포 및 운영

### Docker 설정
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8081

CMD ["gunicorn", "--bind", "0.0.0.0:8081", "app:app"]
```

### Docker Compose 통합
```yaml
services:
  bitcoincash-service:
    build: ./bitcoincash_service
    ports:
      - "8081:8081"
    environment:
      - FLASK_ENV=production
      - ELECTRON_CASH_URL=http://electron-cash:7777
    volumes:
      - ./data:/app/data
    depends_on:
      - electron-cash
```

### 모니터링
```python
@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'database': check_database_connection(),
        'electron_cash': check_electron_cash_connection(),
        'timestamp': datetime.utcnow().isoformat()
    })
```

## 🚀 향후 개선 계획

### 단기 (1-2주)
1. **Rate Limiting 구현**: Flask-Limiter 도입
2. **구조화된 로깅**: structlog 적용
3. **캐싱 시스템**: Redis 연동

### 중기 (1-2개월)
1. **마이크로서비스 분리**: Payment 서비스 독립화
2. **API 버전 관리**: v1, v2 엔드포인트 분리
3. **성능 모니터링**: Prometheus + Grafana

### 장기 (3-6개월)
1. **다중 암호화폐 지원**: BTC, ETH 추가
2. **고가용성 구성**: 로드 밸런서 적용
3. **클라우드 배포**: Kubernetes 마이그레이션

---

**프로젝트 시작일**: 2025-07-01  
**현재 버전**: v2.0  
**마지막 업데이트**: 2025-09-07  
**운영 상태**: ✅ Production (defadb.com)  
**개발자**: defadb Team
