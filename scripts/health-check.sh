#!/bin/bash
# =============================================================================
# System Health Check Script - NeuroSurveillance System
# =============================================================================
# Location: /srv/frigate/health-check.sh (on NVR server)
#
# Comprehensive health check for the entire surveillance system.
# Checks both Raspberry Pi and Frigate NVR components.
#
# IMPORTANT: Replace all {VARIABLES} with your actual values.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
PI_IP="{PI_IP}"
PI_USER="{PI_USER}"
FRIGATE_URL="http://localhost:5000"
RTSP_PORT="8554"
CAMERA_0="{CAMERA_0_ID}"
CAMERA_1="{CAMERA_1_ID}"
RECORDINGS_DIR="/srv/frigate/storage/recordings"

# Output formatting
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
print_header() {
    echo ""
    echo "========================================"
    echo " $1"
    echo "========================================"
}

check_pass() {
    echo -e "[${GREEN}✓${NC}] $1"
}

check_fail() {
    echo -e "[${RED}✗${NC}] $1"
}

check_warn() {
    echo -e "[${YELLOW}!${NC}] $1"
}

# -----------------------------------------------------------------------------
# Raspberry Pi Checks
# -----------------------------------------------------------------------------
print_header "RASPBERRY PI HEALTH"

# Ping test
if ping -c 1 -W 2 "$PI_IP" > /dev/null 2>&1; then
    check_pass "Pi reachable at $PI_IP"
else
    check_fail "Pi unreachable at $PI_IP"
fi

# SSH and temperature check
if temp=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$PI_USER@$PI_IP" "vcgencmd measure_temp" 2>/dev/null); then
    temp_val=$(echo "$temp" | grep -oP '\d+\.\d+')
    if (( $(echo "$temp_val < 70" | bc -l) )); then
        check_pass "Temperature: $temp"
    else
        check_warn "Temperature HIGH: $temp"
    fi
else
    check_fail "Cannot SSH to Pi"
fi

# Throttling check
if throttle=$(ssh -o ConnectTimeout=5 "$PI_USER@$PI_IP" "vcgencmd get_throttled" 2>/dev/null); then
    if [[ "$throttle" == *"0x0"* ]]; then
        check_pass "No throttling detected"
    else
        check_warn "Throttling detected: $throttle"
    fi
fi

# go2rtc service check
if ssh -o ConnectTimeout=5 "$PI_USER@$PI_IP" "systemctl is-active --quiet go2rtc" 2>/dev/null; then
    check_pass "go2rtc service running"
else
    check_fail "go2rtc service NOT running"
fi

# Camera process check
cam_count=$(ssh -o ConnectTimeout=5 "$PI_USER@$PI_IP" "pgrep rpicam-vid | wc -l" 2>/dev/null || echo "0")
if [ "$cam_count" -eq 2 ]; then
    check_pass "Camera processes: $cam_count/2"
else
    check_fail "Camera processes: $cam_count/2 (expected 2)"
fi

# go2rtc API check
if curl -sf "http://$PI_IP:1984/api/streams" > /dev/null 2>&1; then
    check_pass "go2rtc API responding"
else
    check_fail "go2rtc API not responding"
fi

# -----------------------------------------------------------------------------
# RTSP Stream Checks
# -----------------------------------------------------------------------------
print_header "RTSP STREAMS"

for stream in "$CAMERA_0" "$CAMERA_1"; do
    if timeout 5 ffprobe -v error -rtsp_transport tcp "rtsp://$PI_IP:$RTSP_PORT/$stream" 2>&1 | grep -q "Stream #0"; then
        check_pass "Stream $stream: OK"
    else
        check_fail "Stream $stream: FAILED"
    fi
done

# -----------------------------------------------------------------------------
# Frigate NVR Checks
# -----------------------------------------------------------------------------
print_header "FRIGATE NVR"

# Container status
if docker ps --filter name=frigate --format '{{.Names}}' | grep -q '^frigate$'; then
    check_pass "Frigate container running"
else
    check_fail "Frigate container NOT running"
fi

# Frigate API
if curl -sf "$FRIGATE_URL/api/stats" > /dev/null 2>&1; then
    check_pass "Frigate API responding"

    # Check QSV
    if curl -sf "$FRIGATE_URL/api/stats" | grep -qi "intel"; then
        check_pass "Intel QSV acceleration active"
    else
        check_warn "QSV acceleration may not be active"
    fi
else
    check_fail "Frigate API not responding"
fi

# Docker resource usage
echo ""
echo "Container Resources:"
docker stats frigate --no-stream --format "  CPU: {{.CPUPerc}}  Memory: {{.MemUsage}}"

# -----------------------------------------------------------------------------
# Storage Checks
# -----------------------------------------------------------------------------
print_header "STORAGE"

# Disk usage
disk_usage=$(df -h "$RECORDINGS_DIR" 2>/dev/null | tail -1 | awk '{print $5}' | tr -d '%')
if [ -n "$disk_usage" ]; then
    if [ "$disk_usage" -lt 80 ]; then
        check_pass "Disk usage: ${disk_usage}%"
    elif [ "$disk_usage" -lt 90 ]; then
        check_warn "Disk usage: ${disk_usage}% (getting full)"
    else
        check_fail "Disk usage: ${disk_usage}% (CRITICAL)"
    fi
fi

# Recent recordings
recent=$(find "$RECORDINGS_DIR" -name "*.mp4" -mmin -10 2>/dev/null | wc -l)
if [ "$recent" -gt 0 ]; then
    check_pass "Recent recordings (last 10min): $recent files"
else
    check_warn "No recordings in last 10 minutes"
fi

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
print_header "HEALTH CHECK COMPLETE"
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# =============================================================================
# INSTALLATION
# =============================================================================
#
# 1. Copy to NVR server:
#    sudo cp health-check.sh /srv/frigate/
#    sudo chmod +x /srv/frigate/health-check.sh
#
# 2. Set up SSH key authentication to Pi (no password):
#    ssh-keygen -t rsa (if not already done)
#    ssh-copy-id {PI_USER}@{PI_IP}
#
# 3. Run manually:
#    /srv/frigate/health-check.sh
#
# 4. Optional: Schedule via cron:
#    crontab -e
#    # Run every 15 minutes
#    */15 * * * * /srv/frigate/health-check.sh >> /srv/frigate/health.log 2>&1
#
# =============================================================================
