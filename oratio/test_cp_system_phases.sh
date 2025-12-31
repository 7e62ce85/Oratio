#!/bin/bash
# CP Moderation System - Phase별 구현 상태 검증 스크립트

echo "======================================================================="
echo "    CP MODERATION SYSTEM - 구현 상태 간접 테스트"
echo "======================================================================="
echo ""

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 체크 함수
check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✅${NC} $2"
        return 0
    else
        echo -e "${RED}❌${NC} $2"
        return 1
    fi
}

check_function() {
    if grep -q "$1" "$2" 2>/dev/null; then
        echo -e "${GREEN}✅${NC} $3"
        return 0
    else
        echo -e "${RED}❌${NC} $3"
        return 1
    fi
}

check_db_table() {
    if docker exec bitcoincash-service sqlite3 /data/payments.db ".schema $1" | grep -q "CREATE TABLE"; then
        echo -e "${GREEN}✅${NC} DB Table: $1"
        return 0
    else
        echo -e "${RED}❌${NC} DB Table: $1"
        return 1
    fi
}

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 1: REPORTING${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "📱 Frontend Components:"
check_file "lemmy-ui-custom/src/shared/utils/cp-moderation.ts" "  CP Moderation Utils"
check_function "submitCPReport" "lemmy-ui-custom/src/shared/utils/cp-moderation.ts" "  submitCPReport() function"
check_function "getReportedContentIds" "lemmy-ui-custom/src/shared/utils/cp-moderation.ts" "  getReportedContentIds() function"

echo ""
echo "🔧 Backend API:"
check_function "@cp_bp.route('/report'" "oratio/bitcoincash_service/routes/cp.py" "  POST /api/cp/report"
check_function "@cp_bp.route('/reported-content-ids'" "oratio/bitcoincash_service/routes/cp.py" "  GET /api/cp/reported-content-ids"
check_function "def create_cp_report" "oratio/bitcoincash_service/services/cp_moderation.py" "  create_cp_report() service"

echo ""
echo "💾 Database:"
check_db_table "cp_reports"
check_db_table "user_cp_permissions"

# CP reports 개수 확인
REPORT_COUNT=$(docker exec bitcoincash-service sqlite3 /data/payments.db "SELECT COUNT(*) FROM cp_reports;" 2>/dev/null)
if [ ! -z "$REPORT_COUNT" ]; then
    echo -e "${GREEN}✅${NC} CP Reports in DB: ${YELLOW}${REPORT_COUNT}${NC}"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 2: MODERATOR REVIEW${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "📱 Frontend Components:"
check_file "lemmy-ui-custom/src/shared/components/cp/moderator-review-panel.tsx" "  Moderator Review Panel"
check_function "getPendingReports" "lemmy-ui-custom/src/shared/utils/cp-moderation.ts" "  getPendingReports() function"
check_function "reviewCPReport" "lemmy-ui-custom/src/shared/utils/cp-moderation.ts" "  reviewCPReport() function"

echo ""
echo "🔧 Backend API:"
check_function "@cp_bp.route('/reports/pending'" "oratio/bitcoincash_service/routes/cp.py" "  GET /api/cp/reports/pending"
check_function "@cp_bp.route('/report/<report_id>/review'" "oratio/bitcoincash_service/routes/cp.py" "  POST /api/cp/report/<id>/review"
check_function "def review_cp_report" "oratio/bitcoincash_service/services/cp_moderation.py" "  review_cp_report() service"

echo ""
echo "💾 Database:"
check_db_table "cp_reviews"

echo ""
echo "🔍 Review Logic Check:"
check_function "REVIEW_DECISION_CP_CONFIRMED" "oratio/bitcoincash_service/services/cp_moderation.py" "  CP Confirmed Decision"
check_function "REVIEW_DECISION_NOT_CP" "oratio/bitcoincash_service/services/cp_moderation.py" "  Not CP Decision"
check_function "ban_user" "oratio/bitcoincash_service/services/cp_moderation.py" "  ban_user() function"
check_function "revoke_report_ability" "oratio/bitcoincash_service/services/cp_moderation.py" "  revoke_report_ability() function"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 3: RE-REPORTING & ESCALATION${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "🔍 Re-reporting Logic:"
check_function "check_existing_report" "oratio/bitcoincash_service/services/cp_moderation.py" "  check_existing_report() function"
check_function "ESCALATION_MODERATOR" "oratio/bitcoincash_service/services/cp_moderation.py" "  Moderator Escalation Level"
check_function "ESCALATION_ADMIN" "oratio/bitcoincash_service/services/cp_moderation.py" "  Admin Escalation Level"
check_function "reporter_is_member" "oratio/bitcoincash_service/services/cp_moderation.py" "  Membership Check for Re-reporting"

echo ""
echo "📋 Logic Check:"
if grep -q "Free users cannot re-report content approved by moderators" "oratio/bitcoincash_service/services/cp_moderation.py"; then
    echo -e "${GREEN}✅${NC} Free user re-report blocking"
fi
if grep -q "Content approved by admin cannot be reported again" "oratio/bitcoincash_service/services/cp_moderation.py"; then
    echo -e "${GREEN}✅${NC} Admin-approved content protection"
fi

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 4: ADMIN PANEL${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "📱 Frontend Components:"
check_file "lemmy-ui-custom/src/shared/components/cp/admin-control-panel.tsx" "  Admin Control Panel"

echo ""
echo "🔧 Backend API:"
check_function "@cp_bp.route('/admin/user/<user_id>/ban'" "oratio/bitcoincash_service/routes/cp.py" "  POST /api/cp/admin/user/<id>/ban"
check_function "@cp_bp.route('/admin/user/<user_id>/unban'" "oratio/bitcoincash_service/routes/cp.py" "  POST /api/cp/admin/user/<id>/unban"
check_function "@cp_bp.route('/admin/user/<user_id>/revoke-report'" "oratio/bitcoincash_service/routes/cp.py" "  POST /api/cp/admin/user/<id>/revoke-report"
check_function "@cp_bp.route('/admin/user/<user_id>/restore'" "oratio/bitcoincash_service/routes/cp.py" "  POST /api/cp/admin/user/<id>/restore"

echo ""
echo "🔍 Admin Functions:"
check_function "def restore_user_privileges" "oratio/bitcoincash_service/services/cp_moderation.py" "  restore_user_privileges() service"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}PHASE 5: APPEALS SYSTEM${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "📱 Frontend Components:"
check_file "lemmy-ui-custom/src/shared/components/cp/appeal-form.tsx" "  Appeal Form"
check_function "submitCPAppeal" "lemmy-ui-custom/src/shared/utils/cp-moderation.ts" "  submitCPAppeal() function"

echo ""
echo "🔧 Backend API:"
check_function "@cp_bp.route('/appeal'" "oratio/bitcoincash_service/routes/cp.py" "  POST /api/cp/appeal"
check_function "@cp_bp.route('/appeal/<appeal_id>/review'" "oratio/bitcoincash_service/routes/cp.py" "  POST /api/cp/appeal/<id>/review"

echo ""
echo "💾 Database:"
check_db_table "cp_appeals"

echo ""
echo "🔍 Appeal Logic:"
check_function "def create_appeal" "oratio/bitcoincash_service/services/cp_moderation.py" "  create_appeal() service"
check_function "def review_appeal" "oratio/bitcoincash_service/services/cp_moderation.py" "  review_appeal() service"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}BACKGROUND TASKS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

check_function "def run_cp_background_tasks" "oratio/bitcoincash_service/services/cp_moderation.py" "  Background Task Runner"
check_function "def unban_expired_users" "oratio/bitcoincash_service/services/cp_moderation.py" "  Auto-Unban Function"
check_function "def auto_delete_pending_reports" "oratio/bitcoincash_service/services/cp_moderation.py" "  Auto-Delete Reports Function"

echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}AUDIT & NOTIFICATIONS${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "💾 Database:"
check_db_table "cp_audit_log"
check_db_table "cp_notifications"

echo ""
echo "🔍 Notification Functions:"
check_function "def create_notification" "oratio/bitcoincash_service/services/cp_moderation.py" "  create_notification() service"
check_function "def notify_community_moderators" "oratio/bitcoincash_service/services/cp_moderation.py" "  notify_community_moderators() function"
check_function "def log_audit" "oratio/bitcoincash_service/services/cp_moderation.py" "  log_audit() function"

echo ""
echo "======================================================================="
echo -e "${GREEN}테스트 완료!${NC}"
echo "======================================================================="
echo ""
echo -e "${YELLOW}📌 다음 단계:${NC}"
echo "   1. lemmy-ui 재빌드: cd oratio && docker-compose up -d --build lemmy-ui"
echo "   2. Moderator 계정으로 /cp/moderator-review 접속"
echo "   3. Pending reports 확인 및 review 테스트"
echo "   4. Admin 계정으로 /cp/admin-panel 접속"
echo "   5. Appeals 기능 테스트"
echo ""
