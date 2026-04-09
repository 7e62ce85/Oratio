# Content Importer System (자동 콘텐츠 수집 봇)

> **작성일**: 2026-03-30 | **최종 수정**: 2026-04-08 (Bitchute/Rumble 채널당 1개 제한, 4chan 복합 스코어링 + 필터링 + 404 liveness check)
> **서비스명**: `content-importer` (Docker)
> **목적**: 빈 포럼 문제 해결 — 외부 인기 게시물을 자동 수집하여 Lemmy에 등록

---

## 📋 개요

신규 포럼은 "콘텐츠가 없어서 유저가 안 오고, 유저가 없어서 콘텐츠가 안 쌓이는" 악순환에 빠지기 쉽다.
Content Importer는 Reddit, YouTube, 4chan, MGTOW.tv, Bitchute, Rumble, Imgur, Instagram, 9gag, XCancel(트윗 검색), 뉴스 RSS 등 여러 외부 소스의
인기 게시물을 자동으로 수집하여 **소스별 전용 커뮤니티**에 봇 계정(`OratioRepostBot`)으로 등록하는 시스템이다.

### 핵심 특징
- **여러 소스 → 소스별 전용 커뮤니티**: 각 소스가 독립된 커뮤니티에 게시
- **댓글 자동 임포트**: 소스 웹사이트의 인기 댓글 Top 3를 함께 가져와 Lemmy에 등록 (score 기반, AI 불필요, URL 포함 댓글 자동 제외)
- **Upgoat 본문 content 추출**: listing 페이지에서 self-post 본문 자동 추출 → `📝 Original content` blockquote 포맷으로 Lemmy body에 포함
- **YouTube Data API v3**: Trending 동영상 수집 + 공식 댓글 API (무료, 10k units/day)
- **소스 확장 쉬움**: 새 사이트 추가 = Collector 클래스 1개 작성
- **중복 방지**: SQLite 기반 fingerprint 저장으로 같은 URL 재등록 방지
- **AI 선별**: Gemini 2.5-flash (dynamic thinking) — 1사이클당 1회 배치 호출, 월 ~₩180~360
- **관리 API**: FastAPI 기반 수동 트리거, 통계, 이력 조회

---

## 🏗️ 아키텍처 (v3 — 배치 AI)

