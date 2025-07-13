# Lemmy with Bitcoin Cash Payment Integration

This project implements a **Lemmy** community platform with **Bitcoin Cash (BCH) Payment Integration** using Electron Cash wallet. Running in Docker containers, the system provides a complete solution for accepting BCH payments within a Lemmy forum installation, with **Nginx** configured as a reverse proxy with SSL (Let's Encrypt).

## Table of Contents

- [Project Overview](#project-overview)
- [System Architecture](#system-architecture)
- [Features](#features)
- [UI Integration](#ui-integration)
- [Installation and Configuration](#installation-and-configuration)
  - [1. Prerequisites](#1-prerequisites)
  - [2. Setup Instructions](#2-setup-instructions)
  - [3. Configuration Options](#3-configuration-options)
- [Components](#components)
  - [1. Lemmy Core](#1-lemmy-core)
  - [2. Bitcoin Cash Payment Service](#2-bitcoin-cash-payment-service)
  - [3. Electron Cash Integration](#3-electron-cash-integration)
  - [4. Nginx Configuration](#4-nginx-configuration)
- [Database Structure](#database-structure)
- [API Endpoints](#api-endpoints)
- [Payment Processing Flow](#payment-processing-flow)
- [Backup and Maintenance](#backup-and-maintenance)
- [Security Considerations](#security-considerations)
- [Environment Variables Configuration](#environment-variables-configuration)
- [Troubleshooting](#troubleshooting)
- [Technical Notes](#technical-notes)
- [Future Improvements](#future-improvements)
- [Development Workflow](#development-workflow)

---

## Project Overview

This project integrates Bitcoin Cash payments with the Lemmy community platform, providing:

- **Payment Processing**: Complete BCH payment processing using Electron Cash
- **User Credit Management**: System for tracking user payments and credits
- **Invoice Generation**: Dynamic invoice creation with QR codes
- **Payment Verification**: Automated transaction monitoring and verification
- **Multiple Payment Modes**: Both direct payments and address-specific payments
- **Mock Mode**: Testing environment without actual BCH transactions
- **UI Integration**: Seamless integration with Lemmy's user interface

The implementation uses Flask (Python) for the payment service and integrates with the Rust-based Lemmy platform through a custom UI overlay.

---

## System Architecture

The system consists of several interconnected components:

1. **Lemmy** - Core community platform built in Rust
2. **Bitcoin Cash Payment Service** - Flask application for payment processing
3. **Electron Cash Integration** - BCH wallet management and verification
4. **Nginx** - Reverse proxy for the various services
5. **Custom UI Integration** - Modified Lemmy UI with BCH payment features

The components communicate through Docker networking, with the payment service calling the Lemmy API when credits need to be applied.

---

## Features

- **BCH Payment Processing**: Full invoice generation and payment verification
- **QR Code Generation**: For easy mobile payments
- **Transaction Monitoring**: Automatic checking for payment confirmations
- **User Credit System**: Tracking of user credits and transactions
- **Mock Mode**: Test functionality without actual BCH transactions
- **Direct Payment Mode**: Simplified payment handling with centralized wallet
- **Multiple Confirmation Levels**: Configurable confirmation requirements
- **Fault Tolerance**: Handling of network and database connection issues
- **Integrated UI**: Native payment buttons and credit display in Lemmy interface

---

## UI Integration

### BCH Payment Button
- **Location**: Prominently displayed in the main navigation bar
- **Design**: Green-themed button with Bitcoin Cash logo
- **Functionality**: Direct link to payment service for invoice generation
- **Responsive**: Works on both desktop and mobile interfaces

### User Credit Display
- **Location**: User dropdown menu in the navigation bar
- **Real-time Updates**: Automatically fetches and displays current BCH credit balance
- **Korean Language Support**: "보유 크레딧: X BCH" format
- **API Integration**: Secure communication with payment service using API keys

### Environment Variable Handling
- **Build-time Injection**: Environment variables are now properly injected during Docker build
- **Runtime Compatibility**: System works correctly in containerized environments
- **Fallback Support**: Multiple fallback mechanisms for different deployment scenarios

### JavaScript Integration
- **Client-side Configuration**: Dynamic configuration loading through `window.__BCH_CONFIG__`
- **Server-side Rendering**: Proper environment variable handling during SSR
- **Error Handling**: Comprehensive error logging and fallback mechanisms

---

## Installation and Configuration

### 1. Prerequisites

- Docker and Docker Compose
- Domain name with DNS configured
- SSL certificates (Let's Encrypt)
- 1GB+ RAM server (DigitalOcean Droplet or similar)
- Basic knowledge of Bitcoin Cash and Electron Cash

### 2. Setup Instructions

1. **Clone the repository and configure environment variables**:
   - Configure payment wallet address
   - Set up API keys and credentials

2. **Start the services**:
   ```bash
   docker-compose up -d
   ```

3. **Initialize the Electron Cash wallet**:
   - The system will automatically set up the wallet and generate payment addresses

### 3. Configuration Options

The system supports various configuration options through environment variables in the Docker Compose file:

- `MOCK_MODE`: Enable/disable mock payment processing (true/false)
- `TESTNET`: Use BCH testnet instead of mainnet (true/false)
- `DIRECT_MODE`: Enable direct payment handling mode (true/false)
- `MIN_CONFIRMATIONS`: Minimum confirmations required to mark a payment as completed
- `PAYOUT_WALLET`: The BCH address for centralized payments
- `ELECTRON_CASH_URL`: URL for Electron Cash RPC service
- `LEMMY_API_URL`: URL for Lemmy API
- `FORWARD_PAYMENTS`: Enable automatic forwarding of received funds to payout wallet

---

## Components

### 1. Lemmy Core

- Standard Lemmy installation using Docker containers
- Community platform with posts, comments, and user interactions
- Version 0.19.8 of Lemmy and Lemmy-UI with custom BCH integration
- PostgreSQL database for storing forum data
- Pictrs service for image handling

### 2. Bitcoin Cash Payment Service

- Flask-based API service for handling BCH payments
- Features:
  - Invoice generation and management
  - Payment verification and transaction monitoring
  - User credit management
  - QR code generation for mobile payments
  - Integration with Lemmy API for user credit application
  - RESTful API endpoints for UI integration
- Database: SQLite with WAL journaling mode
- Located in `/user/oratio/bitcoincash_service`

### 3. Electron Cash Integration

- Serves as the Bitcoin Cash wallet backend
- Manages:
  - Address generation
  - Balance checking
  - Transaction verification
  - Payment forwarding
- RPC interface for the payment service
- Wallet data stored in `/user/oratio/data/electron_cash`

### 4. Nginx Configuration

- Reverse proxy for both Lemmy and the payment service
- SSL termination with Let's Encrypt certificates
- Configuration for handling both HTTP and HTTPS traffic
- Static file serving for BCH UI assets
- Located in `/user/oratio/nginx`

---

## Database Structure

The payment service uses SQLite with the following tables:

- **invoices**: Stores payment invoices and their statuses
  - Fields: id, payment_address, amount, status, created_at, expires_at, paid_at, user_id, tx_hash, confirmations

- **addresses**: Tracks BCH addresses generated for payments
  - Fields: address, created_at, used

- **user_credits**: Manages user credit balances
  - Fields: user_id, credit_balance, last_updated

- **transactions**: Records all transaction history
  - Fields: id, user_id, amount, type, description, created_at, invoice_id

---

## API Endpoints

### Payment Service API

- **/generate_invoice**: Create a new payment invoice
  - Parameters: amount, user_id
  - Returns: Invoice details with payment address

- **/invoice/<invoice_id>**: View invoice details
  - Shows QR code and payment status

- **/check_payment/<invoice_id>**: Check payment status
  - Returns current status of the invoice: pending, paid, completed, expired

- **/api/user_credit/<user_id>**: Get user credit balance
  - Requires API key authentication
  - Used by UI for real-time credit display

- **/api/transactions/<user_id>**: Get user transaction history
  - Requires API key authentication

- **/health**: Service health check endpoint

### UI Integration Endpoints

- **BCH Configuration**: Dynamic configuration injection for client-side scripts
- **Credit Updates**: Real-time credit balance retrieval
- **Payment Status**: Live payment status updates for active invoices

---

## Payment Processing Flow

1. **Invoice Creation**:
   - User requests an invoice with an amount
   - System generates a unique BCH address (or uses direct payment address)
   - QR code is generated for easy mobile payment

2. **Payment Monitoring**:
   - Background service checks for incoming payments
   - For each pending invoice, the system checks the address balance
   - When a payment is detected, the transaction is verified

3. **Confirmation Process**:
   - System monitors confirmations for each transaction
   - When minimum confirmations are reached, payment is marked as complete
   - User credits are added to their account

4. **Credit Application**:
   - User credits are applied within the Lemmy system
   - Transaction records are maintained for auditing

5. **Optional Forwarding**:
   - If enabled, received funds are automatically forwarded to a central wallet
   - Helps with wallet management and security

---

## Backup and Maintenance

### Wallet Backup

The system includes a wallet backup script (`wallet_backup.sh`) that should be run regularly to back up the Electron Cash wallet data. Key files to back up include:

- `/srv/lemmy/defadb.com/data/electron_cash/wallets`
- `/srv/lemmy/defadb.com/data/electron_cash/seed.txt`
- `/srv/lemmy/defadb.com/data/bitcoincash/payments.db`

### Transaction Monitoring

A background process continuously monitors transactions and updates payment statuses automatically. This runs within the Bitcoin Cash Payment Service container.

### Database Maintenance

The SQLite database uses WAL journaling mode for better performance and reliability. Regular checkpoints occur automatically, but manual vacuuming may be needed occasionally for optimal performance.

---

## Security Considerations

- **Wallet Security**: The Electron Cash wallet requires secure credential management
- **API Authentication**: API keys protect sensitive endpoints
- **Transaction Forwarding**: The system can automatically move funds to a designated payout wallet
- **SSL/TLS**: All connections are secured with SSL/TLS through Nginx
- **Database Security**: The SQLite database uses proper locking and foreign key constraints
- **Error Handling**: Comprehensive error handling prevents information leakage
- **Network Isolation**: Docker networking isolates services appropriately

---

## Environment Variables Configuration

### Docker Build Configuration

The system now properly handles environment variables during both build and runtime:

```dockerfile
# Build-time environment variables
ARG LEMMY_API_KEY
ARG LEMMY_BCH_PAYMENT_URL
ARG LEMMY_BCH_API_URL

# Runtime environment variables
ENV LEMMY_API_KEY=${LEMMY_API_KEY}
ENV LEMMY_BCH_PAYMENT_URL=${LEMMY_BCH_PAYMENT_URL}
ENV LEMMY_BCH_API_URL=${LEMMY_BCH_API_URL}
```

### Docker Compose Setup

```yaml
services:
  lemmy-ui:
    build:
      context: ./user/lemmy-ui-custom/
      args:
        LEMMY_API_KEY: ${LEMMY_API_KEY}
        LEMMY_BCH_PAYMENT_URL: ${BCH_PAYMENT_URL}
        LEMMY_BCH_API_URL: ${BCH_API_URL}
    environment:
      - LEMMY_API_KEY=${LEMMY_API_KEY}
      - LEMMY_BCH_PAYMENT_URL=${BCH_PAYMENT_URL}
      - LEMMY_BCH_API_URL=${BCH_API_URL}
```

### Key Environment Variables

- `LEMMY_API_KEY`: API key for secure communication between UI and payment service
- `LEMMY_BCH_PAYMENT_URL`: URL for the payment service interface
- `LEMMY_BCH_API_URL`: API endpoint for user credit queries
- `MOCK_MODE`: Enable/disable mock payment processing
- `DIRECT_MODE`: Enable direct payment handling mode
- `MIN_CONFIRMATIONS`: Minimum confirmations required
- `PAYOUT_WALLET`: Central BCH address for payments

---

## Troubleshooting

### Common Issues

- **Environment Variable Problems**: 
  - Issue: UI shows "undefined" for BCH configuration
  - Solution: Rebuild Docker images with proper build args
  - Command: `docker-compose build --no-cache lemmy-ui`

- **Credit Display Issues**:
  - Issue: User credits not showing in dropdown
  - Solution: Check API key configuration and network connectivity
  - Debug: Check browser console for API errors

- **Payment Button Missing**:
  - Issue: BCH button not visible in navigation
  - Solution: Verify JavaScript integration and environment variables
  - Fallback: Floating button appears as backup

- **Connection Problems**: If the Electron Cash RPC service is unreachable, check network settings and credentials
- **Database Locking**: During high concurrency, the SQLite database may experience locking issues
- **Transaction Confirmations**: BCH network congestion can delay transaction confirmations

### Logs

- Main logs are available in the `logs` directory
- Electron Cash logs are in `electron-cash-logs.txt`
- Bitcoin Cash service logs are in `bitcoincash_service/bch_payment.log`
- UI integration logs available in browser console

### Diagnostic Commands

For debugging, you can use these commands:

```bash
# Check Bitcoin Cash service logs
docker-compose logs bitcoincash-service

# Check UI container logs
docker-compose logs lemmy-ui

# Test BCH configuration
docker-compose exec lemmy-ui printenv | grep BCH

# Test API connectivity
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8081/api/user_credit/1
```

---

## Technical Notes

- The system is designed to handle network interruptions gracefully
- The direct payment handler provides fallback capabilities when Electron Cash is unavailable
- Database operations use proper locking and timeout handling
- External APIs are used as fallbacks for transaction verification
- Environment variables are properly injected at both build and runtime
- UI integration uses modern JavaScript patterns with fallback support
- Real-time credit updates use secure API communication
- Transaction monitoring occurs in a background thread to avoid blocking the main application

### Recent Improvements (2025)

- **Webpack Configuration**: Proper environment variable injection during build process
- **Docker Integration**: Build-time and runtime environment variable handling
- **UI Components**: Native React/Inferno components for BCH integration
- **API Security**: Enhanced API key authentication for UI-service communication
- **Error Handling**: Comprehensive error logging and user feedback
- **Responsive Design**: Mobile-friendly payment interfaces

---

## Future Improvements

Potential enhancements to consider:

- **Multi-wallet Support**: Implement multiple wallets for better scaling
- **Enhanced Analytics**: Add detailed reporting on payment patterns
- **Additional Cryptocurrencies**: Extend beyond BCH to other coins
- **Advanced Verification**: Implement additional payment verification methods
- **User Interface Improvements**: Create a more comprehensive admin dashboard
- **Performance Optimization**: Further optimize database operations for higher throughput
- **Mobile App Integration**: Native mobile app payment support
- **Advanced Credit System**: Implement credit expiration and usage tracking
- **Multi-language Support**: Expand beyond Korean to other languages

---

## Development Workflow

### Git Version Control

This project uses Git for version control. The repository is configured to ignore sensitive files like `.env`, wallet data, and database files through the `.gitignore` file.

### Standard Development Flow

1. **Make changes to your files**
   - Implement features or bug fixes

2. **Stage your changes**
   ```bash
   git add .
   ```
   - This stages all modified files except those ignored by `.gitignore`

3. **Commit your changes**
   ```bash
   git commit -m "Description of changes"
   ```
   - Use clear, descriptive commit messages

4. **Push to the remote repository**
   ```bash
   git push origin main
   ```
   - Replace `main` with your branch name if working on a different branch

### Sensitive Files

The following types of files are excluded from version control for security reasons:
- Environment variables (`.env`, `*.env`)
- Wallet data and seed phrases
- Password files
- Database files
- Certificates and keys
- Log files

### Adding New Files to Ignore

If you need to add more files to ignore, update the `.gitignore` file:
```bash
echo "pattern_to_ignore" >> .gitignore
git add .gitignore
git commit -m "Update .gitignore to exclude new pattern"
```

/////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////
/////////////////////////////////////////////////////////////////////////////////////////

# Lemmy와 Bitcoin Cash 결제 통합 시스템

이 프로젝트는 Electron Cash 지갑을 사용하여 **Bitcoin Cash (BCH) 결제 통합**이 포함된 **Lemmy** 커뮤니티 플랫폼을 구현합니다. Docker 컨테이너에서 실행되며, Lemmy 포럼 설치 내에서 BCH 결제를 수락하는 완전한 솔루션을 제공하고, SSL(Let's Encrypt)이 포함된 리버스 프록시로 **Nginx**가 구성되어 있습니다.

## 목차

- [프로젝트 개요](#프로젝트-개요)
- [시스템 아키텍처](#시스템-아키텍처)
- [기능](#기능)
- [UI 통합](#ui-통합)
- [설치 및 구성](#설치-및-구성)
  - [1. 사전 요구사항](#1-사전-요구사항)
  - [2. 설정 지침](#2-설정-지침)
  - [3. 구성 옵션](#3-구성-옵션)
- [구성 요소](#구성-요소)
  - [1. Lemmy 코어](#1-lemmy-코어)
  - [2. Bitcoin Cash 결제 서비스](#2-bitcoin-cash-결제-서비스)
  - [3. Electron Cash 통합](#3-electron-cash-통합)
  - [4. Nginx 구성](#4-nginx-구성)
- [데이터베이스 구조](#데이터베이스-구조)
- [API 엔드포인트](#api-엔드포인트)
- [결제 처리 흐름](#결제-처리-흐름)
- [백업 및 유지보수](#백업-및-유지보수)
- [보안 고려사항](#보안-고려사항)
- [환경변수 구성](#환경변수-구성)
- [문제 해결](#문제-해결)
- [기술 노트](#기술-노트)
- [향후 개선사항](#향후-개선사항)
- [개발 워크플로](#개발-워크플로)

---

## 프로젝트 개요

이 프로젝트는 Bitcoin Cash 결제를 Lemmy 커뮤니티 플랫폼과 통합하여 다음을 제공합니다:

- **결제 처리**: Electron Cash를 사용한 완전한 BCH 결제 처리
- **사용자 크레딧 관리**: 사용자 결제 및 크레딧 추적 시스템
- **인보이스 생성**: QR 코드가 포함된 동적 인보이스 생성
- **결제 검증**: 자동화된 거래 모니터링 및 검증
- **다중 결제 모드**: 직접 결제 및 주소별 결제 모두 지원
- **모의 모드**: 실제 BCH 거래 없이 테스트 환경
- **UI 통합**: Lemmy 사용자 인터페이스와의 완벽한 통합

구현은 결제 서비스를 위해 Flask(Python)를 사용하고 사용자 정의 UI 오버레이를 통해 Rust 기반 Lemmy 플랫폼과 통합됩니다.

---

## 시스템 아키텍처

시스템은 여러 상호 연결된 구성 요소로 구성됩니다:

1. **Lemmy** - Rust로 구축된 핵심 커뮤니티 플랫폼
2. **Bitcoin Cash 결제 서비스** - 결제 처리를 위한 Flask 애플리케이션
3. **Electron Cash 통합** - BCH 지갑 관리 및 검증
4. **Nginx** - 다양한 서비스를 위한 리버스 프록시
5. **사용자 정의 UI 통합** - BCH 결제 기능이 포함된 수정된 Lemmy UI

구성 요소들은 Docker 네트워킹을 통해 통신하며, 크레딧이 적용될 때 결제 서비스가 Lemmy API를 호출합니다.

---

## 기능

- **BCH 결제 처리**: 완전한 인보이스 생성 및 결제 검증
- **QR 코드 생성**: 쉬운 모바일 결제를 위한 기능
- **거래 모니터링**: 결제 확인의 자동 확인
- **사용자 크레딧 시스템**: 사용자 크레딧 및 거래 추적
- **모의 모드**: 실제 BCH 거래 없이 기능 테스트
- **직접 결제 모드**: 중앙집중식 지갑을 통한 간소화된 결제 처리
- **다중 확인 레벨**: 구성 가능한 확인 요구사항
- **장애 허용**: 네트워크 및 데이터베이스 연결 문제 처리
- **통합 UI**: Lemmy 인터페이스의 네이티브 결제 버튼 및 크레딧 표시

---

## UI 통합

### BCH 결제 버튼
- **위치**: 메인 네비게이션 바에 눈에 띄게 표시
- **디자인**: Bitcoin Cash 로고가 포함된 녹색 테마 버튼
- **기능**: 인보이스 생성을 위한 결제 서비스 직접 링크
- **반응형**: 데스크톱 및 모바일 인터페이스 모두에서 작동

### 사용자 크레딧 표시
- **위치**: 네비게이션 바의 사용자 드롭다운 메뉴
- **실시간 업데이트**: 현재 BCH 크레딧 잔액을 자동으로 가져와 표시
- **한국어 지원**: "보유 크레딧: X BCH" 형식
- **API 통합**: API 키를 사용한 결제 서비스와의 안전한 통신

### 환경변수 처리
- **빌드 시점 주입**: 환경변수가 이제 Docker 빌드 중에 적절히 주입됨
- **런타임 호환성**: 컨테이너화된 환경에서 시스템이 올바르게 작동
- **폴백 지원**: 다양한 배포 시나리오를 위한 다중 폴백 메커니즘

### JavaScript 통합
- **클라이언트 측 구성**: `window.__BCH_CONFIG__`를 통한 동적 구성 로딩
- **서버 측 렌더링**: SSR 중 적절한 환경변수 처리
- **오류 처리**: 포괄적인 오류 로깅 및 폴백 메커니즘

---

## 설치 및 구성

### 1. 사전 요구사항

- Docker 및 Docker Compose
- DNS가 구성된 도메인 이름
- SSL 인증서 (Let's Encrypt)
- 1GB+ RAM 서버 (DigitalOcean Droplet 또는 유사)
- Bitcoin Cash 및 Electron Cash의 기본 지식

### 2. 설정 지침

1. **저장소 복제 및 환경변수 구성**:
   - 결제 지갑 주소 구성
   - API 키 및 자격 증명 설정

2. **서비스 시작**:
   ```bash
   docker-compose up -d
   ```

3. **Electron Cash 지갑 초기화**:
   - 시스템이 자동으로 지갑을 설정하고 결제 주소를 생성합니다

### 3. 구성 옵션

시스템은 Docker Compose 파일의 환경변수를 통해 다양한 구성 옵션을 지원합니다:

- `MOCK_MODE`: 모의 결제 처리 활성화/비활성화 (true/false)
- `TESTNET`: 메인넷 대신 BCH 테스트넷 사용 (true/false)
- `DIRECT_MODE`: 직접 결제 처리 모드 활성화 (true/false)
- `MIN_CONFIRMATIONS`: 결제를 완료로 표시하는 데 필요한 최소 확인 수
- `PAYOUT_WALLET`: 중앙집중식 결제를 위한 BCH 주소
- `ELECTRON_CASH_URL`: Electron Cash RPC 서비스 URL
- `LEMMY_API_URL`: Lemmy API URL
- `FORWARD_PAYMENTS`: 수신된 자금을 지급 지갑으로 자동 전송 활성화

---

## 구성 요소

### 1. Lemmy 코어

- Docker 컨테이너를 사용한 표준 Lemmy 설치
- 게시물, 댓글 및 사용자 상호작용이 있는 커뮤니티 플랫폼
- 사용자 정의 BCH 통합이 포함된 Lemmy 및 Lemmy-UI 버전 0.19.8
- 포럼 데이터 저장을 위한 PostgreSQL 데이터베이스
- 이미지 처리를 위한 Pictrs 서비스

### 2. Bitcoin Cash 결제 서비스

- BCH 결제 처리를 위한 Flask 기반 API 서비스
- 기능:
  - 인보이스 생성 및 관리
  - 결제 검증 및 거래 모니터링
  - 사용자 크레딧 관리
  - 모바일 결제를 위한 QR 코드 생성
  - 사용자 크레딧 적용을 위한 Lemmy API와의 통합
  - UI 통합을 위한 RESTful API 엔드포인트
- 데이터베이스: WAL 저널링 모드가 포함된 SQLite
- 위치: `/user/oratio/bitcoincash_service`

### 3. Electron Cash 통합

- Bitcoin Cash 지갑 백엔드 역할
- 관리 항목:
  - 주소 생성
  - 잔액 확인
  - 거래 검증
  - 결제 전송
- 결제 서비스를 위한 RPC 인터페이스
- 지갑 데이터는 `/user/oratio/data/electron_cash`에 저장

### 4. Nginx 구성

- Lemmy 및 결제 서비스 모두를 위한 리버스 프록시
- Let's Encrypt 인증서를 사용한 SSL 종료
- HTTP 및 HTTPS 트래픽 처리를 위한 구성
- BCH UI 자산을 위한 정적 파일 제공
- 위치: `/user/oratio/nginx`

---

## 데이터베이스 구조

결제 서비스는 다음 테이블이 있는 SQLite를 사용합니다:

- **invoices**: 결제 인보이스 및 상태 저장
  - 필드: id, payment_address, amount, status, created_at, expires_at, paid_at, user_id, tx_hash, confirmations

- **addresses**: 결제용으로 생성된 BCH 주소 추적
  - 필드: address, created_at, used

- **user_credits**: 사용자 크레딧 잔액 관리
  - 필드: user_id, credit_balance, last_updated

- **transactions**: 모든 거래 기록 저장
  - 필드: id, user_id, amount, type, description, created_at, invoice_id

---

## API 엔드포인트

### 결제 서비스 API

- **/generate_invoice**: 새 결제 인보이스 생성
  - 매개변수: amount, user_id
  - 반환값: 결제 주소가 포함된 인보이스 세부정보

- **/invoice/<invoice_id>**: 인보이스 세부정보 보기
  - QR 코드 및 결제 상태 표시

- **/check_payment/<invoice_id>**: 결제 상태 확인
  - 인보이스의 현재 상태 반환: pending, paid, completed, expired

- **/api/user_credit/<user_id>**: 사용자 크레딧 잔액 조회
  - API 키 인증 필요
  - 실시간 크레딧 표시를 위해 UI에서 사용

- **/api/transactions/<user_id>**: 사용자 거래 내역 조회
  - API 키 인증 필요

- **/health**: 서비스 상태 확인 엔드포인트

### UI 통합 엔드포인트

- **BCH 구성**: 클라이언트 측 스크립트를 위한 동적 구성 주입
- **크레딧 업데이트**: 실시간 크레딧 잔액 조회
- **결제 상태**: 활성 인보이스의 실시간 결제 상태 업데이트

---

## 결제 처리 흐름

1. **인보이스 생성**:
   - 사용자가 금액과 함께 인보이스 요청
   - 시스템이 고유한 BCH 주소 생성 (또는 직접 결제 주소 사용)
   - QR 코드가 생성되어 쉬운 모바일 결제를 지원

2. **결제 모니터링**:
   - 백그라운드 서비스가 들어오는 결제를 확인
   - 각 보류 중인 인보이스에 대해 시스템이 주소 잔액을 확인
   - 결제가 감지되면 거래가 검증됨

3. **확인 프로세스**:
   - 시스템이 각 거래의 확인을 모니터링
   - 최소 확인 수에 도달하면 결제가 완료로 표시
   - 사용자 계정에 크레딧이 추가됨

4. **크레딧 적용**:
   - 사용자 크레딧이 Lemmy 시스템 내에서 적용됨
   - 감사를 위해 거래 기록이 유지됨

5. **선택적 전송**:
   - 활성화된 경우, 수신된 자금이 자동으로 중앙 지갑으로 전송됨
   - 지갑 관리 및 보안에 도움

---

## 백업 및 유지보수

### 지갑 백업

시스템에는 Electron Cash 지갑 데이터를 백업하기 위해 정기적으로 실행되어야 하는 지갑 백업 스크립트(`wallet_backup.sh`)가 포함되어 있습니다. 백업할 주요 파일:

- `/srv/lemmy/defadb.com/data/electron_cash/wallets`
- `/srv/lemmy/defadb.com/data/electron_cash/seed.txt`
- `/srv/lemmy/defadb.com/data/bitcoincash/payments.db`

### 거래 모니터링

백그라운드 프로세스가 지속적으로 거래를 모니터링하고 결제 상태를 자동으로 업데이트합니다. 이는 Bitcoin Cash 결제 서비스 컨테이너 내에서 실행됩니다.

### 데이터베이스 유지보수

SQLite 데이터베이스는 더 나은 성능과 신뢰성을 위해 WAL 저널링 모드를 사용합니다. 정기적인 체크포인트가 자동으로 발생하지만, 최적의 성능을 위해 가끔 수동 배큠이 필요할 수 있습니다.

---

## 보안 고려사항

- **지갑 보안**: Electron Cash 지갑은 안전한 자격 증명 관리가 필요
- **API 인증**: API 키가 민감한 엔드포인트를 보호
- **거래 전송**: 시스템이 수신된 자금을 지정된 지급 지갑으로 자동 이동 가능
- **SSL/TLS**: 모든 연결이 Nginx를 통해 SSL/TLS로 보안됨
- **데이터베이스 보안**: SQLite 데이터베이스가 적절한 잠금 및 외래 키 제약 조건 사용
- **오류 처리**: 포괄적인 오류 처리로 정보 누출 방지
- **네트워크 격리**: Docker 네트워킹이 서비스를 적절히 격리

---

## 환경변수 구성

### Docker 빌드 구성

시스템은 이제 빌드 및 런타임 모두에서 환경변수를 적절히 처리합니다:

```dockerfile
# 빌드 시점 환경변수
ARG LEMMY_API_KEY
ARG LEMMY_BCH_PAYMENT_URL
ARG LEMMY_BCH_API_URL

# 런타임 환경변수
ENV LEMMY_API_KEY=${LEMMY_API_KEY}
ENV LEMMY_BCH_PAYMENT_URL=${LEMMY_BCH_PAYMENT_URL}
ENV LEMMY_BCH_API_URL=${LEMMY_BCH_API_URL}
```

### Docker Compose 설정

```yaml
services:
  lemmy-ui:
    build:
      context: ./user/lemmy-ui-custom/
      args:
        LEMMY_API_KEY: ${LEMMY_API_KEY}
        LEMMY_BCH_PAYMENT_URL: ${BCH_PAYMENT_URL}
        LEMMY_BCH_API_URL: ${BCH_API_URL}
    environment:
      - LEMMY_API_KEY=${LEMMY_API_KEY}
      - LEMMY_BCH_PAYMENT_URL=${BCH_PAYMENT_URL}
      - LEMMY_BCH_API_URL=${BCH_API_URL}
```

### 주요 환경변수

- `LEMMY_API_KEY`: UI와 결제 서비스 간 안전한 통신을 위한 API 키
- `LEMMY_BCH_PAYMENT_URL`: 결제 서비스 인터페이스 URL
- `LEMMY_BCH_API_URL`: 사용자 크레딧 쿼리를 위한 API 엔드포인트
- `MOCK_MODE`: 모의 결제 처리 활성화/비활성화
- `DIRECT_MODE`: 직접 결제 처리 모드 활성화
- `MIN_CONFIRMATIONS`: 필요한 최소 확인 수
- `PAYOUT_WALLET`: 결제를 위한 중앙 BCH 주소

---

## 문제 해결

### 일반적인 문제

- **환경변수 문제**: 
  - 문제: UI에 BCH 구성에 대해 "undefined" 표시
  - 해결책: 적절한 빌드 인수로 Docker 이미지 재빌드
  - 명령어: `docker-compose build --no-cache lemmy-ui`

- **크레딧 표시 문제**:
  - 문제: 드롭다운에 사용자 크레딧이 표시되지 않음
  - 해결책: API 키 구성 및 네트워크 연결 확인
  - 디버그: API 오류에 대한 브라우저 콘솔 확인

- **결제 버튼 누락**:
  - 문제: 네비게이션에 BCH 버튼이 보이지 않음
  - 해결책: JavaScript 통합 및 환경변수 확인
  - 폴백: 백업으로 플로팅 버튼 나타남

- **연결 문제**: Electron Cash RPC 서비스에 접근할 수 없는 경우 네트워크 설정 및 자격 증명 확인
- **데이터베이스 잠금**: 높은 동시성 중에 SQLite 데이터베이스에서 잠금 문제가 발생할 수 있음
- **거래 확인**: BCH 네트워크 혼잡으로 거래 확인이 지연될 수 있음

### 로그

- 메인 로그는 `logs` 디렉터리에서 사용 가능
- Electron Cash 로그는 `electron-cash-logs.txt`에 있음
- Bitcoin Cash 서비스 로그는 `bitcoincash_service/bch_payment.log`에 있음
- UI 통합 로그는 브라우저 콘솔에서 사용 가능

### 진단 명령어

디버깅을 위해 다음 명령어를 사용할 수 있습니다:

```bash
# Bitcoin Cash 서비스 로그 확인
docker-compose logs bitcoincash-service

# UI 컨테이너 로그 확인
docker-compose logs lemmy-ui

# BCH 구성 테스트
docker-compose exec lemmy-ui printenv | grep BCH

# API 연결 테스트
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8081/api/user_credit/1
```

---

## 기술 노트

- 시스템은 네트워크 중단을 우아하게 처리하도록 설계됨
- 직접 결제 처리기는 Electron Cash를 사용할 수 없을 때 폴백 기능 제공
- 데이터베이스 작업은 적절한 잠금 및 타임아웃 처리 사용
- 외부 API는 거래 검증의 폴백으로 사용됨
- 환경변수는 빌드 및 런타임 모두에서 적절히 주입됨
- UI 통합은 폴백 지원과 함께 현대적인 JavaScript 패턴 사용
- 실시간 크레딧 업데이트는 안전한 API 통신 사용
- 거래 모니터링은 메인 애플리케이션을 차단하지 않도록 백그라운드 스레드에서 발생

### 최근 개선사항 (2025년)

- **Webpack 구성**: 빌드 프로세스 중 적절한 환경변수 주입
- **Docker 통합**: 빌드 시점 및 런타임 환경변수 처리
- **UI 구성 요소**: BCH 통합을 위한 네이티브 React/Inferno 구성 요소
- **API 보안**: UI-서비스 통신을 위한 향상된 API 키 인증
- **오류 처리**: 포괄적인 오류 로깅 및 사용자 피드백
- **반응형 디자인**: 모바일 친화적인 결제 인터페이스

---

## 향후 개선사항

고려할 잠재적 개선사항:

- **다중 지갑 지원**: 더 나은 확장을 위한 다중 지갑 구현
- **향상된 분석**: 결제 패턴에 대한 상세한 보고 추가
- **추가 암호화폐**: BCH를 넘어 다른 코인으로 확장
- **고급 검증**: 추가 결제 검증 방법 구현
- **사용자 인터페이스 개선**: 더 포괄적인 관리자 대시보드 생성
- **성능 최적화**: 더 높은 처리량을 위한 데이터베이스 작업 추가 최적화
- **모바일 앱 통합**: 네이티브 모바일 앱 결제 지원
- **고급 크레딧 시스템**: 크레딧 만료 및 사용 추적 구현
- **다국어 지원**: 한국어를 넘어 다른 언어로 확장

---

## 개발 워크플로

### Git 버전 관리

이 프로젝트는 버전 관리를 위해 Git을 사용합니다. 저장소는 `.gitignore` 파일을 통해 `.env`, 지갑 데이터 및 데이터베이스 파일과 같은 민감한 파일을 무시하도록 구성되어 있습니다.

### 표준 개발 흐름

1. **파일 변경**
   - 기능 구현 또는 버그 수정

2. **변경사항 스테이징**
   ```bash
   git add .
   ```
   - `.gitignore`에 의해 무시된 파일을 제외한 모든 수정된 파일을 스테이징

3. **변경사항 커밋**
   ```bash
   git commit -m "변경사항 설명"
   ```
   - 명확하고 설명적인 커밋 메시지 사용

4. **원격 저장소에 푸시**
   ```bash
   git push origin main
   ```
   - 다른 브랜치에서 작업하는 경우 `main`을 브랜치 이름으로 교체

### 민감한 파일

다음 유형의 파일은 보안상의 이유로 버전 관리에서 제외됩니다:
- 환경변수 (`.env`, `*.env`)
- 지갑 데이터 및 시드 구문
- 암호 파일
- 데이터베이스 파일
- 인증서 및 키
- 로그 파일

### 새 파일을 무시 목록에 추가

더 많은 파일을 무시해야 하는 경우 `.gitignore` 파일을 업데이트하십시오:
```bash
echo "무시할_패턴" >> .gitignore
git add .gitignore
git commit -m "새 패턴을 제외하도록 .gitignore 업데이트"
```
