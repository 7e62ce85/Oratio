# 🌐 다국어(i18n) 시스템 가이드

> 최종 작업일: 2026-04-20

## 아키텍처 개요

```
[사용자가 Lemmy UI에서 언어 선택]
        │
        ▼
I18NextService.ts ──► localStorage('i18nextLng') 저장
        │                        │
        ▼                        ▼
  Lemmy UI 커스텀 페이지      Flask 결제 페이지
  (about, wallet, ads)       (index, help, invoice, error, success)
        │                        │
        ▼                        ▼
custom-translations.json     translations.json
  → generate_translations.js   → i18n.js (클라이언트 JS)
  → per-language .ts files
```

**핵심**: Lemmy UI와 Flask 결제 페이지가 `localStorage('i18nextLng')`를 통해 언어를 공유함.

---

## 파일 구조

| 파일 | 위치 | 역할 |
|------|------|------|
| `custom-translations.json` | `lemmy-ui-custom/` | Lemmy UI 커스텀 페이지 번역 마스터 |
| `generate_translations.js` | `lemmy-ui-custom/` | JSON → per-language .ts 변환 스크립트 |
| `translations.json` | `oratio/bitcoincash_service/static/js/` | Flask 결제 페이지 번역 마스터 |
| `i18n.js` | `oratio/bitcoincash_service/static/js/` | Flask 클라이언트 번역 로직 |
| `I18NextService.ts` | `lemmy-ui-custom/src/shared/services/` | localStorage 동기화 포함 |

---

## 현재 상태 (2026-04-20)

### Lemmy UI (`custom-translations.json`)
- **136키** × 31개 언어 — **전체 완료 (누락 0)**
- 대상 페이지: `about.tsx`, `wallet.tsx`, `ads.tsx` (캠페인 폼 포함)

### Flask 결제 (`translations.json`)
- **103키** × 31개 언어 — **전체 완료 (누락 0)**
- 대상 페이지: index.html, help.html, invoice.html, error.html, payment_success.html

### 지원 언어 (31개)
```
en, ko, ja, zh, zh_Hant, de, fr, es, ru, pt, pt_BR,
it, nl, pl, sv, da, fi, ar, fa, vi, id, el, cs, bg,
hr, ca, eu, eo, ga, gl, oc
```

---

## 작업 절차

### 1. 새 언어 추가

```bash
# Step 1: custom-translations.json에 언어 추가
# "새언어코드": { "key": "번역", ... }

# Step 2: .ts 파일 생성
cd /home/user/Oratio/lemmy-ui-custom
node generate_translations.js

# Step 3: translations.json에도 추가 (Flask)
# oratio/bitcoincash_service/static/js/translations.json

# Step 4: Docker 리빌드 (Lemmy UI만)
cd /home/user/Oratio/oratio
docker-compose stop lemmy-ui && docker-compose rm -f lemmy-ui
docker rmi lemmy-ui-custom:latest
docker-compose build --no-cache lemmy-ui
docker-compose up -d lemmy-ui && docker image prune -f
```

### 2. 페이지 텍스트 변경 (기존 키 수정)

1. **영어(en) 값 수정** → 해당 JSON 파일에서 `en` 키 수정
2. **다른 언어도 반영** → 각 언어의 동일 키 수정
3. Lemmy UI 변경 시 `node generate_translations.js` 실행
4. Docker 리빌드

### 3. 새 번역 키 추가 (새 UI 요소)

1. **소스 코드에 `i18n.t("new_key")` 추가** (tsx 파일)
2. `custom-translations.json`의 **모든 언어**에 `"new_key"` 추가
3. Flask 페이지면 `translations.json`에도 추가 + HTML에 `data-i18n="new_key"` 속성
4. `node generate_translations.js` → Docker 리빌드

---

## 주의사항

- `custom-translations.json`은 수동 편집 가능하나, 스크립트 실행 전 반드시 최신 상태 확인
- Flask `translations.json`은 리빌드 불필요 (정적 파일, 즉시 반영)
- `i18n.js`의 fallback 순서: `localStorage → navigator.language → 'en'`
- HTML `data-i18n` 속성: `data-i18n="키"` (텍스트), `data-i18n-html="키"` (HTML 포함)

---

## 로그인 후 언어 즉시 반영 (2026-04-20 수정)

기존 문제: 로그인 직후 브라우저 언어로 표시되다가 페이지 이동/새로고침 후에야 유저 설정 언어로 전환됨.

### 수정 파일 3개

| 파일 | 수정 내용 |
|------|-----------|
| `catch-all-handler.tsx` | SSR 시 `site.my_user.interface_language`를 Accept-Language보다 우선 적용 |
| `client/index.tsx` | SSR 언어 ≠ 클라이언트 언어일 때 `hydrate()` 대신 `render()`로 전체 DOM 재생성 |
| `home/login.tsx` | `handleLoginSuccess()`에서 `loadUserLanguage()` 호출 추가 |

**핵심**: 로그인 → `myUserInfo` 설정 → `loadUserLanguage()` → i18next 즉시 전환
