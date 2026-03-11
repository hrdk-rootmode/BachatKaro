# Redis Setup Guide

## 🎯 Purpose
Guide for setting up Redis for caching, AI healing, and session management.

## 📋 Redis Options

### **Option 1: Railway Redis (Current)**
```bash
# Already configured in .env
REDIS_URL=redis://default:pWJcOLKLIsKyhKiDbuKnMuonBsFLHPQI@yamanote.proxy.rlwy.net:41764
REDIS_MAX_CONNECTIONS=50
```

### **Option 2: Supabase Redis**
```bash
# Add to .env
REDIS_URL=redis://default:password@aws-0-ap-south-1.pooler.supabase.com:5432
REDIS_MAX_CONNECTIONS=50
```

### **Option 3: Local Redis**
```bash
# Add to .env
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=50
```

### **Option 4: Redis Cloud**
```bash
# Add to .env
REDIS_URL=redis://username:password@redis-12345.cloud.redislabs.com:12345
REDIS_MAX_CONNECTIONS=50
```

## 🚀 Quick Setup Commands

### **Test Redis Connection**
```bash
# Test current Redis setup
python scripts/02_setup_database.py  # Includes Redis test

# Test Redis only
python -c "
import asyncio
from app.core.redis_client import redis_client

async def test():
    await redis_client.connect()
    result = await redis_client.ping()
    print(f'Redis ping: {result}')
    await redis_client.disconnect()

asyncio.run(test())
"
```

### **Check Redis Status**
```bash
# Monitor Redis
redis-cli -h host -p port ping

# Check memory usage
redis-cli -h host -p port info memory

# Check connected clients
redis-cli -h host -p port info clients
```

## 🔧 Configuration Files

### **Environment Variables (.env)**
```bash
# Redis Configuration
REDIS_URL=redis://user:password@host:port/database
REDIS_MAX_CONNECTIONS=50

# Optional: Redis SSL
REDIS_SSL=true
REDIS_SSL_CERT_PATH=/path/to/cert.pem
```

### **Application Configuration**
```python
# app/core/redis_client.py - Already configured
# Uses settings.REDIS_URL from .env
# Auto-connects on first use
# Handles connection pooling
```

## 🗂️ Redis Usage in Application

### **AI Healing Cache**
```python
# Selector healing cache
redis_client.set(f"selector:{platform}:{field}:{hash}", selector_json, ttl=86400)  # 24h

# Usage tracking
redis_client.incr(f"groq:usage:healing:{date}")
```

### **Session Management**
```python
# User sessions
redis_client.set(f"session:{session_id}", session_data, ttl=3600)  # 1h

# Rate limiting
redis_client.set(f"rate_limit:{user_id}", request_count, ttl=60)  # 1m
```

### **Product Cache**
```python
# Product data cache
redis_client.set(f"product:{product_fingerprint}", product_json, ttl=1800)  # 30m

# Search results cache
redis_client.set(f"search:{query_hash}", results_json, ttl=900)  # 15m
```

## 🚨 Troubleshooting

### **Common Issues**

#### **Connection Failed**
```bash
# Check URL format
redis-cli -h host -p port ping

# Check network
telnet host port

# Check credentials
redis-cli -h host -p port -a password auth
```

#### **Memory Issues**
```bash
# Check memory usage
redis-cli info memory

# Clear expired keys
redis-cli --scan --pattern "*" | xargs redis-cli del

# Set max memory
redis-cli config set maxmemory 256mb
```

#### **Performance Issues**
```bash
# Monitor slow queries
redis-cli slowlog get 10

# Check connection pool
redis-cli info clients

# Optimize configuration
redis-cli config set timeout 300
redis-cli config set tcp-keepalive 60
```

## 🔍 Redis Monitoring

### **Basic Monitoring**
```bash
# Real-time monitoring
redis-cli monitor

# Statistics overview
redis-cli info

# Memory usage
redis-cli info memory | grep used_memory_human

# Connected clients
redis-cli info clients
```

