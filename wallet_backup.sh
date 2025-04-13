#!/bin/bash
# wallet_backup.sh - BitcoinCash 지갑 및 결제 데이터 백업 스크립트

# 설정
BACKUP_DIR="/srv/lemmy/defadb.com/backups"
ELECTRON_CASH_DATA="/srv/lemmy/defadb.com/data/electron-cash"
PAYMENT_DATA="/srv/lemmy/defadb.com/data/bitcoincash"
DATE=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/bch_wallet_backup_$DATE.tar.gz"
LOG_FILE="$BACKUP_DIR/backup_log.txt"
GPG_KEY="YOUR_GPG_KEY_ID"  # 암호화에 사용할 GPG 키 ID

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"

echo "$(date): 백업 시작" >> "$LOG_FILE"

# 컨테이너 중지 (옵션)
# docker-compose -f /srv/lemmy/defadb.com/docker-compose.yml stop electron-cash bitcoincash-service

# 데이터 백업
echo "지갑 및 결제 데이터 백업 중..." >> "$LOG_FILE"
tar -czf "$BACKUP_FILE" "$ELECTRON_CASH_DATA" "$PAYMENT_DATA"

# GPG로 백업 파일 암호화 (선택사항)
if [ ! -z "$GPG_KEY" ]; then
    echo "백업 파일 암호화 중..." >> "$LOG_FILE"
    gpg --encrypt --recipient "$GPG_KEY" "$BACKUP_FILE"
    rm "$BACKUP_FILE"  # 암호화되지 않은 파일 삭제
    BACKUP_FILE="$BACKUP_FILE.gpg"
fi

# 백업 완료 메시지
echo "$(date): 백업 완료. 파일: $BACKUP_FILE" >> "$LOG_FILE"

# 컨테이너 재시작 (옵션)
# docker-compose -f /srv/lemmy/defadb.com/docker-compose.yml start electron-cash bitcoincash-service

# 오래된 백업 파일 삭제 (30일 이상)
find "$BACKUP_DIR" -name "bch_wallet_backup_*.tar.gz*" -type f -mtime +30 -delete

# 오프사이트 백업 (옵션)
# 예: 안전한 외부 서버로 백업 파일 전송
# scp "$BACKUP_FILE" backup_user@remote_server:/path/to/backup/