# Oratio 서버 운영 계획

> **작성일**: 2026-04-03 | **기준 데이터**: 실서버 실측 (2026-04-03)

---

## 📊 현재 서버 현황

### 하드웨어

| 항목 | 스펙 |
|------|------|
| RAM | 91.9 GiB |
| 디스크 | 500.1 GB NVMe (정리 후 407 GB 가용) |
| 가동시간 | 143일+ (안정) |
| Swap | 미설정 |

### 서비스 구성 (Docker 12개 컨테이너)

| 컨테이너 | 메모리 | 역할 |
|-----------|--------|------|
| lemmy (백엔드) | 399 MiB | Rust 포럼 엔진 |
| lemmy-ui (프론트) | 164 MiB | Node.js SSR |
| postgres | 167 MiB | DB |
| proxy (nginx) | 54 MiB | 리버스 프록시 + SSL |
| content-importer | 75 MiB | 자동 콘텐츠 수집 봇 |
| electron-cash | 54 MiB (2 GiB 제한) | BCH 결제 |
| bitcoincash-service | 44 MiB | BCH API |
| pictrs | 42 MiB | 이미지 호스팅 |
| pow-validator | 58 MiB | PoW 캡차 |
| email-service | 26 MiB | 이메일 발송 |
| postfix | 5 MiB | SMTP |
| certbot | 6 MiB | SSL 인증서 |
| **합계** | **≈ 1.1 GiB (1.16%)** | RAM 91.9 GiB 중 |

### DB 실측 (2026-04-03)

| 항목 | 수치 |
|------|------|
| 전체 DB 크기 | 41 MB |
| 포스트 (활성 / 소프트삭제 / DB 전체) | 265 / 437 / 702건 (평균 1,224 bytes/건) |
| 댓글 (활성 / 소프트삭제 / DB 전체) | 484 / 197 / 681건 (평균 341 bytes/건) |
| 유저 | 18명 |
| 커뮤니티 | 27개 |
| 포스트당 평균 댓글 수 | 1.83개 (활성 기준: 484 / 265) |

---

## 📈 수용 한계 추정

### 포스트/댓글 (메모리 기준)

포스트 1건(댓글 포함) 평균 비용 ≈ **4.7 KB** (행 + 인덱스 + aggregates + 댓글)

| 시나리오 | DB 크기 | 포스트 수 | 댓글 수 |
|----------|---------|-----------|---------|
| **현재** | **41 MB** | **702** | **681** |
| DB 4 GB | 4 GB | ~85만 | ~82만 |
| DB 20 GB | 20 GB | ~430만 | ~417만 |
| 이론 한계 (RAM 전부 투입) | 67 GB | ~1,400만 | ~1,360만 |

**현재 702건은 이론 한계의 0.005%.** 수백만 건까지 문제없음.

### 동시접속자 (RAM 기준)

유저 1명당 메모리: ~10–25 MB (백엔드 + DB 커넥션 + SSR + 프록시)

| 유저당 메모리 | 동시접속 가능 수 |
|--------------|----------------|
| 25 MB (보수적) | ~820명 |
| 15 MB (현실적) | ~1,370명 |
| 10 MB (낙관적) | ~2,050명 |

---

## 🎯 단계별 운영 계획

### Phase 1: 현재 — 소규모 (유저 ~100명, 포스트 ~5,000건)

**현 상태 유지. 추가 인프라 불필요.**

- [ ] Docker 빌드 후 `docker image prune -f` 습관화
- [ ] 월 1회 `docker builder prune -a -f` 실행
- [x] Swap 8 GiB 설정 (안전망) ✅ 2026-04-03 완료

