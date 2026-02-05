#!/bin/bash
# =============================================================================
# Full System Validation Script - NeuroSurveillance System
# =============================================================================
# Location: Run from any machine with network access to both Pi and NVR
#
# This script performs comprehensive validation of the entire surveillance
# system. Use after deployment or when troubleshooting issues.
#
# IMPORTANT: Replace all {VARIABLES} with your actual values.
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
PI_IP="{PI_IP}"
NVR_IP="{NVR_IP}"
RTSP_PORT="8554"
CAMERA_0="{CAMERA_0_ID}"
CAMERA_1="{CAMERA_1_ID}"

# -----------------------------------------------------------------------------
# Result Tracking
# -----------------------------------------------------------------------------
PASS=()
FAIL=()
WARN=()

# -----------------------------------------------------------------------------
# Test Functions
# -----------------------------------------------------------------------------
check() {
    local desc="$1"
    shift

    if "$@" >/dev/null 2>&1; then
        PASS+=("$desc")
        return 0
    else
        FAIL+=("$desc")
        return 1
    fi
}

check_warn() {
    local desc="$1"
    shift

    if "$@" >/dev/null 2>&1; then
        PASS+=("$desc")
        return 0
    else
        WARN+=("$desc")
        return 1
    fi
}

# -----------------------------------------------------------------------------
# Banner
# -----------------------------------------------------------------------------
echo "=============================================="
echo "  NeuroSurveillance System Validation"
echo "=============================================="
echo ""
echo "Pi IP:  $PI_IP"
echo "NVR IP: $NVR_IP"
echo "Time:   $(date)"
echo ""

# -----------------------------------------------------------------------------
# Network Tests
# -----------------------------------------------------------------------------
echo ">>> Network Connectivity"

check "Ping Raspberry Pi" ping -c 1 -W 2 "$PI_IP"
check "Ping NVR Server" ping -c 1 -W 2 "$NVR_IP"

# -----------------------------------------------------------------------------
# Raspberry Pi Tests
# -----------------------------------------------------------------------------
echo ">>> Raspberry Pi Services"

check "go2rtc API responding" curl -sf "http://$PI_IP:1984/api/streams"

# -----------------------------------------------------------------------------
# RTSP Stream Tests
# -----------------------------------------------------------------------------
echo ">>> RTSP Streams"

check "RTSP stream: $CAMERA_0" \
    timeout 10 ffprobe -v error -rtsp_transport tcp "rtsp://$PI_IP:$RTSP_PORT/$CAMERA_0"

check "RTSP stream: $CAMERA_1" \
    timeout 10 ffprobe -v error -rtsp_transport tcp "rtsp://$PI_IP:$RTSP_PORT/$CAMERA_1"

# -----------------------------------------------------------------------------
# Frigate Tests
# -----------------------------------------------------------------------------
echo ">>> Frigate NVR"

check "Frigate container running" \
    docker ps --filter name=frigate --format '{{.Names}}' | grep -q '^frigate$'

check "Frigate API responding" \
    curl -sf "http://$NVR_IP:5000/api/stats"

check_warn "Intel QSV active" \
    bash -c "curl -sf http://$NVR_IP:5000/api/stats | grep -qi intel"

# -----------------------------------------------------------------------------
# Recording Tests
# -----------------------------------------------------------------------------
echo ">>> Recording Status"

check_warn "Recent recordings exist" \
    bash -c "curl -sf http://$NVR_IP:5000/api/stats | grep -q 'recording'"

# -----------------------------------------------------------------------------
# Results Summary
# -----------------------------------------------------------------------------
echo ""
echo "=============================================="
echo "  VALIDATION RESULTS"
echo "=============================================="
echo ""

# Print passes
if [ ${#PASS[@]} -gt 0 ]; then
    echo "PASSED (${#PASS[@]}):"
    for p in "${PASS[@]}"; do
        echo "  [✓] $p"
    done
    echo ""
fi

# Print warnings
if [ ${#WARN[@]} -gt 0 ]; then
    echo "WARNINGS (${#WARN[@]}):"
    for w in "${WARN[@]}"; do
        echo "  [!] $w"
    done
    echo ""
fi

# Print failures
if [ ${#FAIL[@]} -gt 0 ]; then
    echo "FAILED (${#FAIL[@]}):"
    for f in "${FAIL[@]}"; do
        echo "  [✗] $f"
    done
    echo ""
fi

# -----------------------------------------------------------------------------
# Final Status
# -----------------------------------------------------------------------------
echo "=============================================="
if [ ${#FAIL[@]} -eq 0 ] && [ ${#WARN[@]} -eq 0 ]; then
    echo "  STATUS: ALL CHECKS PASSED ✓"
    echo "=============================================="
    exit 0
elif [ ${#FAIL[@]} -eq 0 ]; then
    echo "  STATUS: PASSED WITH WARNINGS"
    echo "=============================================="
    exit 0
else
    echo "  STATUS: VALIDATION FAILED"
    echo "=============================================="
    echo ""
    echo "Troubleshooting steps:"
    echo "1. Check docs/troubleshooting.md for common issues"
    echo "2. Verify all services are running"
    echo "3. Check logs: journalctl -u go2rtc -n 50"
    echo "4. Check Frigate: docker logs frigate --tail 50"
    exit 1
fi

# =============================================================================
# USAGE
# =============================================================================
#
# 1. Edit the configuration variables at the top of this script
#
# 2. Make executable:
#    chmod +x validate-system.sh
#
# 3. Run:
#    ./validate-system.sh
#
# 4. For automated testing, capture exit code:
#    ./validate-system.sh && echo "System OK" || echo "System has issues"
#
# =============================================================================
