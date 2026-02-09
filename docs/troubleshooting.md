# Troubleshooting Guide

Quick reference for diagnosing and resolving common issues.

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Common Issues](#common-issues)
3. [Emergency Procedures](#emergency-procedures)
4. [Log Locations](#log-locations)

---

## Quick Diagnostics

### Raspberry Pi Health Check

```bash
# One-liner status check
echo "Temp: $(vcgencmd measure_temp) | Throttle: $(vcgencmd get_throttled) | Cams: $(ps aux | grep rpicam-vid | grep -v grep | wc -l)/2 | go2rtc: $(systemctl is-active go2rtc)"
```

### Test RTSP Streams

```bash
# Test from Pi (locally)
ffprobe rtsp://localhost:8554/{CAMERA_0_ID}

# Test from NVR (remotely)
ffprobe -rtsp_transport tcp rtsp://{PI_IP}:8554/{CAMERA_0_ID}
```

### Check Frigate Status

```bash
# Container status
docker ps | grep frigate

# API check
curl -s http://localhost:5000/api/stats | python3 -m json.tool

# Recent recordings
find /srv/frigate/storage/recordings -name "*.mp4" -mmin -10 | wc -l
```

---

## Common Issues

### 🔴 System Freeze / SSH Hangs

**Symptoms:**
- SSH sessions freeze
- Cannot connect to Pi
- System unresponsive

**Cause:** Zombie rpicam-vid processes due to wrong `KillMode`

**Solution:**

```bash
# Check current KillMode
grep KillMode /etc/systemd/system/go2rtc.service

# Must be: KillMode=control-group
# If not, edit the file:
sudo nano /etc/systemd/system/go2rtc.service

# Change to:
# KillMode=control-group

# Apply changes
sudo systemctl daemon-reload
sudo systemctl restart go2rtc
```

---

### 🔴 "No Frames Received" in Frigate

**Symptoms:**
- Frigate shows camera as offline
- "No frames received" error

**Cause:** Usually network or stream issues

**Solution:**

1. Check Pi streams are working:
```bash
curl http://{PI_IP}:1984/api/streams
```

2. Test RTSP directly:
```bash
ffprobe -rtsp_transport tcp rtsp://{PI_IP}:8554/{CAMERA_0_ID}
```

3. Restart go2rtc:
```bash
ssh {PI_USER}@{PI_IP} "sudo systemctl restart go2rtc"
```

4. Verify Frigate config uses TCP:
```yaml
input_args:
  - -rtsp_transport
  - tcp
```

---

### 🔴 Frigate 100% CPU Usage

**Symptoms:**
- High CPU on NVR
- Sluggish web interface
- Frame drops

**Cause:** Hardware acceleration not active

**Solution:**

1. Verify GPU access:
```bash
ls -la /dev/dri
```

2. Check docker-compose.yml has:
```yaml
devices:
  - /dev/dri:/dev/dri
group_add:
  - "992"  # render group
  - "44"   # video group
```

3. Check Frigate config has:
```yaml
ffmpeg:
  hwaccel_args: preset-intel-qsv-h264
```

4. Verify QSV is active:
```bash
curl http://localhost:5000/api/stats | grep -i intel
```

5. Restart Frigate:
```bash
docker compose restart frigate
```

---

### 🔴 Docker Memory Errors

**Symptoms:**
- Container crashes
- "Cannot allocate memory" errors

**Cause:** Usually disk full or insufficient shared memory

**Solution:**

1. Check disk space:
```bash
df -h /srv/frigate/storage
```

2. Clean old recordings:
```bash
find /srv/frigate/storage/recordings -name "*.mp4" -mtime +7 -delete
```

3. Increase shm_size in docker-compose.yml:
```yaml
shm_size: "512mb"
```

4. Restart:
```bash
docker compose down && docker compose up -d
```

---

### 🟡 High Temperature on Pi

**Symptoms:**
- Temperature > 70°C
- Throttling detected

**Solution:**

1. Check current temperature:
```bash
vcgencmd measure_temp
```

2. Check throttling:
```bash
vcgencmd get_throttled
# 0x0 = OK
# Other values = throttling occurred
```

3. Reduce load:
```bash
# Edit go2rtc.yaml
# Reduce framerate: --framerate 10 (from 15)
# Reduce resolution: --width 800 --height 600
```

4. Improve cooling:
   - Add heatsink
   - Add active fan
   - Improve ventilation

---

### 🟡 Camera Not Detected

**Symptoms:**
- `rpicam-hello --list-cameras` shows no cameras
- Camera process not starting

**Solution:**

1. Check physical connection
2. Check camera cable orientation (blue side up)
3. Verify not using legacy camera mode:
```bash
# Should NOT have: start_x=1, gpu_mem=128 with camera_auto_detect
# In /boot/firmware/config.txt
```

4. Reboot:
```bash
sudo reboot
```

---

### 🟡 Stream Delays / Latency

**Symptoms:**
- Video is several seconds behind real-time

**Solution:**

1. Reduce buffer in Frigate config:
```yaml
input_args:
  - -buffer_size
  - "262144"  # Reduce from 512000
  - -max_delay
  - "250000"  # Reduce from 500000
```

2. Or use WebRTC for live viewing (lower latency than RTSP)

---

## Emergency Procedures

### Emergency Restart (Pi)

```bash
sudo systemctl stop go2rtc
sudo pkill -9 rpicam-vid
sudo systemctl start go2rtc
```

### Emergency Restart (Frigate)

```bash
docker compose down
docker compose up -d
```

### Full System Recovery

```bash
# On Pi
sudo systemctl stop go2rtc
sudo pkill -9 rpicam-vid go2rtc
sudo systemctl daemon-reload
sudo systemctl start go2rtc

# On NVR
docker compose down
docker system prune -f
docker compose up -d
```

### Rollback Configuration

```bash
# On Pi - restore backup
sudo cp /opt/go2rtc/go2rtc.yaml.backup /opt/go2rtc/go2rtc.yaml
sudo systemctl restart go2rtc

# On NVR - restore backup
cp /srv/frigate/config/config.yml.backup /srv/frigate/config/config.yml
docker compose restart frigate
```

---

## Log Locations

### Raspberry Pi

| Log | Command |
|-----|---------|
| go2rtc service | `journalctl -u go2rtc.service -f` |
| System log | `journalctl -f` |
| Watchdog log | `cat ~/watchdog.log` |

### NVR Server

| Log | Command |
|-----|---------|
| Frigate | `docker logs frigate -f` |
| Docker | `journalctl -u docker -f` |

### Log Analysis Tips

```bash
# Find errors in go2rtc logs
journalctl -u go2rtc --since "1 hour ago" | grep -i error

# Find Frigate errors
docker logs frigate 2>&1 | grep -i error | tail -50

# Check for camera disconnections
journalctl -u go2rtc | grep -i "disconnect\|fail\|error"
```

---

## Known Limitations

| Issue | Status | Workaround |
|-------|--------|------------|
| H.265 causes kernel panic | Hardware limitation | Use H.264 only |
| WiFi unreliable for RTSP | Expected | Use Ethernet |
| USB cameras not supported | By design | Use CSI cameras |
| 4K not stable 24/7 | Resource limitation | Use 1080p or lower |

---

## Getting Help

If issues persist:

1. Check all logs for error messages
2. Run the validation script: `./scripts/validate-system.sh`
3. Capture system state:
```bash
# On Pi
vcgencmd measure_temp
vcgencmd get_throttled
systemctl status go2rtc
journalctl -u go2rtc --since "30 min ago"

# On NVR
docker logs frigate --tail 100
```
4. Search [Frigate GitHub Issues](https://github.com/blakeblackshear/frigate/issues)
5. Search [go2rtc GitHub Issues](https://github.com/AlexxIT/go2rtc/issues)
