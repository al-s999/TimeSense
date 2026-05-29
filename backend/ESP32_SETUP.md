# Time Sense Backend - ESP32 Integration Guide

## Problem Fixed
**ECONNRESET Error** - The backend was only binding to `localhost (127.0.0.1)`, which prevented ESP32 and other network devices from accessing it.

## Solution Applied

### 1. **Server Binding Fixed**
The backend now supports binding to `0.0.0.0` (all network interfaces) instead of just localhost.

### 2. **New Startup Scripts**

#### On Linux/macOS:
```bash
cd backend
./run_esp32_mode.sh
```

Or manually:
```bash
uvicorn app.main:app --reload -H 0.0.0.0 -p 8000
```

#### On Windows:
```batch
cd backend
run_esp32_mode.bat
```

Or manually:
```batch
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. **CORS Enabled**
All origins are now allowed for ESP32 connectivity:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 4. **New ESP32 API Endpoints**

#### Health Check (Test Connection)
```
GET /api/health
```
Response: `{ "status": "ok", "service": "time-sense-backend" }`

#### Access Decision (Check Access)
```
GET /api/access?device_id=esp32-001
```
Response: `{ "access": "allow"|"deny", "identity": "saya"|"teman"|null }`

#### Get Commands (Poll for Actions)
```
GET /api/command?device_id=esp32-001
```
Response: `{ "action": "enable"|"disable"|"open_door"|"close_door"|null }`

#### Sensor Updates (Send Data)
```
POST /api/sensor/update
Content-Type: application/json

{
  "device_id": "esp32-001",
  "sensor_type": "temperature|motion|door_state",
  "value": any,
  "timestamp": optional
}
```
Response: `{ "status": "ok", "message": "sensor data received" }`

### 5. **Error Handling & Logging**
All endpoints now include:
- Try-catch error handling
- Proper JSON error responses
- Request/response logging for debugging

Example logs:
```
[API] GET /api/health
[API] GET /api/health OK
[SENSOR] esp32-001 temperature=28.5
```

## Testing from ESP32

### 1. First Test Health Check
```cpp
// Arduino/ESP32 Code
#include <HTTPClient.h>

HTTPClient http;
http.begin("http://192.168.x.x:8000/api/health");
int httpCode = http.GET();
String payload = http.getString();
Serial.println(payload); // Should print: {"status":"ok","service":"time-sense-backend"}
```

### 2. Get Access Status
```cpp
http.begin("http://192.168.x.x:8000/api/access?device_id=esp32-001");
int httpCode = http.GET();
String payload = http.getString();
// Should contain: "access":"allow" or "access":"deny"
```

### 3. Send Sensor Data
```cpp
String payload = "{\"device_id\":\"esp32-001\",\"sensor_type\":\"temperature\",\"value\":28.5}";
http.begin("http://192.168.x.x:8000/api/sensor/update");
http.addHeader("Content-Type", "application/json");
int httpCode = http.POST(payload);
```

## Troubleshooting

### ESP32 still getting ECONNRESET?

1. **Check server is running with 0.0.0.0 binding:**
   ```bash
   netstat -an | grep 8000
   # Should show: 0.0.0.0:8000
   ```

2. **Verify ESP32 IP is on same network:**
   ```bash
   ping 192.168.x.x  # From PC
   ```

3. **Test from PC on same network:**
   ```bash
   curl http://192.168.x.x:8000/api/health
   ```

4. **Check firewall:**
   - Disable firewall temporarily or allow port 8000
   - On Linux: `sudo ufw allow 8000`

5. **Check logs for errors:**
   - Look for `[API]` and `[ERROR]` messages
   - Check database connection errors

### Endpoints returning 400 Bad Request?

This is usually a payload validation issue. All ESP32 endpoints are now more lenient:
- `/api/command` - Always returns valid JSON
- `/api/sensor/update` - Accepts any payload structure
- `/api/access` - Works with or without parameters

### Connection timeout?

- Increase timeout in ESP32 code to 5-10 seconds
- Check if server is actually running with `./run_esp32_mode.sh`
- Verify no port conflicts with other services

## Architecture

```
ESP32 (192.168.x.x:XXXX)
    ↓ HTTP requests
    ↓ (ECONNRESET was happening here)
    ↓
FastAPI Server (0.0.0.0:8000) ← NOW FIXED!
    ├── /api/health (test connection)
    ├── /api/access (get access decision)
    ├── /api/command (get pending commands)
    └── /api/sensor/update (receive sensor data)
    ↓
Database (SQLite/PostgreSQL)
```

## Environment Variables

Add to `.env` if needed:

```env
# API Access Control
API_KEY=               # Leave empty for open access

# CORS Origins (will auto-allow all for ESP32)
CORS_ORIGINS=http://localhost:3000,http://192.168.x.x:3000

# Debug Logging
DEBUG=1                # Enable verbose logging
```

## Files Modified

1. ✅ `/app/main.py` - Added endpoints, error handling, logging
2. ✅ `README.md` - Updated with new instructions
3. ✅ `run_esp32_mode.sh` - New Linux/macOS startup script
4. ✅ `run_esp32_mode.bat` - New Windows startup script

## Next Steps

1. Run backend with: `./run_esp32_mode.sh` or `run_esp32_mode.bat`
2. Test `/api/health` endpoint from browser or curl
3. Update ESP32 code to use proper IP:port
4. Monitor logs for `[API]` debug messages
5. Add `/api/sensor/update` calls from ESP32 for telemetry

---

**All changes preserve existing functionality!** No UI, frontend, or database logic was modified.
