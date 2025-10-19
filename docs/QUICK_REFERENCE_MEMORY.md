# Quick Reference: Electron Cash Memory Monitoring

## Check Current Status

```bash
# Memory usage
docker stats --no-stream electron-cash

# Process count
docker top electron-cash | grep python | wc -l

# Container logs
docker logs electron-cash --tail 50

# System memory
free -h
```

## Run Health Check

```bash
/home/user/Oratio/oratio/health_check_and_restart.sh
```

## Manual Restart (if needed)

```bash
cd /home/user/Oratio/oratio
docker-compose restart electron-cash
```

## View Logs

```bash
# Health check log
tail -f /home/user/Oratio/oratio/logs/health_check.log

# Restart history
tail -f /home/user/Oratio/oratio/logs/restart_history.log
```

## Expected Normal Values

- **Memory:** 50-200 MB (max 2 GB limit)
- **Processes:** 2-3 Python processes
- **Alerts triggered if:**
  - Memory > 500 MB
  - Processes > 10

## Emergency Actions

If memory leak occurs again:

```bash
# 1. Restart container
docker-compose restart electron-cash

# 2. Check for process multiplication
docker top electron-cash

# 3. Check logs for errors
docker logs electron-cash --tail 100
```
