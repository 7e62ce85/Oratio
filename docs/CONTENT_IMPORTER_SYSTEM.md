# Content Importer System (자동 콘텐츠 수집 봇)

> **작성일**: 2026-03-30 | **최종 수정**: 2026-03-31 (댓글 임포트 + YouTube Trending API)
> **서비스명**: `content-importer` (Docker)
> **목적**: 빈 포럼 문제 해결 — 외부 인기 게시물을 자동 수집하여 Lemmy에 등록

---

## 📋 개요

신규 포럼은 "콘텐츠가 없어서 유저가 안 오고, 유저가 없어서 콘텐츠가 안 쌓이는" 악순환에 빠지기 쉽다.
Content Importer는 Reddit, YouTube, 4chan, MGTOW.tv, Bitchute, 뉴스 RSS 등 8개 외부 소스의
인기 게시물을 자동으로 수집하여 **소스별 전용 커뮤니티**에 봇 계정(`OratioRepostBot`)으로 등록하는 시스템이다.

### 핵심 특징
- **8개 소스 → 소스별 전용 커뮤니티**: 각 소스가 독립된 커뮤니티에 게시
- **댓글 자동 임포트**: 소스 웹사이트의 인기 댓글 Top 3를 함께 가져와 Lemmy에 등록 (score 기반, AI 불필요)
- **YouTube Data API v3**: Trending 동영상 수집 + 공식 댓글 API (무료, 10k units/day)
- **소스 확장 쉬움**: 새 사이트 추가 = Collector 클래스 1개 작성
- **중복 방지**: SQLite 기반 fingerprint 저장으로 같은 URL 재등록 방지
- **AI 선별**: Gemini 2.5-flash (dynamic thinking) — 1사이클당 1회 배치 호출, 월 ~₩360~720
- **관리 API**: FastAPI 기반 수동 트리거, 통계, 이력 조회

---

## 🏗️ 아키텍처 (v3 — 배치 AI)

```
┌──────────────────────────────────────────────────────────────┐
│                   Scheduler (6시간마다)                        │
│                                                              │
│  Phase 1: 전체 소스 수집                                      │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐     │
│  │Reddit  │ │ArsTech │ │Science │ │Reuters │ │YouTube │ ... │
│  │(2 sub) │ │  RSS   │ │  RSS   │ │  RSS   │ │API v3  │     │
│  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘     │
│      └──────────┴──────────┴──────────┴──────────┘           │
│                            ▼                                 │
│                  DedupStore (SQLite)                          │
│                  중복 URL 제거                                │
│                            ▼                                 │
│  Phase 2: AI 배치 선별 (Gemini 2.5-flash, 1회 호출)           │
│            title + body preview 전송, dynamic thinking        │
│            소스별 쿼타에 따라 N개씩 선별                       │
│            실패 시 → score 기반 fallback                      │
│                            ▼                                 │
│  Phase 3: 소스별 전용 커뮤니티에 게시 + 인기 댓글 임포트       │
│            reddit, arstechnica, sciencedaily, reuters,        │
│            youtube, fourchan, mgtowtv, bitchute               │
│            (한국어 ≥30% → banmal 커뮤니티 오버라이드)          │
│                            ▼                                 │
│  Phase 3.5: 댓글 임포트 (score 기반 Top 3)                    │
│            YouTube: commentThreads.list (좋아요 순)            │
│            4chan: quote-count 기반 (>>replies 수)              │
│            Reddit: JSON API top sort (datacenter IP 차단 가능) │
└──────────────────────────────────────────────────────────────┘
```

---

## 📁 파일 구조

