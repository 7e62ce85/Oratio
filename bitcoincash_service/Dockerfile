# 1단계: 빌드 환경
FROM rust:1.72 AS builder
#FROM ekidd/rust-musl-builder:stable AS builder
WORKDIR /app

# 필수 패키지 설치
#RUN apt update && apt install -y musl-tools

# Rust 바이너리를 `musl` 타겟으로 빌드하도록 설정
#RUN rustup target add x86_64-unknown-linux-musl

# Cargo.toml과 소스 복사
COPY Cargo.toml .
COPY src ./src
# 프로그램을 릴리즈 모드로 빌드
#RUN cargo build --release --target=x86_64-unknown-linux-musl

# 릴리즈 모드로 빌드 (기본 타겟 사용)
RUN cargo update
RUN cargo build --release

# 2단계: 실행 환경 (glibc 기반)
FROM debian:bookworm-slim
#FROM debian:bullseye-slim
WORKDIR /app
# VS
# 2단계: 실행 환경: `alpine`을 사용해 최적화 (GLIBC 없이 실행 가능)
#FROM alpine:latest
#WORKDIR /app

# 빌드된 바이너리 복사 (musl 사용)(빌드 단계의 기본 경로는 /home/rust/src/target/...)
#COPY --from=builder /home/rust/src/target/x86_64-unknown-linux-musl/release/bitcoincash_service /app/
#COPY --from=builder /app/target/x86_64-unknown-linux-musl/release/bitcoincash_service /app/
COPY --from=builder /app/target/release/bitcoincash_service /app/

# 빌드된 바이너리 복사
#COPY --from=builder /app/target/release/bitcoincash_service /app/

# 실행
CMD ["./bitcoincash_service"]
ENV RUST_LOG=info
