# 📚 프로젝트 문서 관리 가이드

## 🎯 목적
Rust-Lemmy + BCH Payment 프로젝트의 기술 문서들을 체계적으로 관리하기 위한 가이드

## 📁 권장 디렉토리 구조

```
/opt/khankorean/oratio/
├── docs/                           # 📚 모든 문서 통합 관리
│   ├── deployment/                 # 🚀 배포 관련
│   │   ├── production-setup.md     # 프로덕션 배포 가이드
│   │   ├── domain-migration.md     # 도메인 변경 기록
│   │   └── ssl-setup.md           # SSL 인증서 설정
│   ├── troubleshooting/           # 🔧 문제 해결
│   │   ├── docker-restart-fix.md  # Docker 재시작 문제
│   │   ├── electron-cash-fix.md   # ElectronCash 연결 문제
│   │   ├── email-setup-fix.md     # 이메일 인증 문제
│   │   └── ui-thumbnail-fix.md    # UI 썸네일 문제
│   ├── features/                  # ✨ 기능 개발
│   │   ├── bch-payment-system.md  # BCH 결제 시스템
│   │   ├── email-verification.md  # 이메일 인증 시스템
│   │   └── ui-improvements.md     # UI/UX 개선사항
│   ├── technical/                 # 🔬 기술 분석
│   │   ├── api-documentation.md   # API 문서
│   │   ├── database-schema.md     # 데이터베이스 구조
│   │   └── security-analysis.md   # 보안 분석
│   └── archive/                   # 📦 해결된 문제들
│       ├── resolved-issues/       # 해결된 이슈들
│       └── deprecated/            # 더 이상 사용하지 않는 문서
└── logs/                          # 🗂️ 로그 파일들 (임시)
    ├── current/                   # 현재 진행 중인 로그
    └── archive/                   # 오래된 로그들
```

## 🏷️ 파일 네이밍 규칙

### 📝 **문서 종류별 네이밍**

1. **기능 개발 문서**
   ```
   {feature-name}-{type}.md
   예: bch-payment-implementation.md
      email-verification-setup.md
   ```

2. **문제 해결 문서**
   ```
   {problem-area}-fix-{date}.md
   예: docker-restart-fix-2025-07.md
      electron-cash-connection-fix-2025-08.md
   ```

3. **배포/설정 문서**
   ```
   {environment}-{purpose}.md
   예: production-deployment.md
      development-setup.md
   ```

4. **기술 분석 문서**
   ```
   {component}-{analysis-type}.md
   예: api-security-analysis.md
      database-performance-analysis.md
   ```

### 🗓️ **날짜 표기법**
- 연월 형식: `YYYY-MM` (예: 2025-08)
- 연월일 형식: `YYYY-MM-DD` (세부 버전 관리 시)

### 📊 **버전 관리**
- 메이저 업데이트: `v2-feature-name.md`
- 마이너 업데이트: 파일 내 버전 히스토리 섹션 추가

## 🧹 현재 파일 정리 방안

### ✅ **즉시 삭제 가능**
```bash
# 빈 파일 삭제
rm /opt/khankorean/oratio/RESEND_SETUP.md

# 오래된 로그 파일 아카이브
mkdir -p /opt/khankorean/oratio/logs/archive
mv /opt/khankorean/oratio/electron-cash-logs.txt /opt/khankorean/oratio/logs/archive/
```

### 🔄 **통합 및 재구성**
1. **배포 관련 문서 통합**
   - `DOMAIN_CHANGES_SUMMARY.md` + `README_DEPLOYMENT.md` → `docs/deployment/production-setup.md`

2. **문제 해결 문서 정리**
   - `restartingISSUE.md` + `TECHNICAL_SUMMARY.md` → `docs/troubleshooting/docker-restart-fix.md`
   - `ELECTRON_CASH_CONNECTION_ERROR_REPORT.txt` → `docs/troubleshooting/electron-cash-fix.md`

3. **기능 문서 분리**
   - `EMAIL_VERIFICATION_GUIDE.md` → `docs/features/email-verification.md`
   - `bitcoincash_service/TECHNICAL_REPORT.md` → `docs/features/bch-payment-system.md`