```
oratio/content_importer/
├── app.py                  # FastAPI 엔트리포인트 (포트 8085)
├── config.py               # 환경변수 기반 설정 + 소스 정의
├── models.py               # NormalizedPost, NormalizedComment 데이터클래스
├── scheduler.py            # v3 배치 파이프라인 (전체 수집 → 1회 AI → 소스별 게시)
├── lemmy_client.py         # Lemmy API v3 클라이언트 (로그인, 글 등록)
├── dedup.py                # SQLite 중복 제거 저장소
├── ai_selector.py          # v3 배치 AI 선별 (Gemini, dynamic thinking)
├── collectors/
│   ├── base.py             # 추상 베이스 클래스
│   ├── reddit.py           # Reddit RSS 수집기
│   ├── rss_news.py         # 범용 RSS/Atom 수집기 (ArsTechnica, ScienceDaily, Reuters)
│   ├── youtube.py          # YouTube Data API v3 수집기 (Trending + 댓글)
│   ├── fourchan.py         # 4chan JSON API 수집기
│   ├── mgtow.py            # MGTOW.tv HTML 스크래핑 수집기
│   ├── bitchute.py         # Bitchute POST API 수집기
│   └── ilbe.py             # Ilbe 수집기 (비활성화)
├── Dockerfile              # Python 3.11-slim 기반
├── requirements.txt        # fastapi, feedparser, httpx, beautifulsoup4 등
├── setup_content_importer.sh  # 봇 계정 + 커뮤니티 초기 생성
└── README.md
```

---

## ⚙️ 환경변수 (.env)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LEMMY_BOT_USERNAME` | `OratioRepostBot` | 봇 계정 이름 |
| `LEMMY_BOT_PASSWORD` | (자동생성) | 봇 계정 비밀번호 |
| `LEMMY_DEFAULT_COMMUNITY` | `trending` | 기본 등록 커뮤니티 (각 소스가 개별 지정) |
| `IMPORT_INTERVAL_MINUTES` | `360` | 수집 주기 (분). 360 = 6시간 |
| `IMPORT_ON_STARTUP` | `false` | 시작 시 즉시 수집 여부 |
| `AI_ENABLED` | `true` | AI 선별 사용 여부 |
| `AI_PROVIDER` | `gemini` | AI 제공자 (`openai` / `anthropic` / `gemini`) |
| `GEMINI_API_KEY` | (필수) | Gemini API 키 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini 모델 (dynamic thinking) |
| `AI_PICKS_PER_SOURCE` | `3` | 소스별 기본 AI 선별 수 |
| `IMPORTER_API_KEY` | (LEMMY_API_KEY) | 관리 API 인증 키 |
| `YOUTUBE_API_KEY` | (필수) | YouTube Data API v3 키 (Google Cloud Console에서 발급, 무료) |
| `COMMENTS_ENABLED` | `true` | 소스 댓글 자동 임포트 활성화 여부 |
| `COMMENTS_PER_POST` | `3` | 게시물당 가져올 인기 댓글 수 |

---

## 🔄 수집 파이프라인 상세

### 1단계: 수집 (Collectors)

현재 활성화된 8개 소스 (소스별 전용 커뮤니티):

| 소스 | 타입 | 수집 수 | 대상 커뮤니티 | AI 선별 수 |
|------|------|---------|-------------|-----------|
| Reddit r/technology | RSS | 25 | reddit | 3 |
| Reddit r/worldnews | RSS | 25 | reddit | 3 |
| Ars Technica | RSS | 20 | arstechnica | 3 |
| ScienceDaily | RSS | 20 | sciencedaily | 2 |
| Reuters (Google News 경유) | RSS | 25 | reuters | 3 |
| YouTube (US Trending) | API v3 | 25 | youtube | 2 |
| 4chan /pol/ | JSON API | 20 | fourchan | 2 |
| MGTOW.tv | HTML 스크래핑 | 15 | mgtowtv | 2 |
| Bitchute | POST API | 15 | bitchute | 2 |

**비활성화**: BBC World, Ilbe

### 2단계: 정규화 (NormalizedPost)

모든 소스의 게시물이 동일한 형태로 변환됨:
- `title`, `url`, `body`, `author`, `score`, `source`, `source_community`
- `fingerprint`: URL의 SHA256 해시 (중복 판별용)

### 3단계: 중복 제거 (DedupStore)

SQLite DB (`/data/importer.db`)에 등록된 fingerprint를 저장.
이전에 등록한 URL은 자동 제외.

### 4단계: 선별 (AI Batch Selector — v3)

