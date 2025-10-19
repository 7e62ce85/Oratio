# 🏗️ Lemmy 프로젝트 구조 - Rust는 어디에?

## 🎯 핵심 답변

**당신의 프로젝트에는 Rust 소스 코드가 없습니다!**

왜냐하면:
- ✅ **Lemmy Core (Rust)**: Docker 이미지로 사용
- ✅ **직접 수정한 부분**: UI (TypeScript/React) + Python (결제 서비스)
- ❌ **Rust 코드**: 직접 작성하지 않음

---

## 📦 프로젝트 구조 분석

### **현재 Docker 컨테이너 구성**

```
┌─────────────────────────────────────────────────────────────┐
│                    Oratio 프로젝트                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. oratio-lemmy-1        (Rust 백엔드)                     │
│     └─> Image: dessalines/lemmy:0.19.8                      │
│         ├─ Rust로 작성된 Lemmy 백엔드                       │
│         ├─ API 서버 (포트 8536)                             │
│         ├─ 데이터베이스 연동                                │
│         └─ 📦 미리 컴파일된 바이너리 (소스 없음!)           │
│                                                              │
│  2. oratio-lemmy-ui-1     (프론트엔드 - 당신이 수정함!)    │
│     └─> Image: lemmy-ui-custom:latest                       │
│         ├─ TypeScript/React                                 │
│         ├─ 당신이 커스터마이징한 UI                         │
│         ├─ BCH 결제 통합                                    │
│         └─ ✅ 소스: /home/user/Oratio/lemmy-ui-custom/      │
│                                                              │
│  3. bitcoincash-service   (결제 서비스 - 당신이 작성함!)   │
│     └─> Image: oratio-bitcoincash-service                   │
│         ├─ Python (Flask)                                   │
│         ├─ BCH 결제 처리                                    │
│         └─ ✅ 소스: /home/user/Oratio/oratio/               │
│                         bitcoincash_service/                │
│                                                              │
│  4. oratio-postgres-1     (데이터베이스)                    │
│  5. oratio-nginx-1        (웹 서버/프록시)                  │
│  6. electron-cash         (BCH 지갑)                        │
│  7. email-service         (이메일)                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔍 Rust는 어디에 있나?

### **1️⃣ Lemmy 백엔드 (Rust) - Docker 이미지**

```yaml
# docker-compose.yml
lemmy:
  image: dessalines/lemmy:0.19.8  # ← 이것이 Rust 백엔드!
  hostname: lemmy
  restart: always
  environment:
    - RUST_LOG=warn
  volumes:
    - ./lemmy.hjson:/config/config.hjson:Z
```

**특징:**
- 🦀 **Rust로 작성됨**: Lemmy 개발팀이 Rust로 개발
- 📦 **미리 컴파일됨**: Docker Hub에서 바이너리 다운로드
- ❌ **소스 코드 없음**: 당신의 프로젝트에는 Rust 소스가 없음
- ✅ **API 제공**: REST API를 통해 UI와 통신

**Rust 백엔드가 하는 일:**
```
- 사용자 인증 및 권한 관리
- 게시물/댓글 CRUD
- 투표 시스템
- 커뮤니티 관리
- 연합(Federation) 기능
- 데이터베이스 연동 (PostgreSQL)
```

---

### **2️⃣ 당신이 수정한 부분 (Rust 아님!)**

```
/home/user/Oratio/
├── lemmy-ui-custom/           ← TypeScript/React (프론트엔드)
│   ├── src/
│   │   ├── shared/
│   │   │   ├── components/   ← UI 컴포넌트
│   │   │   └── utils/
│   │   │       └── proof-of-work.ts  ← 방금 추가한 PoW
│   │   └── client/
│   └── package.json
│
└── oratio/
    ├── bitcoincash_service/   ← Python (결제 서비스)
    │   ├── app.py
    │   ├── routes/
    │   ├── services/
    │   └── models.py
    │
    └── docker-compose.yml
```

---

## 🏛️ 전체 아키텍처

```
┌───────────────────────────────────────────────────────────┐
│                      사용자 브라우저                        │
└───────────────────────────────────────────────────────────┘
                            │
                            ↓
┌───────────────────────────────────────────────────────────┐
│                    Nginx (프록시)                          │
│                    포트 80/443                             │
└───────────────────────────────────────────────────────────┘
                            │
            ┌───────────────┼───────────────┐
            ↓               ↓               ↓
┌──────────────────┐ ┌──────────────┐ ┌────────────────┐
│   Lemmy UI       │ │ Lemmy Backend│ │ BCH Payment    │
│  (TypeScript)    │ │   (Rust)     │ │   (Python)     │
│                  │ │              │ │                │
│  ✅ 당신이 수정  │ │  📦 Docker   │ │  ✅ 당신이 작성│
│                  │ │    Image     │ │                │
│  - signup.tsx    │ │              │ │  - app.py      │
│  - pow.ts        │ │  - API 제공  │ │  - routes/     │
│  - BCH 통합      │ │  - DB 연동   │ │  - services/   │
└──────────────────┘ └──────────────┘ └────────────────┘
                            │
                            ↓
                   ┌────────────────┐
                   │   PostgreSQL   │
                   │  (데이터베이스) │
                   └────────────────┘