### 📦 **아카이브 처리**
```bash
# 해결된 문제들을 아카이브로 이동
mkdir -p /opt/khankorean/oratio/docs/archive/resolved-issues
mv /opt/khankorean/oratio/lemmy_thumbnail_fix_summary.txt /opt/khankorean/oratio/docs/archive/resolved-issues/
```

## 📋 문서 템플릿

### 🔧 **문제 해결 문서 템플릿**
```markdown
# {문제명} 해결 가이드

## 📋 문제 개요
- **발생일**: YYYY-MM-DD
- **영향 범위**: 
- **심각도**: [낮음/중간/높음/치명적]

## 🔍 증상
- 구체적인 오류 메시지
- 재현 단계

## 🛠️ 해결 과정
### 1단계: 원인 분석
### 2단계: 해결 방법 적용
### 3단계: 검증

## ✅ 최종 해결책
```

### ✨ **기능 개발 문서 템플릿**
```markdown
# {기능명} 구현 문서

## 🎯 목표
## 🏗️ 아키텍처
## 🔧 구현 세부사항
## 🧪 테스트
## 📊 성능 지표
## 🔄 향후 개선사항
```

## 📝 문서 작성 가이드라인

### ✅ **DO - 해야 할 것들**
1. **명확한 제목과 날짜** 기록
2. **문제-원인-해결-검증** 순서로 구조화
3. **코드 블록과 명령어** 정확히 기록
4. **스크린샷이나 로그** 필요시 첨부
5. **관련 파일 경로** 명시
6. **향후 예방 방법** 제안

### ❌ **DON'T - 하지 말아야 할 것들**
1. **중복 문서** 생성하지 않기
2. **해결되지 않은 상태**로 문서 작성하지 않기
3. **개인적인 메모**는 별도 관리
4. **임시 파일**을 문서 디렉토리에 두지 않기

## 🔄 정기 관리 프로세스

### 📅 **월별 정리** (매월 말)
1. 해결된 문제 문서들을 archive로 이동
2. 중복 문서 확인 및 통합
3. 오래된 로그 파일 정리

### 📅 **분기별 검토** (3개월마다)
1. 문서 구조 개선 필요성 검토
2. 템플릿 업데이트
3. 네이밍 규칙 준수 확인

## 🛠️ 도구 및 자동화

### 📝 **문서 생성 스크립트**
```bash
#!/bin/bash
# create_doc.sh - 새 문서 생성 스크립트

TYPE=$1  # feature, troubleshooting, deployment, technical
NAME=$2
DATE=$(date +%Y-%m)

case $TYPE in
    "feature")
        DIR="docs/features"
        TEMPLATE="feature-template.md"
        ;;
    "troubleshooting")
        DIR="docs/troubleshooting"
        TEMPLATE="troubleshooting-template.md"
        ;;
    *)
        echo "지원되는 타입: feature, troubleshooting, deployment, technical"
        exit 1
        ;;
esac

cp templates/$TEMPLATE $DIR/${NAME}-${DATE}.md
echo "문서 생성됨: $DIR/${NAME}-${DATE}.md"
```

### 🔍 **중복 문서 검색**
```bash
# 중복 가능성이 있는 문서들 찾기
find docs/ -name "*.md" -exec basename {} \; | sort | uniq -d
```

## 📚 권장 도구

### 📝 **문서 편집**
- **VS Code**: Markdown 미리보기 지원
- **Typora**: WYSIWYG Markdown 에디터
- **Obsidian**: 문서 간 링크 관리

### 🔗 **버전 관리**
- Git을 통한 문서 히스토리 관리
- 중요 변경사항은 커밋 메시지에 상세 기록

### 📊 **문서 품질 관리**
- Markdown linter 사용
- 링크 유효성 검사
- 맞춤법 검사

---

## 📞 문의 및 개선 제안

문서 관리 방식에 대한 개선 제안이나 질문이 있으시면 이슈로 등록해 주세요.

**마지막 업데이트**: 2025-09-07
**버전**: v1.0
