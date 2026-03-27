# Oratio — Lemmy 포럼 + Bitcoin Cash 결제 플랫폼

**Lemmy** 커뮤니티 포럼에 **Bitcoin Cash (BCH) 결제**, 콘텐츠 모더레이션, 멤버십 시스템, 광고 플랫폼을 통합한 프로젝트. Docker Compose 11개 서비스로 운영.

> **English version**: [README.md](README.md)

---

## 목차

- [프로젝트 구성 방식](#프로젝트-구성-방식)
- [시스템 아키텍처](#시스템-아키텍처)
- [설치 가이드 (Linux)](#설치-가이드-linux)
- [설치 가이드 (Windows — WSL2)](#설치-가이드-windows--wsl2)
- [설치 후 체크리스트](#설치-후-체크리스트)
- [API 레퍼런스](#api-레퍼런스)
- [데이터베이스 구조](#데이터베이스-구조)
- [환경변수](#환경변수)
- [문제 해결](#문제-해결)
- [백업 및 유지보수](#백업-및-유지보수)
- [기여하기](#기여하기)
- [라이선스](#라이선스)

---

## 프로젝트 구성 방식

이 프로젝트는 Lemmy를 재작성한 게 **아니다**. 공식 Lemmy 백엔드를 그대로 사용하고, 그 위에 커스텀 서비스를 추가한 구조:

| 컴포넌트 | 출처 | 수정 여부 | 언어 |
|----------|------|-----------|------|
| **lemmy** (백엔드) | `dessalines/lemmy:0.19.8` 공식 이미지 | ❌ 수정 없음 | Rust |
| **lemmy-ui** (프론트엔드) | Lemmy UI 오픈소스 fork | ✅ BCH 버튼, 크레딧 표시, PoW 캡차 추가 | TypeScript/Inferno.js |
| **bitcoincash-service** | 자체 개발 | ✅ 100% 커스텀 | Python/Flask |
| **pow-validator** | 자체 개발 | ✅ 100% 커스텀 | Python |
| **email-service** | 자체 개발 | ✅ 100% 커스텀 | Python |
| **electron-cash** | Electron Cash 오픈소스 + 커스텀 Dockerfile | ⚠️ 래핑 | Python |
| **nginx, postgres, pictrs, postfix, certbot** | 공식 이미지 | ❌ 설정만 | — |

### 저장소 구조

```
Oratio/                              ← 레포 루트
├── lemmy-ui-custom/                 ← 📦 커스텀 프론트엔드 (Docker 이미지로 빌드됨)
│   ├── src/                         ←   Inferno.js 컴포넌트, BCH UI 통합
│   ├── Dockerfile                   ←   멀티 스테이지 빌드
│   └── package.json
├── oratio/                          ← 📦 인프라 + 자체 백엔드 서비스 전부
│   ├── docker-compose.yml           ←   11개 컨테이너 전부 정의 (여기가 운영 루트)
│   ├── .env                         ←   시크릿 (refresh_passwords.sh로 생성)
│   ├── lemmy.hjson                  ←   Lemmy 코어 설정
│   ├── nginx_production.conf        ←   Nginx 리버스 프록시 설정
│   ├── bitcoincash_service/         ←   Flask 결제/모더레이션/멤버십/광고 API
│   ├── pow_validator_service/       ←   PoW 봇 방지 서비스
│   ├── email-service/               ←   Resend API 이메일 프록시
│   ├── electron_cash/               ←   BCH 지갑 Docker 빌드
│   ├── data/                        ←   영구 데이터 (지갑, certbot, 결제 DB)
│   └── volumes/                     ←   Docker 볼륨 마운트 (postgres, pictrs)
├── docs/                            ← 추가 문서
├── files/                           ← nginx가 서빙하는 정적 파일 (PDF 등)
├── README.md                        ← 영어 버전
└── README_KOR.md                    ← 이 파일
```

**핵심 관계**: `oratio/docker-compose.yml`이 `../lemmy-ui-custom/`에서 `lemmy-ui` 이미지를 빌드한다. 모든 `docker compose` 명령은 `oratio/`에서 실행.

---

## 시스템 아키텍처

11개 Docker 서비스로 구성:

```
                        ┌──────────────────────┐
                        │   certbot            │
                        │   SSL 자동 갱신       │
                        └──────────────────────┘
                                   │ (공유 볼륨: letsencrypt)
                                   ▼
┌──────────────────────┐   ┌──────────────────────┐
│   nginx (proxy)      │──▶│   lemmy-ui           │
│   Port: 80, 443      │   │   커스텀 프론트엔드    │
│   SSL 종료           │   │   Port: 1234         │
└──────────────────────┘   └──────────────────────┘
    │       │       │                  │
    │       │       ▼                  ▼
    │       │  ┌──────────────────────┐   ┌──────────────────────┐
    │       │  │  pow-validator       │   │  bitcoincash-service │
    │       │  │  봇 방지             │   │  Flask API           │
    │       │  │  Port: 5001         │   │  Port: 8081          │
    │       │  └──────────────────────┘   └──────────────────────┘
    │       │             │                        │
    │       ▼             ▼                        ▼
    │  ┌──────────────────────┐   ┌──────────────────────┐
    │  │   lemmy              │   │   electron-cash      │
    │  │   공식 백엔드         │   │   BCH 지갑 (RPC)     │
    │  │   Port: 8536         │   │   Port: 7777         │
    │  └──────────────────────┘   └──────────────────────┘
    │             │
    ▼             ▼
┌──────────────────────┐   ┌──────────────────────┐
│   postgres           │   │   pictrs             │
│   포럼 데이터베이스    │   │   이미지 호스팅       │
│   Port: 5432         │   │   Port: 8080         │
└──────────────────────┘   └──────────────────────┘

┌──────────────────────┐   ┌──────────────────────┐
│   email-service      │   │   postfix            │
│   Resend API 프록시   │   │   내부 SMTP          │
│   Port: 1025, 8025   │   │   릴레이              │
└──────────────────────┘   └──────────────────────┘
```

### 서비스 요약

| # | 서비스 | 역할 | 포트 |
|---|--------|------|------|
| 1 | **proxy** (nginx) | 리버스 프록시, SSL, 라우팅 | 80, 443 |
| 2 | **certbot** | Let's Encrypt 자동 갱신 | — |
| 3 | **lemmy** | 포럼 백엔드 (공식 Rust 이미지) | 8536 |
| 4 | **lemmy-ui** | BCH 통합 커스텀 프론트엔드 | 1234 |
| 5 | **pictrs** | 이미지 호스팅 및 처리 | 8080 |
| 6 | **postgres** | PostgreSQL 포럼 데이터 | 5432 |
| 7 | **postfix** | 내부 메일 릴레이 | — |
| 8 | **pow-validator** | PoW 봇 방지 (회원가입 + 게시글) | 5001 |
| 9 | **bitcoincash-service** | 결제, 모더레이션, 멤버십, 광고 API | 8081 |
| 10 | **email-service** | Resend API 프록시 (SMTP 포트 차단 우회) | 1025, 8025 |
| 11 | **electron-cash** | BCH HD 지갑 + RPC 인터페이스 | 7777 |

### 요청 흐름
1. **브라우저** → nginx (SSL) → lemmy-ui (프론트엔드)
2. **회원가입 / 새 게시글** → nginx → pow-validator (PoW 검증) → lemmy (백엔드)
3. **BCH 결제** → nginx `/payments/` → bitcoincash-service → electron-cash → 블록체인
4. **콘텐츠 신고** → nginx `/api/cp/` → bitcoincash-service (CP 모더레이션)
5. **멤버십 / 광고** → nginx `/api/membership/` 또는 `/api/ads/` → bitcoincash-service
6. **이메일 인증** → lemmy → email-service (Resend API) → 사용자 수신함

---

## 설치 가이드 (Linux)

> 모든 명령은 `oratio/` (docker-compose.yml이 있는 곳)에서 실행. 별도 언급이 없는 한.

### 1. 사전 요구사항

**서버 사양:**
- OS: Ubuntu 22.04+ 또는 Debian 12+ (Docker 지원하는 아무 Linux)
- RAM: 최소 2GB (4GB+ 권장)
- 디스크: 20GB+ SSD
- 포트 80, 443 개방
- 등록된 도메인 + DNS가 이 서버를 가리켜야 함

**Docker 설치:**
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# 로그아웃 후 재로그인해야 그룹 변경 적용됨

# Docker Compose v2 확인
docker compose version
```

**DNS 레코드** (도메인 등록기관에서 설정):

| 레코드 | 타입 | 값 |
|--------|------|-----|
| `your-domain.com` | A | `<서버 IP>` |
| `www.your-domain.com` | A | `<서버 IP>` |

> 결제 서비스는 `https://your-domain.com/payments/` (서브경로)로 제공됨 — 별도 서브도메인 필요 없음.

### 2. 클론 & 디렉토리 이동

```bash
git clone https://github.com/7e62ce85/Oratio.git
cd Oratio/oratio
```

### 3. 시크릿 & 환경 파일 생성

두 가지 방법. **방법 A 권장.**

#### 방법 A — 자동 (권장)

```bash
cp refresh_passwords.sh.example refresh_passwords.sh
nano refresh_passwords.sh
```

맨 위의 `[CHANGE_ME]` 섹션 수정:
```bash
DOMAIN="your-domain.com"
ADMIN_EMAIL="admin@your-domain.com"
RESEND_API_KEY_VALUE=""                              # https://resend.com 에서 발급 (선택)
PAYOUT_WALLET_ADDRESS="bitcoincash:qYourAddress"     # BCH 수금 주소
SMTP_FROM="noreply@your-domain.com"
```

실행:
```bash
chmod +x refresh_passwords.sh
./refresh_passwords.sh
```

이 스크립트가 하는 일:
- PostgreSQL, Electron Cash, API 키, 관리자 비밀번호, Flask 시크릿을 자동 생성
- `oratio/.env`와 `lemmy-ui-custom/.env`에 기록
- `lemmy.hjson`의 비밀번호도 동기화
- 컨테이너를 새 시크릿으로 재생성

#### 방법 B — 수동

```bash
# 1. .env 생성
cp .env.example .env
nano .env                    # REQUIRED 항목 전부 채우기

# 2. lemmy.hjson 생성
cp lemmy.hjson.example lemmy.hjson
nano lemmy.hjson
#   - password: .env의 POSTGRES_PASSWORD와 일치해야 함
#   - hostname: 본인 도메인
#   - pictrs api_key: docker-compose.yml의 PICTRS__SERVER__API_KEY와 일치
#   - email smtp_from_address: 발신 주소

# 3. lemmy-ui-custom에도 .env 공유
cp .env ../lemmy-ui-custom/.env
```

### 4. SSL 부트스트랩 (Let's Encrypt)

**문제**: Nginx가 시작하려면 인증서가 필요한데, Certbot은 Nginx가 떠 있어야 ACME 챌린지를 처리할 수 있음.

**해결**: 포함된 부트스트랩 스크립트 사용:

```bash
nano init-letsencrypt-simple.sh
#   - domains=(your-domain.com) 으로 수정
#   - email="admin@your-domain.com" 으로 수정

chmod +x init-letsencrypt-simple.sh
./init-letsencrypt-simple.sh
```

이 스크립트의 동작:
1. 권장 TLS 파라미터 다운로드
2. 임시 자체서명(더미) 인증서 생성
3. 더미 인증서로 Nginx 시작
4. 더미 인증서 삭제
5. Let's Encrypt 실제 인증서 요청 (webroot 방식)
6. 실제 인증서로 Nginx 리로드

> **SSL 없이 먼저 테스트하고 싶다면?** `nginx_temp_nossl.conf`를 `nginx_internal.conf`로 복사하고, 스택을 올려서 HTTP로 확인한 뒤, DNS 준비되면 SSL 부트스트랩 실행.

### 4-1. 추가 `.example` 파일

일부 파일에는 서버별 고유 값(IP 주소, 도메인)이 포함되어 있어 **git에서 추적하지 않습니다**.
`.example` 버전을 복사한 뒤 본인 환경에 맞게 수정하세요:

```bash
# Postfix SMTP 설정 스크립트 (선택 — 이메일 자체 호스팅 시에만 필요)
cp setup_postfix_check.sh.example setup_postfix_check.sh
nano setup_postfix_check.sh        # SERVER_IP, DOMAIN, MAIL_HOSTNAME 수정

# Postfix DNS 가이드 (참고 문서)
cp setup_postfix_dns_guide.md.example setup_postfix_dns_guide.md

# SSL 설정 참고 문서
cp ../docs/SSL_LETSENCRYPT_SETUP.md.example ../docs/SSL_LETSENCRYPT_SETUP.md
```

> 이 파일들은 `.gitignore`에 등록되어 있어 실제 IP/도메인이 리포지토리에 푸시되지 않습니다.

### 5. 볼륨 권한 설정

```bash
# pictrs는 UID 991로 실행됨
mkdir -p volumes/pictrs
sudo chown -R 991:991 volumes/pictrs

# 지갑 데이터
mkdir -p data/electron_cash

# 결제 데이터베이스
mkdir -p data/bitcoincash

# Certbot (init 스크립트가 보통 만들지만, 확실하게)
mkdir -p data/certbot/conf data/certbot/www
```

### 6. 빌드 & 실행

```bash
# 커스텀 이미지 빌드 (lemmy-ui, bitcoincash-service, pow-validator, email-service, electron-cash)
docker compose build

# 11개 서비스 전부 시작
docker compose up -d

# 로그 확인
docker compose logs -f --tail=50
```

> **`.env`에서 lemmy-ui 빌드 타임에 박히는 값** (`LEMMY_API_KEY`, `LEMMY_BCH_*`)을 변경했다면 반드시 리빌드:
> ```bash
> docker compose build --no-cache lemmy-ui
> docker compose up -d
> ```

### 7. 확인

```bash
# 모든 컨테이너가 "Up"이어야 함
docker compose ps

# HTTPS 테스트
curl -I https://your-domain.com

# 결제 서비스 헬스체크
curl https://your-domain.com/payments/health

# 기대 응답:
# {"status": "ok", "services": {"database": "healthy", "electron_cash": "connected"}}
```

---

## 설치 가이드 (Windows — WSL2)

**개발 및 테스트 전용.** 프로덕션 배포는 Linux 사용.

### 1. WSL2 활성화

```powershell
# PowerShell을 관리자 권한으로 실행
wsl --install -d Ubuntu-22.04
```

재부팅 필요시 재부팅. Ubuntu 처음 실행 시 사용자명/비밀번호 설정.

### 2. Docker Desktop 설치

1. https://www.docker.com/products/docker-desktop/ 에서 다운로드
2. 설치 시 **"Use WSL 2 based engine"** 활성화
3. Docker Desktop → Settings → Resources → WSL Integration → Ubuntu 활성화
4. Docker Desktop 재시작

### 3. WSL2에서 계속 진행

Ubuntu 터미널 열기 (시작 메뉴 또는 PowerShell에서 `wsl`):

```bash
# Docker 동작 확인
docker compose version

# 클론 후 Linux 가이드와 동일
git clone https://github.com/7e62ce85/Oratio.git
cd Oratio/oratio
```

이후 **[Linux 가이드 3~7단계](#3-시크릿--환경-파일-생성)** 를 그대로 따라가면 됨.

### WSL2 참고사항
- 성능은 레포가 **WSL2 파일시스템 안** (`~/Oratio`)에 있을 때 가장 좋음. `/mnt/c/`에 두면 느림.
- Windows의 `localhost`가 WSL2로 매핑되므로 `https://localhost`로 접근 가능.
- 로컬 SSL 테스트는 SSL 건너뛰기 (`nginx_temp_nossl.conf` 사용) 또는 자체서명 인증서 권장.

> **macOS**: Docker Desktop for Mac에서도 동작함. Docker Desktop 설치 후 Linux 가이드 3~7단계 따라가면 됨.

---

## 설치 후 체크리스트

모든 컨테이너가 실행된 후:

- [ ] `docker compose ps` — 11개 서비스 "Up" 확인
- [ ] `https://your-domain.com` — Lemmy UI 로드됨
- [ ] 새 계정 등록 가능 (PoW 캡차 나타남)
- [ ] 이메일 인증 도착 (`RESEND_API_KEY` 설정했다면)
- [ ] `https://your-domain.com/payments/` — 결제 페이지 로드됨
- [ ] `https://your-domain.com/payments/health` — `{"status": "ok"}` 반환
- [ ] 유저 드롭다운에 BCH 크레딧 잔액 표시됨
- [ ] `.env`의 자격증명으로 관리자 로그인 가능

---

## API 레퍼런스

결제 서비스(`bitcoincash-service`, 포트 8081)의 엔드포인트. 메인 도메인에서 `/payments/`, `/api/cp/`, `/api/membership/` 등으로 프록시됨.

### 인보이스 & 결제

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| GET | `/generate_invoice` | — | 인보이스 생성 (파라미터: `amount`, `user_id`) |
| GET | `/invoice/<invoice_id>` | — | 인보이스 상세 (QR코드, 상태) |
| GET | `/check_payment/<invoice_id>` | — | 결제 상태 확인 |
| GET | `/payment_success/<invoice_id>` | — | 결제 성공 페이지 |

### 사용자 크레딧 API

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| GET | `/api/user_credit/<user_id>` | `X-API-Key` | 숫자 ID로 크레딧 조회 |
| GET | `/api/user_credit/<username>` | `X-API-Key` | 유저명으로 크레딧 조회 |
| GET | `/api/transactions/<user_id>` | `X-API-Key` | ID로 거래 내역 |
| GET | `/api/transactions/<username>` | `X-API-Key` | 유저명으로 거래 내역 |
| GET | `/api/has_payment/<user_id>` | `X-API-Key` | 결제 이력 확인 |
| GET | `/api/has_payment/<username>` | `X-API-Key` | 결제 이력 확인 |
| GET | `/health` | — | 헬스 체크 |

### 멤버십 API (`/api/membership/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/membership/price` | 현재 멤버십 가격 |
| GET | `/api/membership/status/<username>` | 멤버십 상태 |
| GET | `/api/membership/check/<username>` | 멤버십 활성 여부 |
| POST | `/api/membership/purchase` | 멤버십 구매 |
| GET | `/api/membership/transactions/<username>` | 멤버십 거래 내역 |
| POST | `/api/membership/check-expiry` | 만료 체크 트리거 |

### CP (콘텐츠 보호) 모더레이션 API (`/api/cp/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/cp/permissions/by-username/<username>` | 유저 권한 조회 |
| GET | `/api/cp/permissions/<user_id>` | ID로 권한 조회 |
| GET | `/api/cp/permissions/revoked` | 권한 취소된 유저 목록 |
| GET | `/api/cp/permissions/can-report/<user_id>` | 신고 가능 여부 |
| POST | `/api/cp/permissions/initialize` | 권한 초기화 |
| GET | `/api/cp/user-reports/<username>` | 유저가 한 신고 목록 |
| POST | `/api/cp/report` | 신고 제출 |
| GET | `/api/cp/report/<report_id>` | 신고 상세 |
| GET | `/api/cp/reports/pending` | 대기 중 신고 |
| GET | `/api/cp/reported-content-ids` | 숨겨진 콘텐츠 ID |
| GET | `/api/cp/report/<id>/check-existing` | 중복 확인 |
| POST | `/api/cp/report/<id>/review` | 신고 심사 |
| POST | `/api/cp/appeal` | 이의 제기 |
| GET | `/api/cp/appeals/pending` | 대기 중 이의 |
| GET | `/api/cp/appeal/<appeal_id>` | 이의 상세 |
| POST | `/api/cp/appeals/<id>/review` | 이의 심사 |
| POST | `/api/cp/admin/user/<id>/ban` | 유저 밴 (관리자) |
| POST | `/api/cp/admin/user/<id>/revoke-report` | 신고 권한 박탈 |
| POST | `/api/cp/admin/user/<id>/restore` | 권한 복구 |
| GET | `/api/cp/notifications/<person_id>` | 알림 조회 |
| POST | `/api/cp/notifications/<id>/read` | 읽음 표시 |
| POST | `/api/cp/background/run-tasks` | 백그라운드 태스크 |
| GET | `/api/cp/health` | CP 시스템 헬스 |
| GET | `/api/cp/check-post-access/<post_id>` | 게시글 숨김 여부 (nginx auth_request) |

### 업로드 쿼터 API (`/api/upload/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/upload/quota/<user>` | 남은 업로드 쿼터 |
| POST | `/api/upload/validate` | 업로드 전 검증 |
| POST | `/api/upload/record` | 업로드 기록 |
| GET | `/api/upload/history/<user>` | 업로드 이력 |
| GET | `/api/upload/pricing` | 티어 가격 |
| POST | `/api/upload/reset-quota/<user_id>` | 쿼터 리셋 (관리자) |

### 광고 API (`/api/ads/`)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/api/ads/display` | 표시할 광고 |
| POST | `/api/ads/click` | 클릭 기록 |
| POST | `/api/ads/confirm` | 표시 확인 |
| GET | `/api/ads/stats/sections` | 섹션 통계 |
| GET | `/api/ads/credits/<username>` | 광고 크레딧 |
| POST | `/api/ads/credits/add` | 크레딧 추가 |
| POST | `/api/ads/campaigns` | 캠페인 생성 |
| GET | `/api/ads/campaigns/user/<username>` | 유저 캠페인 |
| GET | `/api/ads/campaigns/<id>` | 캠페인 상세 |
| GET | `/api/ads/admin/pending` | 대기 캠페인 (관리자) |
| GET | `/api/ads/admin/active` | 활성 캠페인 (관리자) |
| POST | `/api/ads/admin/approve/<id>` | 캠페인 승인 |
| POST | `/api/ads/admin/reject/<id>` | 캠페인 거부 |
| GET | `/api/ads/total-budget` | 총 예산 |
| GET | `/api/ads/health` | 광고 시스템 헬스 |
| GET | `/api/ads/credits/price` | 크레딧 가격 |
| POST | `/api/ads/credits/invoice` | 크레딧 인보이스 |
| GET | `/api/ads/credits/check/<invoice_id>` | 크레딧 결제 확인 |
| POST | `/api/ads/credits/purchase` | 크레딧 구매 |
| GET | `/api/ads/credits/balance/<username>` | 크레딧 잔액 |

### 정적 페이지

| GET | `/` | 결제 서비스 메인 페이지 |
| GET | `/help` | BCH 안내 페이지 |

---

## 데이터베이스 구조

### PostgreSQL (Lemmy — 공식 Lemmy 백엔드가 관리)

표준 Lemmy 스키마: users, posts, comments, communities 등. **수정 없음.**

### SQLite (결제 서비스 — `data/bitcoincash/payments.db`)

13개 테이블, 첫 시작 시 자동 생성:

| 테이블 | 용도 |
|--------|------|
| `invoices` | 결제 인보이스 (id, 주소, 금액, 상태, tx_hash, 확인 수) |
| `addresses` | 생성된 BCH 주소 |
| `user_credits` | 사용자 크레딧 잔액 |
| `transactions` | 모든 거래 기록 (입금, 출금) |
| `user_memberships` | 연간 멤버십 기록 (유저, 만료일, 결제액) |
| `membership_transactions` | 멤버십 BCH 이체 기록 |
| `user_cp_permissions` | 유저 모더레이션 권한 (신고/심사 가능, 밴 상태) |
| `cp_reports` | 콘텐츠 신고 (유형, content_id, 신고자, 상태, 에스컬레이션) |
| `cp_reviews` | 신고 심사 결정 |
| `cp_appeals` | 유저 이의 제기 |
| `cp_notifications` | 모더레이션 알림 |
| `cp_audit_log` | 모든 모더레이션 액션의 감사 추적 |
| `moderator_cp_assignments` | 모더레이터↔커뮤니티 CP 심사 배정 |

---

## 환경변수

전체 목록은 [`oratio/.env.example`](oratio/.env.example) 참고.

### 필수 변수

| 변수 | 설명 |
|------|------|
| `POSTGRES_PASSWORD` | PostgreSQL 비밀번호 (`lemmy.hjson`과 일치해야 함) |
| `ELECTRON_CASH_PASSWORD` | Electron Cash RPC 비밀번호 |
| `LEMMY_API_KEY` | UI ↔ 결제 서비스 공유 시크릿 |
| `LEMMY_ADMIN_USER` | Lemmy 관리자 유저명 |
| `LEMMY_ADMIN_PASS` | Lemmy 관리자 비밀번호 |
| `PAYOUT_WALLET` | BCH 수금 지갑 주소 |
| `FLASK_SECRET_KEY` | Flask 세션 시크릿 |
| `DOMAIN` | 도메인 (예: `oratio.space`) |

### 선택 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `RESEND_API_KEY` | — | Resend.com API 키 (이메일 인증용) |
| `SMTP_FROM_ADDRESS` | — | 이메일 발신 주소 |
| `ADMIN_EMAIL` | — | Let's Encrypt 및 알림용 관리자 이메일 |
| `MOCK_MODE` | `false` | `true` = 테스트용 가짜 결제 |
| `TESTNET` | `false` | `true` = BCH 테스트넷 사용 |
| `MIN_CONFIRMATIONS` | `1` | 필요 BCH 확인 수 |

---

## 문제 해결

### 흔한 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| UI에서 BCH "undefined" | 빌드 시 인수 미전달 | `docker compose build --no-cache lemmy-ui && docker compose up -d` |
| 드롭다운에 크레딧 안 보임 | API 키 불일치 | `.env`와 컨테이너 내 `LEMMY_API_KEY` 확인: `docker compose exec lemmy-ui printenv \| grep API_KEY` |
| Electron Cash 접속 불가 | 비밀번호 틀림 또는 미시작 | `docker compose logs electron-cash` 및 `ELECTRON_CASH_PASSWORD` 확인 |
| SSL 오류 | 인증서 미발급 | `./init-letsencrypt-simple.sh` 실행 |
| pictrs 크래시 | 볼륨 권한 문제 | `sudo chown -R 991:991 volumes/pictrs` |
| SQLite 잠금 | 동시 접근 | WAL + 30초 타임아웃 사용 중; 지속되면 `bitcoincash-service` 재시작 |
| 이메일 미수신 | API 키 없음 | `.env`에 `RESEND_API_KEY` 설정 후 `email-service` 재시작 |
| `lemmy.hjson` 비밀번호 불일치 | `.env`와 hjson 비동기 | `refresh_passwords.sh` 사용 또는 수동 동기화 |

### 진단 명령어

```bash
cd oratio

# 서비스 상태
docker compose ps

# 로그 (최근 200줄)
docker compose logs --tail=200 bitcoincash-service
docker compose logs --tail=200 lemmy-ui
docker compose logs --tail=200 lemmy
docker compose logs --tail=200 electron-cash

# 실행 중 컨테이너의 환경변수 확인
docker compose exec lemmy-ui printenv | grep -i BCH
docker compose exec bitcoincash-service printenv | grep -i ELECTRON

# 결제 API 직접 테스트
curl -H "X-API-Key: YOUR_KEY" http://localhost:8081/api/user_credit/1

# 단일 서비스 재시작
docker compose restart bitcoincash-service

# 전체 재배포
docker compose down && docker compose build && docker compose up -d
```

### 로그 위치

| 로그 | 위치 |
|------|------|
| 전체 서비스 | `docker compose logs <서비스명>` |
| BCH 결제 앱 | 컨테이너 내 `/app/bch_payment.log` |
| 기타 | `oratio/logs/` |
| 브라우저 | 개발자 도구 → 콘솔 |

---

## 백업 및 유지보수

### 백업 대상

| 데이터 | 호스트 경로 |
|--------|-------------|
| Electron Cash 지갑 | `oratio/data/electron_cash/wallets/` |
| 지갑 시드 | `oratio/data/electron_cash/seed.txt` |
| 결제 데이터베이스 | `oratio/data/bitcoincash/payments.db` |
| PostgreSQL | `oratio/volumes/postgres/` |
| Pictrs 이미지 | `oratio/volumes/pictrs/` |
| Let's Encrypt 인증서 | `oratio/data/certbot/` |
| 시크릿 | `oratio/.env` |

### 자동 관리 항목

- **거래 모니터링**: `bitcoincash-service` 내 백그라운드 스레드 (외부 cron 불필요)
- **SSL 갱신**: `certbot` 컨테이너가 12시간 주기로 갱신 루프 실행
- **SQLite WAL 체크포인트**: 자동 발생; 대량 삭제 후 수동 `VACUUM` 권장

---

## 기여하기

```bash
git clone https://github.com/7e62ce85/Oratio.git
cd Oratio/oratio
cp refresh_passwords.sh.example refresh_passwords.sh
nano refresh_passwords.sh    # [CHANGE_ME] 섹션 수정
chmod +x refresh_passwords.sh && ./refresh_passwords.sh
docker compose build && docker compose up -d
```

이슈는 [GitHub Issues](https://github.com/7e62ce85/Oratio/issues)에 다음 정보와 함께 등록:
- OS, 브라우저 정보
- 재현 절차
- 기대 결과 vs 실제 결과
- 관련 로그 (시크릿 제거)

---

## 라이선스

**AGPL-3.0** — [LICENSE](LICENSE) 참고

| 컴포넌트 | 라이선스 |
|----------|----------|
| Lemmy | AGPL-3.0 |
| Electron Cash | MIT |
| Flask | BSD |
| PostgreSQL | PostgreSQL License |
| Nginx | 2-clause BSD |

---

> 📋 **언어 버전**: [English](README.md) · [한국어](README_KOR.md)