- **v3 배치 방식**: 전체 소스의 게시물을 **1회 AI 호출**로 처리
- title + body_preview(200자) + score 전송 → AI 판단 품질 향상
- Gemini 2.5-flash dynamic thinking (기본값) 사용
- 소스별 쿼타 (`ai_picks`)에 따라 N개씩 선별
- **AI 실패 시**: score 기반 fallback (즉시 전환, retry 없음)
- **월 예상 비용**: ~₩360~720 (하루 4회 × 30일 = 120회 호출)

### 5단계: 등록 (LemmyClient)

`OratioRepostBot` 계정으로 Lemmy API v3를 통해 게시물 등록.
본문에 출처, 원작자, 점수, AI 선정 이유 등이 Markdown으로 포매팅됨.

### 6단계: 댓글 임포트 (Score 기반, AI 불필요)

게시물 등록 직후, 해당 소스 웹사이트에서 **인기 댓글 Top N**을 가져와 Lemmy 댓글로 등록.
AI를 사용하지 않으므로 추가 비용 ₩0.

**댓글 지원 소스별 방식:**

| 소스 | API | 정렬 기준 | 비고 |
|------|-----|-----------|------|
| **YouTube** | `commentThreads.list` (공식 API) | 좋아요 수 (likeCount) | 1 quota unit/호출, 무료 |
| **4chan** | Thread JSON API | quote-count (>>replies 수) | API 키 불필요 |
| **Reddit** | `{permalink}.json?sort=top` | upvotes | Datacenter IP 403 차단 가능 |
| MGTOW.tv | ❌ | — | 스팸 댓글만, likes 없음 |
| Bitchute | ❌ | — | 댓글 API 없음 (404) |
| RSS 소스 | ❌ | — | RSS에 댓글 정보 없음 |

**댓글 포맷 (Lemmy 게시):**
```
💬 **@Author**님의 인기 댓글 1위 (youtube, ⬆️ 942):

> 댓글 본문 내용...

*— Imported comment by OratioRepostBot*
```

**YouTube API 비용:**
- Trending 수집: 1 unit/호출
- 댓글 수집: 1 unit × 선택된 포스트 수 (~2개)
- 하루 4사이클 × 3 units = ~12 units/day → 10,000 units/day 무료 한도의 **0.12%**

---

## 🚀 배포 방법

### 최초 설치

```bash
cd /home/user/Oratio/oratio

# 1. 비밀번호 생성 (.env에 봇 비밀번호 포함)
./refresh_passwords.sh

# 2. 봇 계정 + 커뮤니티 생성 (captcha 자동 처리)
chmod +x content_importer/setup_content_importer.sh
./setup_content_importer.sh

# 3. Docker 빌드 및 실행
docker-compose build content-importer
docker-compose up -d content-importer
```

### 수동 트리거 (즉시 수집)

```bash
docker exec oratio-content-importer curl -s -X POST \
  http://localhost:8085/api/importer/trigger \
  -H "X-API-Key: $(grep IMPORTER_API_KEY /home/user/Oratio/oratio/.env | cut -d= -f2)"
```

### 상태 확인

```bash
# 로그 확인
docker-compose logs -f content-importer

# 헬스체크
docker-compose exec -T content-importer curl -s http://localhost:8085/health
```

---

## 📡 관리 API

| 엔드포인트 | 메서드 | 인증 | 설명 |
|------------|--------|------|------|
| `/health` | GET | ❌ | 서비스 상태 |
| `/api/importer/trigger` | POST | ✅ | 즉시 수집 실행 |
| `/api/importer/stats` | GET | ✅ | 총 등록 수, 실행 횟수 |
| `/api/importer/history` | GET | ✅ | 최근 등록 이력 |
| `/api/importer/last-run` | GET | ✅ | 마지막 실행 결과 |
| `/api/importer/sources` | GET | ✅ | 활성 소스 목록 |

인증: `X-API-Key` 헤더에 `LEMMY_API_KEY` 값 전달.

---

## 🔧 새 소스 추가하기

### RSS/Atom 피드 (코드 수정 없음)

`config.py`의 `DEFAULT_SOURCES`에 추가:

```python
{
    "name": "bbc_news",
    "type": "rss",
    "url": "https://feeds.bbci.co.uk/news/rss.xml",
    "source_label": "bbc",
    "community": "news",
    "limit": 15,
    "enabled": True,
}
```