```

---

## 📝 Rust 백엔드 소스는 어디에?

### **Lemmy 공식 GitHub 저장소:**

```
https://github.com/LemmyNet/lemmy
│
├── crates/           ← Rust 소스 코드
│   ├── api/          ← API 엔드포인트
│   ├── db_schema/    ← 데이터베이스 스키마
│   ├── db_views/     ← 데이터베이스 뷰
│   ├── utils/        ← 유틸리티
│   └── ...
│
├── Cargo.toml        ← Rust 프로젝트 설정
└── Cargo.lock
```

**당신의 프로젝트에는 이것들이 없습니다!**  
왜냐하면 Docker 이미지를 사용하기 때문입니다.

---

## 🛠️ PoW를 Rust 백엔드에 추가하려면?

### **방법 1: Lemmy 포크 (복잡함) ❌**

```bash
# 1. Lemmy 저장소 클론
git clone https://github.com/LemmyNet/lemmy.git

# 2. Rust 코드 수정
cd lemmy/crates/api/src/user/
# register.rs 파일 수정

# 3. Rust 컴파일
cargo build --release

# 4. Docker 이미지 빌드
docker build -t custom-lemmy:latest .

# 5. docker-compose.yml 수정
# image: dessalines/lemmy:0.19.8 
# → image: custom-lemmy:latest
```

**문제점:**
- 🔥 Rust 개발 환경 필요
- 🔥 컴파일 시간 오래 걸림
- 🔥 Lemmy 업데이트 시 충돌 가능
- 🔥 유지보수 어려움

---

### **방법 2: 프록시 레이어 (추천!) ✅**

Rust 백엔드를 수정하지 않고, 중간에 검증 레이어 추가:

```
사용자 → Nginx → [PoW 검증 서비스] → Lemmy Rust 백엔드
                      (Python/Node.js)
```

**장점:**
- ✅ Rust 수정 불필요
- ✅ 빠른 개발
- ✅ Lemmy 업데이트 무관
- ✅ 쉬운 유지보수

**구현 예:**

```python
# oratio/pow_validator_service/app.py
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/api/v3/user/register', methods=['POST'])
def register_with_pow():
    data = request.json
    
    # 1. PoW 검증
    if not verify_pow(
        data.get('pow_challenge'),
        data.get('pow_nonce'),
        data.get('pow_hash')
    ):
        return jsonify({'error': 'Invalid PoW'}), 400
    
    # 2. PoW 필드 제거 (Lemmy는 모르는 필드)
    del data['pow_challenge']
    del data['pow_nonce']
    del data['pow_hash']
    
    # 3. Lemmy 백엔드로 전달
    response = requests.post(
        'http://lemmy:8536/api/v3/user/register',
        json=data
    )
    
    return response.json(), response.status_code
```

**Nginx 설정:**
```nginx
# 회원가입 요청만 PoW 검증 서비스로
location /api/v3/user/register {
    proxy_pass http://pow-validator:5000;
}

# 나머지는 Lemmy로
location /api/ {
    proxy_pass http://lemmy:8536;
}
```

---

## 📊 현재 프로젝트 파일 분석

### **Rust 관련 파일:**

```bash
$ find /home/user/Oratio -name "*.rs"
/home/user/Oratio/docs/features/pow_backend_example.rs  ← 예제만!
```

**결과:** 실제 Rust 소스 코드 없음! 예제 파일만 있음.

### **실제로 작업한 파일:**

```
TypeScript/JavaScript:
  - lemmy-ui-custom/src/**/*.tsx
  - lemmy-ui-custom/src/**/*.ts
  
Python:
  - oratio/bitcoincash_service/**/*.py
  - oratio/email-service/**/*.py
  
Configuration:
  - oratio/docker-compose.yml
  - oratio/nginx*.conf
  - oratio/lemmy.hjson
```

---

## 🎯 결론

### **Rust는 어디에?**

```
✅ Lemmy 백엔드 = Rust (Docker 이미지로 실행)
   └─> dessalines/lemmy:0.19.8
   └─> 소스 코드: GitHub에 있음 (당신 프로젝트에는 없음)
   └─> 역할: API 서버, 비즈니스 로직, DB 연동

❌ 당신의 프로젝트 = Rust 없음
   └─> TypeScript: UI 커스터마이징
   └─> Python: BCH 결제 서비스
   └─> Configuration: Docker, Nginx 설정
```

### **PoW 백엔드 검증 추가 방법:**

| 방법 | 난이도 | 추천도 |
|------|--------|--------|
| **Lemmy Rust 포크** | 🔥🔥🔥🔥 높음 | ⭐ 비추천 |
| **Python 프록시 레이어** | ⭐ 쉬움 | ⭐⭐⭐⭐⭐ 강력 추천 |
| **Node.js 미들웨어** | ⭐⭐ 보통 | ⭐⭐⭐⭐ 추천 |

---

### **추천: Python 프록시 서비스 추가**

```
/home/user/Oratio/oratio/
└── pow_validator_service/    ← 새로 추가
    ├── app.py                 ← PoW 검증 로직
    ├── Dockerfile
    └── requirements.txt
```

이렇게 하면 Rust 수정 없이 PoW 검증 가능합니다! 🚀

---

**작성일**: 2025-10-13  
**요약**: 당신의 프로젝트에는 Rust 소스가 없습니다. Lemmy 백엔드는 Docker 이미지로 사용하고, UI와 결제 서비스만 직접 개발했습니다.