```
┌──────────────────────────────────────────────────────────────┐
│                   Scheduler (12시간마다)                       │
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
│            ※ skip_ai 소스(Upgoat 등)는 전체 import            │
│                            ▼                                 │
│  Phase 3: 전체 게시물 셔플 + 소스별 전용 커뮤니티에 게시       │
│            random.shuffle()로 모든 소스 게시물 골고루 섞어 등록 │
│            reddit, arstechnica, sciencedaily, reuters,        │
│            youtube, upgoat, fourchan, mgtowtv, bitchute,      │
│            rumble, imgur, instagram, 9gag, xcancel            │
│            (한국어 ≥30% → banmal 커뮤니티 오버라이드)          │
│                            ▼                                 │
│  Phase 3.5: 댓글 임포트 (score 기반 Top 3)                    │
│            YouTube: commentThreads.list (좋아요 순)            │
│            4chan: quote-count 기반 (>>replies 수)              │
│            Reddit: RSS 폴백 (JSON 403 시, 위치 기반 정렬)      │
│            ArsTechnica: Civis 포럼 스크래핑 (XenForo, 추천 순) │
│            Upgoat: HTML 스크래핑 (viewpost, points 순)         │
│            MGTOW.tv: HTML 스크래핑 (watch 페이지, 좋아요 순)   │
│            Bitchute: CommentFreely JSON API (좋아요-싫어요 순) │
│            Rumble: comment.list API (로그인 필수, DC IP 차단)  │
│            ※ URL 포함 댓글 자동 제외 (스팸 필터)               │
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
│   ├── html_utils.py       # HTML→Text 공통 유틸 (태그 제거, 줄바꿈 보존, entity 디코딩)
│   ├── reddit.py           # Reddit RSS 수집기 (+ RSS 댓글 폴백)
│   ├── rss_news.py         # 범용 RSS/Atom 수집기 (ScienceDaily, Reuters)
│   ├── arstechnica.py      # ArsTechnica RSS 수집 + Civis 포럼 댓글 스크래핑
│   ├── youtube.py          # YouTube Data API v3 수집기 (Trending + 댓글)
│   ├── fourchan.py         # 4chan JSON API 수집기
│   ├── mgtow.py            # MGTOW.tv HTML 스크래핑 수집기 (+ 댓글)
│   ├── bitchute.py         # Bitchute old.bitchute.com SSR 스크래핑 수집기 (Trending + 댓글)
│   ├── rumble.py           # Rumble service.php JSON API 수집기 (cloudscraper)
│   ├── upgoat.py           # Upgoat.net HTML 스크래핑 수집기 (+ 댓글)
│   ├── imgur.py            # Imgur API v3 → RSS → HTML 폴백 체인 수집기 (+ 댓글)
│   ├── instagram.py        # Instagram 스크래핑 수집기 (공개 프로필/태그 기반)
│   ├── ninegag.py          # 9gag JSON API 수집기 (v1/group-posts + comment-cdn 댓글)
│   ├── xcancel.py          # XCancel/Nitter 트윗 검색 수집기 (인스턴스 폴백 + 댓글)
│   └── ilbe.py             # Ilbe 수집기 (비활성화)
├── Dockerfile              # Python 3.11-slim 기반
├── requirements.txt        # fastapi, feedparser, httpx, beautifulsoup4, cloudscraper 등
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
| `IMPORT_INTERVAL_MINUTES` | `720` | 수집 주기 (분). 720 = 12시간 |
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

현재 활성화된 소스 (예시):

| 소스 | 타입 | 수집 수 | 대상 커뮤니티 | AI 선별 수 |
|------|------|---------|-------------|-----------|
| Reddit r/technology | RSS | 25 | reddit | 2 |
| Reddit r/worldnews | RSS | 25 | reddit | 2 |
| Ars Technica | RSS | 20 | arstechnica | 3 |
| ScienceDaily | RSS | 20 | sciencedaily | 2 |
| Reuters (Google News 경유) | RSS | 25 | reuters | 3 |
| YouTube (US Trending) | API v3 | 25 | youtube | 2 |
| Upgoat | HTML 스크래핑 (다중 페이지) | ~45-55 (13~72h 필터) | upgoat | 전체 (skip_ai) |
| 4chan (전체 인기 보드) | JSON API (21개 SFW 보드 스캔, 복합 스코어링 + 필터링) | 20 | fourchan | 10 |
| MGTOW.tv | HTML 스크래핑 | 15 | mgtowtv | 2 |
| Bitchute (Trending) | HTML 스크래핑 (old.bitchute.com SSR) | 15 | bitchute | 2 |
| Rumble (Trending) | JSON API (service.php + cloudscraper) | 15 | rumble | 2 |
| Imgur (Gallery / Memes) | API v3 → RSS → HTML 폴백 체인 | 20 | imgur | 3 |
| Instagram (공개 태그/계정) | HTML 스크래핑 (공개 프로필/태그) | 20 | instagram | 3 |
| 9gag (Hot) | JSON API (`/v1/group-posts`) | 20 | ninegag | 3 |
| XCancel (Twitter/X 검색) | HTML 스크래핑 (Nitter 인스턴스 폴백) | 25 | xcancel | 2 |

**비활성화**: BBC World, Ilbe

> 참고: XCancel 검색 페이지(예: https://xcancel.com/search?f=tweets&q=Liberty)는 검색 결과 페이지 자체를 크롤링/임포트 대상으로 설정할 수 있다. `xcancel` Collector는 검색 쿼리 URL을 소스로 받아 해당 검색의 상위 트윗들을 수집하도록 동작한다.
<!-- 플랫폼	구현 가능?	추천?
Twitter/X	⚠️ 조건부 가능	❌ 비추. 공식 API는 월 $50+ 비용, Nitter는 너무 불안정. 현재 시스템의 운영비(AI ₩720/월)보다 X API만으로 수십배 비쌈.
TikTok	❌ 거의 불가능	❌ 절대 비추. Trending 수집 공식 경로 자체가 없고, 비공식 방법은 Playwright 필요 + 봇 감지 심하고 + 라이브러리가 수시로 깨짐. 게다가 비디오 플랫폼이라 텍스트 기반 Lemmy에 맞지도 않아. -->

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
- **월 예상 비용**: ~₩180~360 (하루 2회 × 30일 = 60회 호출)

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
| **Reddit** | RSS 폴백 (`{permalink}.rss`) | 위치 기반 (hot/best 순) | JSON 403 시 자동 전환, score 없음 |
| **ArsTechnica** | Civis 포럼 HTML 스크래핑 (XenForo) | Upvote 수 | 기사 페이지에서 Civis thread URL 추출 |
| **Upgoat** | HTML 스크래핑 (viewpost) | points | top-level만 (중첩 reply 제외) |
| **MGTOW.tv** | HTML 스크래핑 (watch 페이지) | 좋아요 수 | URL 포함 댓글 제외 (스팸 필터) |
| **Bitchute** | CommentFreely JSON API | 좋아요-싫어요 | `cf_auth` 토큰 추출, top-level만 |
| **Rumble** | `comment.list` (service.php) | 좋아요-싫어요 | 로그인 필수 (`RUMBLE_USERNAME/PASSWORD`). 데이터센터 IP에서 로그인 차단됨 — VPN/주거용 IP 필요 |
| **Imgur** | API v3 / RSS / HTML 폴백 체인 | points | API (Client-ID) → RSS (`hot/viral.rss`) → HTML 스크래핑 순 폴백. ⚠️ DC IP에서 타임아웃 |
| **Instagram** | HTML 스크래핑 (공개 프로필/태그) | 좋아요 수 | ⚠️ 인스타 anti-bot으로 사실상 차단됨. 코드 준비만 완료 |
| **9gag** | `comment-cdn.9gag.com` JSON API | score (likeCount) | `comment-list.json?appId=a_dd8f2b7d304a10edaf6f29517ea0ca4100a43d1b&order=score` ✅ 작동 확인 |
| **XCancel (Tweets)** | HTML 스크래핑 (Nitter 인스턴스 폴백) | reply/like 수 | xcancel.com + 5개 Nitter 인스턴스 순차 시도. ⚠️ 인스턴스 불안정 |
| ScienceDaily, Reuters | ❌ | — | 원본 사이트에 댓글 섹션 없음 |

**댓글 포맷 (Lemmy 게시):**
```
💬 **@Author**'s Top Comment #1 (youtube, ⬆️ 942):