### 새 사이트 타입 (커스텀 Collector)

```python
# collectors/my_source.py
from collectors.base import BaseCollector
from models import NormalizedPost

class MySourceCollector(BaseCollector):
    def fetch(self) -> list[NormalizedPost]:
        # 사이트별 수집 로직 구현
        ...
        return posts
```

`scheduler.py`의 `_get_collector()`에 타입 매핑 추가.

---

## 🔍 트러블슈팅

### 봇 로그인 실패 (`incorrect_login`)

```bash
# DB에서 봇 계정 존재 확인
docker-compose exec -T postgres psql -U lemmy -d lemmy -tA -c \
  "SELECT name FROM person WHERE name = 'OratioRepostBot';"

# 없으면 setup 스크립트 재실행
./setup_content_importer.sh
```

### Reddit 수집 안 됨

Reddit은 데이터센터 IP를 차단할 수 있음. `old.reddit.com` RSS를 사용하면 대부분 해결됨.
로그에서 `403` 에러가 계속 나오면 VPN 또는 프록시 설정 필요.

### 같은 글 반복 등록

SQLite DB 파일 확인:
```bash
docker-compose exec -T content-importer python3 -c "
import sqlite3
conn = sqlite3.connect('/data/importer.db')
print('등록된 글 수:', conn.execute('SELECT COUNT(*) FROM imported_posts').fetchone()[0])
"
```

---

## 📊 운영 가이드

### 권장 설정 (소규모 포럼)

```env
IMPORT_INTERVAL_MINUTES=1440   # 하루 1번
AI_MAX_PICKS=5                 # 사이클당 5개
IMPORT_ON_STARTUP=false
```

### 권장 설정 (활성 포럼)

```env
IMPORT_INTERVAL_MINUTES=360    # 6시간마다
AI_MAX_PICKS=10                # 사이클당 10개
AI_ENABLED=true                # AI 선별 활성화
```

### 수집 중지

```bash
docker-compose stop content-importer
```

### 데이터 초기화 (전체 리셋)

```bash
docker-compose stop content-importer
rm -f data/content_importer/importer.db
docker-compose start content-importer
```

---

## 📝 수정 이력

| 날짜 | 변경 내용 |
|------|----------|
| 2026-03-30 | 최초 구현. Reddit RSS, 뉴스 RSS 수집기, 점수 기반 선별, Lemmy 등록 |
| 2026-03-30 | setup_content_importer.sh에 captcha 자동 처리 추가 |
| 2026-03-30 | refresh_passwords.sh에 봇 비밀번호 + content-importer 서비스 추가 |
| 2026-03-30 | 라이브 테스트 성공 — 55개 수집 → 10개 선별 → Lemmy 등록 완료 |
| 2026-03-30 | Ilbe collector 제거, DCInside 주식갤러리(neostock) collector 추가 |
| 2026-03-30 | DCInside 제거, Ilbe collector 복구 + 썸네일 추출 기능 추가, Lemmy custom_thumbnail 지원 |
| 2026-03-31 | **v3 아키텍처**: 소스별 전용 커뮤니티 + 배치 AI (1회 호출/사이클) |
| 2026-03-31 | 8개 소스 확장: YouTube, 4chan, MGTOW.tv, Bitchute, ScienceDaily, Reuters 추가 |
| 2026-03-31 | Gemini 2.5-flash `thinkingBudget: 0` 적용 후 해제 → dynamic thinking + body preview 복원 (월 ~₩500) |
| 2026-03-31 | BBC 소스 비활성화, retry 로직 제거, 프롬프트 최적화 (title만 전송) |
| 2026-03-31 | **댓글 자동 임포트**: score 기반 Top 3 댓글 (YouTube, 4chan, Reddit) — AI 불필요, ₩0 |
| 2026-03-31 | **YouTube Data API v3**: RSS → Trending API + 공식 commentThreads.list 전환 (무료 10k units/day) |
| 2026-03-31 | 댓글 포맷: `💬 Author님의 인기 댓글 N위 (source, ⬆️ score)` |
| 2026-03-31 | 하드코딩 시크릿 제거 (문서 내 API 키 → .env 참조로 변경) |
