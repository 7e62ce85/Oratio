# DigitalOcean Lemmy & Bitcoincash Payment Service
(Initial API endpoint testing has been completed, with successful GET invoice generation and POST payment callback verification. The core API infrastructure is responding as expected, though the actual BCH payment processing is not yet implemented.)

This project describes the final implementation of **Lemmy** and a **Bitcoincash Payment Service** (Rust-based) using Docker containers on a DigitalOcean Droplet (1GB RAM, Debian 12), with **Nginx** configured as a reverse proxy and SSL (Let's Encrypt) settings applied.

## Table of Contents

- [Project Overview](#project-overview)
- [Components](#components)
- [Prerequisites](#prerequisites)
- [Installation and Deployment](#installation-and-deployment)
  - [1. DigitalOcean Droplet and DNS Setup](#1-digitalocean-droplet-and-dns-setup)
  - [2. Lemmy Installation (Ansible)](#2-lemmy-installation-ansible)
  - [3. Bitcoincash Payment Rust Service Setup](#3-bitcoincash-payment-rust-service-setup)
    - [3.1 Directory Structure](#31-directory-structure)
    - [3.2 Cargo.toml and Rust Code](#32-cargotoml-and-rust-code)
    - [3.3 Dockerfile and Build/Run](#33-dockerfile-and-buildrun)
  - [4. Nginx Reverse Proxy and SSL Setup](#4-nginx-reverse-proxy-and-ssl-setup)
  - [5. Additional Configuration and Troubleshooting](#5-additional-configuration-and-troubleshooting)
- [Testing and Validation](#testing-and-validation)
- [Troubleshooting Tips](#troubleshooting-tips)
- [License](#license)

---

## Project Overview

This project aims to:

- Install **Lemmy** community platform on DigitalOcean (using Ansible and Docker Compose)
- Develop and deploy a **Bitcoincash Payment Service** using Rust (Actix-web) in Docker containers
- Configure **Nginx** as a reverse proxy for domain-specific service access with Let's Encrypt SSL
- Ensure automatic startup on system reboot and resolve Docker networking issues

---

## Components

- **Lemmy**: Community platform (Docker Compose based)
- **Bitcoincash Payment Service**: Rust (Actix-web) based payment API service
- **Nginx**: Acts as reverse proxy, HTTP → HTTPS redirection, upstream configuration
- **Certbot/Let's Encrypt**: SSL certificate issuance
- **Ansible**: Lemmy installation automation
- **Docker & Docker Compose**: Container-based deployment

---

## Prerequisites

- DigitalOcean Droplet (Debian 12, 1GB RAM)
- Domain (e.g., `defadb.com`, `www.defadb.com`, `payments.defadb.com`) and DNS A records configuration
- Basic knowledge of Git, Docker, Docker Compose, Certbot, and Ansible

---

## Installation and Deployment

### 1. DigitalOcean Droplet and DNS Setup

1. **Create Droplet**
   - Create in DigitalOcean console with Shared CPU, 1GB RAM, Debian 12 x64, Singapore region

2. **DNS Configuration**
   - Add following A records in domain management page:
     - `defadb.com` → Droplet IP
     - `www.defadb.com` → Droplet IP
     - `payments.defadb.com` → Droplet IP

---

### 2. Lemmy Installation (Ansible)
( https://github.com/LemmyNet/lemmy-ansible/tree/main )

1. **Install Ansible (Local or WSL)**
   ```bash
   sudo apt update
   sudo apt install ansible
   ```

2. **Clone and Configure Lemmy-Ansible**
   ```bash
   git clone https://github.com/LemmyNet/lemmy-ansible.git
   cd lemmy-ansible
   ```
   - Modify server, domain, PostgreSQL settings in `inventory/host_vars/defadb.com/config.hjson`

3. **Run Lemmy Installation**
   ```bash
   ansible-playbook -i inventory/hosts lemmy.yml
   ```
   - After installation, Docker Compose files will be created in `/srv/lemmy/defadb.com` directory

---

### 3. Bitcoincash Payment Rust Service Setup

#### 3.1 Directory Structure

Project root directory: `/srv/lemmy/defadb.com`

```plaintext
/srv/lemmy/defadb.com
└── bitcoincash_service
    ├── Cargo.toml
    ├── Dockerfile
    └── src
        └── main.rs
```

#### 3.2 Cargo.toml and Rust Code

**Cargo.toml**
```toml
[package]
name = "bitcoincash_service"
version = "0.1.0"
edition = "2021"

[dependencies]
actix-web = "4.3.1"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

**src/main.rs**
```rust
use actix_web::{web, App, HttpResponse, HttpServer, Responder};
use serde::{Deserialize, Serialize};
use std::sync::Mutex;

#[derive(Serialize, Deserialize, Debug, Clone)]
struct PaymentInvoice {
    invoice_id: String,
    payment_address: String,
    amount: f64,
    status: String,
}

#[derive(Serialize, Deserialize, Debug)]
struct PaymentCallback {
    invoice_id: String,
    status: String, // e.g., "paid"
    txid: String,
}

struct AppState {
    invoices: Mutex<Vec<PaymentInvoice>>,
}

async fn generate_invoice(state: web::Data<AppState>) -> impl Responder {
    let invoice = PaymentInvoice {
        invoice_id: "invoice123".to_string(),
        payment_address: "bitcoincash:qr3jej...".to_string(),
        amount: 0.005,
        status: "pending".to_string(),
    };
    {
        let mut invoices = state.invoices.lock().unwrap();
        invoices.push(invoice.clone());
    }
    HttpResponse::Ok().json(invoice)
}

async fn payment_callback(
    state: web::Data<AppState>,
    callback: web::Json<PaymentCallback>,
) -> impl Responder {
    println!("Payment callback received: {:?}", callback);
    let mut updated = false;
    {
        let mut invoices = state.invoices.lock().unwrap();
        for inv in invoices.iter_mut() {
            if inv.invoice_id == callback.invoice_id && callback.status == "paid" {
                inv.status = "paid".to_string();
                updated = true;
                println!("Updated invoice: {:?}", inv);
                break;
            }
        }
    }
    if updated {
        HttpResponse::Ok().body("Payment complete, status updated")
    } else {
        HttpResponse::BadRequest().body("Payment verification failed or invalid status")
    }
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    let app_state = web::Data::new(AppState {
        invoices: Mutex::new(Vec::new()),
    });
    HttpServer::new(move || {
        App::new()
            .app_data(app_state.clone())
            .route("/generate_invoice", web::get().to(generate_invoice))
            .route("/payment_callback", web::post().to(payment_callback))
    })
    .bind("0.0.0.0:8081")?
    .run()
    .await
}
```

#### 3.3 Dockerfile and Build/Run

**Dockerfile**
```dockerfile
# Stage 1: Build environment (glibc based)
FROM rust:1.72 AS builder
WORKDIR /app

# Copy Cargo files and source code
COPY Cargo.toml ./
COPY src ./src

RUN cargo update
RUN cargo build --release

# Stage 2: Runtime environment (glibc based Debian)
FROM debian:bookworm-slim
WORKDIR /app

COPY --from=builder /app/target/release/bitcoincash_service /app/

CMD ["./bitcoincash_service"]
```

**Build and Run**
```bash
cd /srv/lemmy/defadb.com/bitcoincash_service
docker build -t bitcoincash_service .
docker run -d -p 8081:8081 bitcoincash_service
```

Testing:
- Generate invoice:  
  `curl http://<server-IP>:8081/generate_invoice`
- Payment callback:  
  ```bash
  curl -v -X POST "http://<server-IP>:8081/payment_callback" \
       -H "Content-Type: application/json" \
       -d '{"invoice_id": "invoice123", "status": "paid", "txid": "some_tx_id"}'
  ```

---

### 4. Nginx Reverse Proxy and SSL Setup

#### 4.1 Nginx Container Configuration (Docker Compose Example)

The Nginx container exposes ports 80 and 443 to the host.
- `defadb.com` proxies to Lemmy UI/Backend
- `payments.defadb.com` proxies to Bitcoincash service (`http://bitcoincash_service:8081`)

#### 4.2 Nginx Configuration Example (nginx_internal.conf)
```nginx
worker_processes auto;

events {
    worker_connections 1024;
}

http {
    resolver 127.0.0.11 valid=5s;

    # Lemmy default configuration
    map "$request_method:$http_accept" $proxpass {
        default "http://lemmy-ui:1234";
        "~^(?:GET|HEAD):.*?application/(?:activity|ld)\+json" "http://lemmy:8536";
        "~^(?!(GET|HEAD)).*:" "http://lemmy:8536";
    }

    #########################
    # defadb.com - HTTP → HTTPS redirect
    #########################
    server {
        listen 80;
        server_name defadb.com www.defadb.com;
        return 301 https://$host$request_uri;
    }

    #########################
    # defadb.com - HTTPS
    #########################
    server {
        listen 443 ssl;
        server_name defadb.com www.defadb.com;

        ssl_certificate /etc/letsencrypt/live/defadb.com/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/defadb.com/privkey.pem;

        client_max_body_size 20M;
        include proxy_params;

        location / {
            proxy_pass http://lemmy-ui:1234;
        }

        location ~ ^/(api|feeds|nodeinfo|.well-known|version|sitemap.xml) {
            proxy_pass http://lemmy:8536;
        }

        location /pictrs/ {
            proxy_pass http://pictrs:8080;
        }
    }

    #########################
    # payments.defadb.com - HTTP (apply HTTPS if needed)
    #########################
    server {
        listen 80;
        server_name payments.defadb.com;

        location / {
            proxy_pass http://bitcoincash_service:8081;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_pass_request_headers on;
        }
    }
}
```

#### 4.3 SSL Certificate Issuance (Let's Encrypt)

1. Stop Nginx container:
   ```bash
   docker-compose stop proxy
   ```
2. Issue certificates using Certbot:
   ```bash
   sudo certbot certonly --standalone -d defadb.com -d www.defadb.com
   sudo certbot certonly --standalone -d payments.defadb.com
   ```
3. Restart Nginx container and configure `/etc/letsencrypt` volume mount

---

### 5. Additional Configuration and Troubleshooting

#### 5.1 Resolving Port Conflicts
- If port 8081 is already in use, stop/remove existing bitcoincash_service container:
  ```bash
  docker stop <container_id>
  docker rm <container_id>
  ```

#### 5.2 System Service Configuration
- Create `/etc/systemd/system/lemmy.service` for automatic startup:
  ```ini
  [Unit]
  Description=Lemmy and Bitcoincash Payment Service
  After=docker.service
  Requires=docker.service

  [Service]
  Type=oneshot
  RemainAfterExit=yes
  WorkingDirectory=/srv/lemmy/defadb.com
  Environment=PATH=/usr/bin:/usr/local/bin
  ExecStart=/usr/bin/docker-compose up -d
  ExecStop=/usr/bin/docker-compose down

  [Install]
  WantedBy=multi-user.target
  ```
- Register and enable service:
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl enable lemmy
  sudo systemctl start lemmy
  ```

#### 5.3 Docker Network Configuration Improvements
- To resolve network communication issues between Nginx and bitcoincash_service, consider modifying network settings in docker-compose.yml and adding `upstream` blocks in nginx_internal.conf

Example (docker-compose.yml):
[Docker Compose configuration remains the same as in the Korean version]

---

## Testing and Validation

1. **Direct Bitcoincash Service Testing (Port 8081)**
   - GET: `http://<server-IP>:8081/generate_invoice` → Check JSON response
   - POST:  
     ```bash
     curl -v -X POST "http://<server-IP>:8081/payment_callback" \
          -H "Content-Type: application/json" \
          -d '{"invoice_id": "invoice123", "status": "paid", "txid": "some_tx_id"}'
     ```

2. **Nginx Reverse Proxy Testing**
   - Access `https://defadb.com` in browser to verify Lemmy UI/Backend
   - Test Bitcoincash service through browser or curl at `http://payments.defadb.com` (or HTTPS if applied)

---

## Troubleshooting Tips

- **Port Conflicts**: Check used ports and execute container stop/remove commands (`docker stop`/`docker rm`)
- **Network Communication Errors**: Verify Docker Compose network settings and apply Nginx `upstream` configuration
- **SSL Certificate Renewal**: Configure Certbot auto-renewal (using cron or systemd timer)

---