```bash
# Swap 설정 (1회)
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### Phase 2: 성장기 (유저 ~1,000명, 포스트 ~50,000건)

**DB 튜닝 필요. 서버 스펙 변경 불필요.**

- [ ] PostgreSQL `shared_buffers` → 4 GB (현재 기본 128 MB)
- [ ] PostgreSQL `work_mem` → 64 MB
- [ ] PostgreSQL `effective_cache_size` → 48 GB
- [ ] pictrs 이미지 → 외부 스토리지 or CDN 검토
- [ ] nginx 캐싱 활성화 (정적 자산 + API 응답)
- [ ] 로그 로테이션 자동화

```conf
# customPostgresql.conf 수정
shared_buffers = 4GB
work_mem = 64MB
effective_cache_size = 48GB
maintenance_work_mem = 1GB
```

### Phase 3: 활성기 (유저 ~10,000명, 포스트 ~500,000건)

**캐시 레이어 도입.**

- [ ] Redis 캐시 추가 (세션, 핫 포스트)
- [ ] CDN 도입 (이미지/정적 파일)
- [ ] DB 읽기 전용 복제본 검토
- [ ] 모니터링 도구 도입 (Prometheus + Grafana or Netdata)
- [ ] 자동 백업 스크립트 (DB 일일 덤프 + 외부 저장) — ⚡ DB 덤프는 Phase 1에서 완료, 외부 저장만 남음

### Phase 4: 대규모 (유저 ~50,000명+, 포스트 ~수백만건)

**서버 증설 또는 분리 필요.**

- [ ] DB 전용 서버 분리
- [ ] 로드밸런서 도입 (여러 백엔드 인스턴스)
- [ ] 전문 검색 엔진 (PostgreSQL FTS → Elasticsearch/Meilisearch)
- [ ] 오브젝트 스토리지 (S3 호환) for pictrs

---

## 🛡️ 정기 유지보수 체크리스트

### 주간

```bash
# 디스크 상태
df -h /

# 컨테이너 메모리
docker stats --no-stream

# DB 크기
cd /home/user/Oratio/oratio
docker-compose exec -T postgres psql -U lemmy -d lemmy -c \
  "SELECT pg_size_pretty(pg_database_size('lemmy'));"
```

### 월간

```bash
# Docker 쓰레기 정리
docker image prune -f
docker builder prune -a -f
docker volume prune -f

# DB vacuum
docker-compose exec -T postgres psql -U lemmy -d lemmy -c "VACUUM ANALYZE;"

# 로그 크기 확인
du -sh /home/user/Oratio/oratio/logs/
```

### 분기

- DB 풀 백업 + 외부 저장
- SSL 인증서 갱신 확인
- Docker 이미지 보안 업데이트 확인
- 디스크 SMART 상태 점검

---

## ⚠️ 알려진 리스크 & 대응

| 리스크 | 심각도 | 대응 |
|--------|--------|------|
| 디스크 재포화 (빌드 캐시) | 🔴 높음 | 빌드 후 prune 필수. 월간 체크 |
| Electron Cash 메모리 폭주 | 🟡 중간 | 2 GiB 제한 설정됨. health_check 크론 유지 |
| Swap 미설정 | ~~🟡 중간~~ ✅ 해결 | 8 GiB Swap 설정 완료 (2026-04-03) |
| DB 백업 없음 | ~~🔴 높음~~ ✅ 해결 | pg_dump 자동화 완료 (매일 3:10 AM, 7일 보관) |
| 단일 서버 (SPOF) | 🟡 중간 | Phase 3까지는 허용. 이후 이중화 |

---

## 📋 요약

| 지표 | 현재 | 안전 한계 | 비고 |
|------|------|-----------|------|
| **RAM 사용** | 1.1 GiB / 91.9 GiB | ~70 GiB | 여유 98% |
| **디스크** | 27 GB / 457 GB | ~400 GB | 정리 후 여유 93% |
| **포스트** | 702건 | 수백만 건 | DB 튜닝 후 |
| **동시접속** | ~18명 | 800~2,000명 | 현 설정 기준 |
| **다음 조치** | — | Docker prune 습관화 | Phase 1 나머지 |