> 댓글 본문 내용...
```

**YouTube API 비용:**
- Trending 수집: 1 unit/호출
- 댓글 수집: 1 unit × 선택된 포스트 수 (~2개)
- 하루 2사이클 × 3 units = ~6 units/day → 10,000 units/day 무료 한도의 **0.06%**

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
docker image prune -f   
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
| 2026-04-02 | **Upgoat.net 소스 추가**: HTML 스크래핑 collector + 댓글 import (score 기반 Top 3) |
| 2026-04-02 | 댓글 포맷 영문화: `~님의 인기 댓글 N위` → `'s Top Comment #N` + 중복 footer 삭제 |
| 2026-04-02 | Source 링크 개선: `source_permalink` 활용 → 📰 Source 클릭 시 소스 사이트 게시물 페이지로 연결 |
| 2026-04-02 | Reddit 댓글 403 대응: `www.reddit.com` → `old.reddit.com` JSON 엔드포인트로 전환 |
| 2026-04-02 | `setup_content_importer.sh` 소프트코딩: 커뮤니티 목록을 `config.py` enabled 소스에서 자동 추출 (하드코딩 제거) |
| 2026-04-02 | **MGTOW.tv 댓글 import 추가**: watch 페이지 HTML 스크래핑, 좋아요 순 Top 3, URL 포함 댓글 제외 (스팸 필터) |
| 2026-04-02 | **Bitchute 댓글 import 추가**: old.bitchute.com HTML 스크래핑 (SSR), 좋아요-싫어요 순 Top 3, URL 포함 댓글 제외 |
| 2026-04-02 | **Bitchute 수집 방식 전환**: POST search API → old.bitchute.com SSR trending 직접 스크래핑 (실제 Trending 데이터, Day/Week/Month 지원) |
| 2026-04-02 | **Bitchute 댓글 CommentFreely API 전환**: HTML 스크래핑 → `commentfreely.bitchute.com` JSON API (`cf_auth` 토큰, top-level 필터) |
| 2026-04-02 | **ArsTechnica 댓글 import 추가**: 전용 `ArsTechnicaCollector` 생성, Civis 포럼(XenForo) 스크래핑, Upvote 순 Top 3 |
| 2026-04-02 | **Reddit 댓글 RSS 폴백**: JSON API 403 차단 시 `{permalink}.rss` 자동 전환 (feedparser 직접 요청 403 → requests 선행 fetch로 해결) |
| 2026-04-02 | **Upgoat 댓글 중첩 버그 수정**: `.comment-row` 중첩 구조로 reply body가 부모에 복사되던 문제 → depth=0 필터 + 직접자식 body 추출 |
| 2026-04-02 | **Rumble 소스 추가**: `service.php` 비공개 JSON API 발견 (`media.search`), cloudscraper로 CF 우회, views 기반 정렬, 10번째 소스 (댓글 미지원) |
| 2026-04-02 | **Rumble 댓글 import 구현**: `comment.list` API 리버스엔지니어링, `user.get_salts` + MD5 hashStretch 로그인. `_hash_stretch` 버그 수정 (hex→raw bytes). 단, 데이터센터 IP에서 로그인 차단됨 (error JAJSJODIH589SAD) — VPN/주거용 IP 필요 |
| 2026-04-03 | **4개 소스 추가**: XCancel (트윗 검색), Imgur, Instagram, 9gag — collector + 댓글 import 구현 |
| 2026-04-03 | **9gag**: 내부 JSON API (`/v1/group-posts`) 수집 + `comment-cdn.9gag.com` 댓글 API. ✅ 20개 수집, 3개 게시, 9개 댓글 성공 |
| 2026-04-03 | **XCancel**: xcancel.com + Nitter 인스턴스 5개 fallback 구현. ⚠️ 전 인스턴스 403/다운 (인프라 한계) |
| 2026-04-03 | **Imgur**: API v3 → RSS (`hot/viral.rss`) → HTML 3단 폴백 체인. ⚠️ DC IP에서 전부 타임아웃 |
| 2026-04-03 | **Instagram**: 다중 엔드포인트 시도 (`/api/v1/tags/`, graphql, `explore/tags/`). ⚠️ anti-bot으로 수집 불가 |
| 2026-04-03 | **9gag 댓글 API 버그 수정**: `9gag.com/v1/topComments.json` (404) → `comment-cdn.9gag.com/v2/cacheable/comment-list.json` (✅) |
| 2026-04-03 | **라이브 테스트**: 15소스 250개 수집 → 30개 게시 + 69개 댓글. 9gag ✅, XCancel/Imgur/Instagram ⚠️ DC IP 한계 |
| 2026-04-03 | **Upgoat 전체 import**: 다중 페이지 크롤링 + 13시간 이상 된 게시물만 수집 (~90-110개/사이클). AI 선별 비활성화 (`skip_ai=True`), 상대 시간 파싱 (`N hours/days ago`) 구현 |
| 2026-04-03 | **4chan 전체 보드 수집**: `/pol/` 단일 보드 → 23개 인기 보드 스캔 후 replies 기준 글로벌 정렬. 보드당 top 10 → 전체 top 20 선별 |
| 2026-04-03 | **게시 순서 셔플**: 소스별 순차 게시 → `random.shuffle()`로 전체 게시물 섞어서 등록. 다양한 소스의 게시물이 골고루 인터리브됨 |
| 2026-04-03 | **Upgoat 72h 상한**: `max_age_hours: 72` 추가 — 13~72시간 범위의 게시물만 import (장기 다운타임 시 매우 오래된 게시물 방지) |
| 2026-04-03 | **Upgoat 본문 content 추출**: listing 페이지 `textcontentdisplay` div에서 self-post 텍스트 자동 추출. `📝 **Original content**: > blockquote` 포맷으로 body에 포함. link-post URL echo는 자동 제외 |
| 2026-04-03 | **봇 게시물 정리**: interaction(추가 upvote/comment) 없는 801개 게시물 hard-delete (PostgreSQL + SQLite dedup DB). interaction 있는 5개만 보존 |
| 2026-04-03 | **수집 주기 12시간**: `IMPORT_INTERVAL_MINUTES=720`. 라이브 테스트: 404 수집 → 228 게시 + 430 댓글 (Upgoat 174개 포함) |
| 2026-04-06 | **HTML→Text 공통 유틸**: `collectors/html_utils.py` 신규 — `<br>`/`<p>` 줄바꿈 보존, `<wbr>` 제거(URL 보호), `html.unescape()` entity 디코딩. 8개 collector 일괄 적용 (fourchan, reddit, rss_news, bitchute, imgur, ilbe, youtube, upgoat) |
| 2026-04-06 | **4chan 댓글 layer-1 필터**: OP를 직접 `>>quote`하는 1단계 댓글만 import (2단계+ 대댓글은 맥락 없이 의미불명 → 제외) |
| 2026-04-06 | **Upgoat content URL 포함**: `textcontentdisplay`의 `startswith("http")` 필터 제거 → post URL과 정확히 동일한 경우만 skip, URL+텍스트 혼합 content는 import |
| 2026-04-08 | **4chan 복합 스코어링**: `replies` 단독 정렬 → `unique_ips × log2(replies + 1)` 복합 스코어로 전환. 소수 채팅방(replies 700+, ips 15) 대비 다수 참여 토론(replies 150, ips 80) 우선 선별 |
| 2026-04-08 | **4chan 수집 필터링**: sticky/closed/bumplimit 도달 thread 제외, 24시간 초과 thread 제외, unique_ips < 8 제외, "General/Gossip" 패턴 recurring thread 제외 |
| 2026-04-08 | **4chan 404 liveness check**: Lemmy 게시 직전 `a.4cdn.org` HEAD 요청으로 thread 생존 확인. 404면 게시 스킵 (fail-open: 네트워크 에러 시 게시 진행) |
| 2026-04-08 | **4chan NSFW 보드 제외**: `/b/` (Random), `/gif/` (Adult GIF) 제거 — porn/gore 빈출 보드. `/pol/`은 정치 토론 위주라 유지. 23개 → 21개 보드 |
| 2026-04-08 | **General 패턴 regex 강화**: `edition` 단독 매칭 추가, `/xxx/ - ...` 형식(e.g. `/mlb/ - angry leaf edition`) 차단, 깨진 유니코드 패턴 수정 |
| 2026-04-08 | **Bitchute/Rumble 채널당 1개 제한**: 같은 author/channel의 영상을 사이클당 최대 1개만 수집. 일일 에피소드 시리즈(Alex Jones, X22 Report, Timcast 등)가 trending을 독점하는 문제 해결 → AI 후보 풀 다양성 향상 |
| 2026-04-08 | **General regex v3 + /int/ 국가 잡담방 차단**: (1) `/xxx/` 단독 제목 패턴 추가 (`^/\w{2,12}/\s*$`), (2) `/xxx/ +` 구분자 `+` 추가, (3) `brit/pol/` 등 국가별 정치 general 패턴, (4) `/v4/ /ori/` 복수 slug 패턴. `_INT_COUNTRY_GENERALS` frozenset 30개 — `/deutsch/`, `/sauna/`, `/cum/`, `/polska/` 등 /int/ 보드 recurring 국가 잡담방 exact-match 차단 |
| 2026-04-08 | **빈 제목 게시 방지**: `lemmy_client.py`에 `_valid_title()` 추가 — alphanumeric 문자가 없는 제목(빈 문자열, 이모지만 등)은 Lemmy API 호출 전 스킵. `invalid_post_title` 400 에러 방지 |
