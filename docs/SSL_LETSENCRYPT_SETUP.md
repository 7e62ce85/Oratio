# Let's Encrypt SSL Certificate Setup for Oratio

## Overview

This document describes the Let's Encrypt SSL certificate setup process for the Oratio project running on AWS EC2 with Docker containers.

**Date Created**: September 29, 2025  
**Last Updated**: September 29, 2025  
**Author**: System Setup Documentation  

---

## Problem Solved

### Initial Issue
- Nginx container (`oratio-proxy-1`) was continuously restarting
- Error: `cannot load certificate "/etc/letsencrypt/live/oratio.space/fullchain.pem": BIO_new_file() failed`
- SSL certificates were missing from the expected location

### Root Cause
- The nginx configuration was looking for SSL certificates at `/etc/letsencrypt/live/oratio.space/`
- The docker-compose.yml was mounting the system's `/etc/letsencrypt` directory which was empty
- No valid SSL certificates were configured for the domain

---

## Solution Implemented

### 1. Let's Encrypt Integration

#### Docker Compose Configuration
Added a `certbot` service to `docker-compose.yml`:

```yaml
certbot:
  image: certbot/certbot
  restart: unless-stopped
  volumes:
    - ./data/certbot/conf:/etc/letsencrypt
    - ./data/certbot/www:/var/www/certbot
  entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew; sleep 12h & wait $${!}; done;'"
```

#### Nginx Volume Mounts
Updated nginx proxy service volumes:

```yaml
volumes:
  - ./nginx_production.conf:/etc/nginx/nginx.conf:ro,Z
  - ./proxy_params:/etc/nginx/proxy_params:ro,Z
  - ./nginx/js:/etc/nginx/js:ro,Z
  # Let's Encrypt certificates and webroot
  - ./data/certbot/conf:/etc/letsencrypt:ro,Z
  - ./data/certbot/www:/var/www/certbot:ro,Z
```

### 2. Nginx Configuration

#### SSL Configuration in nginx_production.conf
```nginx
# SSL 인증서 (Let's Encrypt)
ssl_certificate /etc/letsencrypt/live/oratio.space/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/oratio.space/privkey.pem;

# SSL 설정 최적화
include /etc/letsencrypt/options-ssl-nginx.conf;
ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
```

#### ACME Challenge Configuration
```nginx
location /.well-known/acme-challenge/ {
    root /var/www/certbot;
}
```

### 3. Automated Certificate Setup

#### Setup Script: `init-letsencrypt-simple.sh`
Created an automated script that:

1. **Downloads TLS parameters**:
   - `options-ssl-nginx.conf` 
   - `ssl-dhparams.pem`

2. **Creates dummy certificates** for nginx startup

3. **Starts nginx** with temporary certificates

4. **Requests real certificates** from Let's Encrypt using webroot method

5. **Reloads nginx** with valid certificates

#### Key Script Features
- **Domain**: `oratio.space` only (subdomains commented out)
- **RSA Key Size**: 4096 bits
- **Email**: `admin@oratio.space`
- **Auto-renewal**: Configured via certbot container

---

## Current Configuration Status

### ✅ Successfully Configured
- **SSL Certificate**: Valid for `oratio.space`
- **Certificate Authority**: Let's Encrypt (E8)
- **Expiry Date**: December 28, 2025 (3 months)
- **Nginx**: Running successfully with SSL
- **Auto-Renewal**: Certbot runs every 12 hours

### 🔧 Network Access Issue
**Problem**: External access blocked by AWS Security Groups

**Status**: HTTPS/HTTP not accessible from external sources due to AWS firewall

**Required Action**: Configure AWS Security Groups to allow:
- **Port 80 (HTTP)**: Inbound from `0.0.0.0/0`
- **Port 443 (HTTPS)**: Inbound from `0.0.0.0/0`

### ⏸️ Temporarily Disabled
- **www.oratio.space**: DNS not configured (commented out in nginx)
- **payments.oratio.space**: DNS not configured (commented out in nginx)

---

## Certificate Information

### Current Certificate Details
```
Subject: CN=oratio.space
Issuer: C=US; O=Let's Encrypt; CN=E8
Valid From: September 29, 2025 09:26:53 GMT
Valid Until: December 28, 2025 09:26:52 GMT
Key Algorithm: EC/prime256v1 (256/128 Bits)
Signature Algorithm: ecdsa-with-SHA384
```

### Certificate Files Location
- **Certificate**: `/etc/letsencrypt/live/oratio.space/fullchain.pem`
- **Private Key**: `/etc/letsencrypt/live/oratio.space/privkey.pem`
- **Chain**: `/etc/letsencrypt/live/oratio.space/chain.pem`
- **Certificate Only**: `/etc/letsencrypt/live/oratio.space/cert.pem`

---

## AWS Infrastructure Details

### Server Information
- **Instance ID**: `i-115613c0669a6fd352787193c4a2da30`
- **Public IP**: `70.34.244.93`
- **Platform**: AWS EC2
- **Operating System**: Linux

### Required AWS Configuration

#### Security Group Rules Needed
```
Type    | Protocol | Port Range | Source     | Description
--------|----------|------------|------------|-------------
HTTP    | TCP      | 80         | 0.0.0.0/0  | Allow HTTP
HTTPS   | TCP      | 443        | 0.0.0.0/0  | Allow HTTPS
SSH     | TCP      | 22         | <your-ip>  | Admin access
```

