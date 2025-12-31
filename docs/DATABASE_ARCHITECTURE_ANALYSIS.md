# 📊 DB 통합 아키텍처 위험 분석

**작성일**: 2025-12-31  
**상태**: 현행 유지 권장

---

## 개요

현재 Oratio는 `/data/payments.db` 단일 SQLite 파일에 모든 결제/멤버십/광고 관련 데이터를 저장합니다.  
이 문서는 통합 DB 아키텍처의 위험 요소와 향후 권장 사항을 정리합니다.

---

## 현재 DB 구조

**파일 위치**: `/data/payments.db` (Docker 컨테이너: `bitcoincash-service`)

### 테이블 분류

| 도메인 | 테이블 | 설명 |
|--------|--------|------|
| **결제** | `invoices`, `addresses`, `user_credits`, `transactions` | BCH 결제 및 크레딧 |
| **멤버십** | `user_memberships`, `membership_transactions` | 멤버십 구독 |
| **업로드 쿼터** | `user_upload_quotas`, `upload_transactions`, `upload_pricing_config` | 파일 업로드 용량 |
| **VP 신고** | `user_vp_permissions`, `vp_reports`, `vp_reviews`, `vp_appeals`, `vp_notifications`, `vp_audit_log`, `moderator_vp_assignments` | Vote Power 신고 시스템 |
| **CP 신고** | `user_cp_permissions`, `cp_reports`, `cp_reviews`, `cp_appeals`, `cp_notifications`, `cp_audit_log`, `moderator_cp_assignments` | Content Policy 신고 시스템 |
| **광고** | `ad_credits`, `ad_campaigns`, `ad_impressions`, `ad_transactions`, `ad_config` | 광고 시스템 |

---

## 위험 분석

### 위험 요소

| 위험 | 심각도 | 설명 |
|------|--------|------|
| **동시성 병목** | 🟡 중간 | SQLite는 쓰기 잠금(write lock)이 DB 전체에 걸림. 광고 impression 대량 기록 시 결제 트랜잭션이 지연될 수 있음 |
| **단일 장애점** | 🟡 중간 | DB 파일 손상 시 모든 기능(결제/멤버십/광고)이 동시에 영향받음 |
| **백업 복잡성** | 🟢 낮음 | 하나의 파일이라 백업은 오히려 단순함 |
| **스키마 충돌** | 🟢 낮음 | 테이블명이 고유해서 현재는 문제없음 |
| **마이그레이션 위험** | 🔴 높음 | 향후 분리 시 데이터 이전 + 코드 변경 범위가 큼 |

### 지금 분리 시 위험이 높은 이유

1. **코드 변경 범위**: 모든 서비스 파일(`ad_service.py`, `membership_service.py`, `payment_service.py` 등)의 DB 경로 변경 필요
2. **데이터 마이그레이션**: 기존 데이터를 새 DB로 이전하는 스크립트 작성 필요
3. **Docker 볼륨**: 볼륨 구조 변경 및 docker-compose.yml 수정 필요
4. **트랜잭션 일관성**: 여러 DB에 걸친 트랜잭션은 2PC(Two-Phase Commit) 불가 → 데이터 일관성 문제 발생 가능
5. **테스트 부담**: 모든 기능에 대한 회귀 테스트 필요

---

## 권장 사항

| 시기 | 조치 | 우선순위 |
|------|------|----------|
| **지금** | ✅ 현행 유지. 정상 작동 중이고 트래픽이 낮다면 분리 불필요 | - |
| **단기** | 정기 백업 스크립트 확인 및 자동화 (예: `sqlite3 .backup` 또는 파일 복사) | 높음 |
| **중기** | 트래픽 증가 시 `ad_impressions` 테이블만 별도 DB로 분리 고려 (가장 쓰기가 많음) | 중간 |
| **장기** | PostgreSQL 전환 검토 (Lemmy 자체가 PostgreSQL 사용하므로 통합 가능) | 낮음 |

---

## ad_impressions 테이블 분리가 필요한 이유

### 문제점

`ad_impressions`는 **모든 페이지 로드마다 INSERT** 발생 → 다른 테이블 대비 쓰기 빈도가 압도적으로 높음.

| 테이블 | 쓰기 빈도 | 예시 |
|--------|----------|------|
| `user_credits`, `transactions` | 낮음 (사용자 액션 시) | 하루 수~수십 건 |
| `ad_impressions` | **매우 높음** (모든 페이지뷰) | 하루 수천~수만 건 |

### SQLite 쓰기 잠금 문제

SQLite는 **DB 전체에 쓰기 잠금**을 검. 트래픽 증가 시:

```
ad_impressions INSERT 대기열 → 다른 테이블 쓰기 대기 → 결제 응답 지연
최악: "database is locked" 에러 발생
```

### 분리 시 vs 분리 안 할 시

| 항목 | 분리 안 함 | 분리 함 |
|------|-----------|---------|
| 결제 응답 속도 | 광고 트래픽에 영향받음 | 독립적, 빠름 |
| DB locked 에러 | 트래픽 증가 시 발생 가능 | 거의 없음 |
| 백업/복구 | impressions 포함하여 느림 | 핵심 DB만 빠르게 처리 |

### 분리 고려 시점

| 지표 | 임계값 |
|------|--------|
| 일일 페이지뷰 | **10,000회 이상** |
| `ad_impressions` 테이블 크기 | **100만 rows 이상** |
| "database is locked" 에러 | **주 1회 이상** |

**현재 트래픽에서는 분리 불필요. 위 임계값 도달 시 분리 검토.**

---

## 백업 권장 명령어

```bash
# 컨테이너 내부에서 백업
docker exec bitcoincash-service sqlite3 /data/payments.db ".backup '/data/payments_backup_$(date +%Y%m%d).db'"

# 호스트로 복사
docker cp bitcoincash-service:/data/payments.db ./backups/payments_$(date +%Y%m%d).db
```

---

## 향후 분리 시 구조 (참고용)

만약 분리가 필요해지면 다음과 같은 구조를 권장:

```
/data/
├── payments.db          # 결제, 크레딧 (핵심)
├── membership.db        # 멤버십 구독
├── uploads.db           # 업로드 쿼터
├── reports.db           # VP/CP 신고 시스템
└── ads.db               # 광고 시스템 (쓰기 빈도 높음)
```

---

## 결론

**현재 상태로 운영을 권장합니다.**

- 정상 작동 중이며, 현재 트래픽 수준에서는 문제없음
- 분리 작업의 위험과 비용이 이득보다 큼
- 백업을 철저히 하고, 트래픽 증가 시 점진적으로 분리 검토

---

## 관련 문서

- [BCH 결제 시스템](/docs/features/bch-payment-system.md)
- [멤버십 시스템](/docs/features/MEMBERSHIP_SYSTEM.md)
- [업로드 쿼터 시스템](/docs/features/UPLOAD_QUOTA_SYSTEM.md)
- [광고 시스템](/docs/features/ADVERTISEMENT_SYSTEM.md)