### **Advanced Monitoring**
```python
# Custom monitoring script
import asyncio
from app.core.redis_client import redis_client

async def monitor_redis():
    while True:
        await redis_client.ping()
        info = await redis_client.info()
        print(f"Memory: {info.get('used_memory_human', 'N/A')}")
        print(f"Clients: {info.get('connected_clients', 'N/A')}")
        await asyncio.sleep(60)

asyncio.run(monitor_redis())
```

## 🛠️ Redis Optimization

### **Connection Pooling**
```python
# Already configured in redis_client.py
max_connections=50
socket_connect_timeout=5
socket_keepalive=True
```

### **Key Expiration**
```python
# AI healing selectors - 24h
redis_client.set(key, value, ttl=86400)

# Sessions - 1h
redis_client.set(key, value, ttl=3600)

# Cache - 30m
redis_client.set(key, value, ttl=1800)
```

### **Memory Management**
```python
# Use efficient data structures
import json
import msgpack  # More compact than JSON

# Compress large values
import gzip
compressed_data = gzip.compress(json.dumps(data).encode())
redis_client.set(key, compressed_data)
```

## 📊 Performance Metrics

### **Key Metrics to Monitor**
- **Connected Clients**: Number of active connections
- **Used Memory**: Current memory usage
- **Hit Rate**: Cache effectiveness
- **Response Time**: Average query time
- **Error Rate**: Failed operations percentage

### **Target Performance**
- **Response Time**: < 10ms for 95% of queries
- **Memory Usage**: < 80% of allocated memory
- **Hit Rate**: > 80% for frequently accessed data
- **Uptime**: > 99.9%

## 🚀 Production Deployment

### **Security**
```bash
# Use strong passwords
REDIS_PASSWORD=$(openssl rand -base64 32)

# Network security
# Configure firewall to allow only application servers
# Use SSL/TLS connections
REDIS_SSL=true

# Authentication
# Disable dangerous commands
redis-cli config set rename-command FLUSHDB ""
redis-cli config set rename-command CONFIG ""
```

### **High Availability**
```bash
# Redis Sentinel for failover
sentinel monitor mymaster 127.0.0.1 6379 2

# Redis Cluster for scaling
redis-cli --cluster create host1:6379 host2:6379 host3:6379

# Backup strategy
redis-cli --rdb /backup/redis-backup-$(date +%Y%m%d).rdb
```

### **Monitoring & Alerting**
```bash
# Redis Exporter for Prometheus
docker run -d -p 9121:9121 oliver006/redis_exporter

# Grafana dashboard
# Visualize Redis metrics
# Set up alerts for memory, connections, errors
```

## 🧪 Testing Redis Setup

### **Basic Test Script**
```python
# test_redis.py
import asyncio
import time
from app.core.redis_client import redis_client

async def test_redis():
    print("🧪 Testing Redis Setup...")
    
    # Test connection
    await redis_client.connect()
    ping = await redis_client.ping()
    print(f"✅ Ping: {ping}")
    
    # Test basic operations
    test_key = f"test:{int(time.time())}"
    
    # Test SET
    set_result = await redis_client.set(test_key, "test_value", ttl=60)
    print(f"✅ SET: {set_result}")
    
    # Test GET
    get_result = await redis_client.get(test_key)
    print(f"✅ GET: {get_result == 'test_value'}")
    
    # Test EXPIRE
    expire_result = await redis_client.set_expiry(test_key, 30)
    print(f"✅ EXPIRE: {expire_result}")
    
    # Test DELETE
    delete_result = await redis_client.delete(test_key)
    print(f"✅ DELETE: {delete_result}")
    
    await redis_client.disconnect()
    print("🎉 Redis test completed!")

if __name__ == "__main__":
    asyncio.run(test_redis())
```

### **Run Test**
```bash
python test_redis.py
```

---

**📞 For Redis issues, check:**
1. Network connectivity to Redis server
2. Firewall settings blocking Redis port
3. Redis server configuration
4. Application connection pool settings

**🎉 Redis is essential for AI healing performance!**