#### AWS CLI Commands (if needed)
```bash
# Get Security Group ID
aws ec2 describe-instances --instance-ids i-115613c0669a6fd352787193c4a2da30 \
  --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId'

# Add HTTP rule
aws ec2 authorize-security-group-ingress --group-id sg-xxxxxx \
  --protocol tcp --port 80 --cidr 0.0.0.0/0

# Add HTTPS rule  
aws ec2 authorize-security-group-ingress --group-id sg-xxxxxx \
  --protocol tcp --port 443 --cidr 0.0.0.0/0
```

---

## DNS Configuration

### Current DNS Status
```
oratio.space        -> 70.34.244.93 ✅ (Configured)
www.oratio.space    -> Not configured ❌
payments.oratio.space -> Not configured ❌
```

### Required DNS Records (for future expansion)
```
Type | Name                  | Value        | TTL
-----|----------------------|--------------|----
A    | www.oratio.space     | 70.34.244.93 | 300
A    | payments.oratio.space| 70.34.244.93 | 300
```

---

## Renewal and Maintenance

### Automatic Renewal
- **Method**: Certbot container runs every 12 hours
- **Command**: `certbot renew`
- **Notification**: Check logs for renewal status
- **Grace Period**: Certificates auto-renew 30 days before expiry

### Manual Renewal (if needed)
```bash
# Force renewal
docker-compose exec certbot certbot renew --force-renewal

# Check certificate status
docker-compose exec certbot certbot certificates

# Test renewal (dry run)
docker-compose exec certbot certbot renew --dry-run
```

### Monitoring Commands
```bash
# Check certificate expiry
openssl x509 -in ./data/certbot/conf/live/oratio.space/fullchain.pem -text -noout | grep "Not After"

# Check nginx status
docker logs oratio-proxy-1 --tail 20

# Test SSL configuration
curl -I https://localhost/
```

---

## Troubleshooting

### Common Issues

#### 1. Nginx Won't Start
```bash
# Check nginx configuration
docker exec oratio-proxy-1 nginx -t

# Check certificate files exist
ls -la ./data/certbot/conf/live/oratio.space/
```

#### 2. Certificate Not Found
```bash
# Re-run Let's Encrypt setup
./init-letsencrypt-simple.sh

# Check certbot logs
docker logs oratio-certbot-1
```

#### 3. External Access Issues
```bash
# Check if ports are open locally
netstat -tlnp | grep -E ":80|:443"

# Test local access
curl -I https://localhost/

# Check AWS Security Groups via AWS Console
```

#### 4. SSL Certificate Errors
```bash
# Check certificate validity
openssl x509 -in ./data/certbot/conf/live/oratio.space/fullchain.pem -text -noout

# Check certificate chain
openssl verify -CAfile ./data/certbot/conf/live/oratio.space/chain.pem \
  ./data/certbot/conf/live/oratio.space/cert.pem
```

---

## Adding Subdomains (Future)

### When DNS is Ready

1. **Update nginx configuration** - uncomment subdomain sections in `nginx_production.conf`

2. **Update Let's Encrypt script** - modify `init-letsencrypt-simple.sh`:
```bash
domains=(oratio.space www.oratio.space payments.oratio.space)
```

3. **Request new certificate**:
```bash
docker-compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    --email admin@oratio.space \
    -d oratio.space \
    -d www.oratio.space \
    -d payments.oratio.space \
    --rsa-key-size 4096 \
    --agree-tos \
    --expand" certbot
```

4. **Reload nginx**:
```bash
docker-compose exec proxy nginx -s reload
```

---

## Security Considerations

### SSL Configuration
- **TLS Versions**: 1.2 and 1.3 only
- **HSTS**: Enabled with 1-year max-age
- **OCSP Stapling**: Configured (warning about missing responder URL is normal)
- **Strong Ciphers**: Using Mozilla recommended settings

### Certificate Management
- **Auto-renewal**: Prevents expiry
- **Webroot method**: Safer than standalone mode
- **Rate Limiting**: Let's Encrypt has rate limits (20 certs/week per domain)

### Access Control
- **Firewall**: AWS Security Groups provide network-level protection
- **Nginx**: Additional application-level security headers configured

---

## Related Files

### Configuration Files
- `docker-compose.yml`: Container orchestration with certbot
- `nginx_production.conf`: Nginx SSL configuration
- `init-letsencrypt-simple.sh`: SSL setup automation script

### Certificate Storage
- `./data/certbot/conf/`: Let's Encrypt certificates and configuration
- `./data/certbot/www/`: Webroot for ACME challenges

### Logs and Monitoring
- `docker logs oratio-proxy-1`: Nginx access and error logs
- `docker logs oratio-certbot-1`: Certificate renewal logs

---

## Next Steps

1. **Configure AWS Security Groups** to allow ports 80 and 443
2. **Test external access** to https://oratio.space
3. **Set up DNS records** for www and payments subdomains (when needed)
4. **Monitor certificate renewal** process
5. **Consider backup strategy** for certificates and configuration

---

## Support and Resources

### Documentation
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)
- [Certbot Documentation](https://certbot.eff.org/docs/)
- [Nginx SSL Configuration](https://nginx.org/en/docs/http/configuring_https_servers.html)

### Useful Commands Reference
```bash
# View all containers
docker ps

# Check certificate status
docker-compose exec certbot certbot certificates

# Force certificate renewal
docker-compose exec certbot certbot renew --force-renewal

# Test nginx configuration
docker exec oratio-proxy-1 nginx -t

# Reload nginx
docker-compose exec proxy nginx -s reload

# View certificate details
openssl x509 -in ./data/certbot/conf/live/oratio.space/fullchain.pem -text -noout
```

---

*This documentation was created to track the SSL certificate setup process and serve as a reference for future maintenance and troubleshooting.*
