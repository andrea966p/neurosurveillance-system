#!/bin/bash
# =============================================================================
# go2rtc Watchdog Script - NeuroSurveillance System
# =============================================================================
# Location: /home/{PI_USER}/watchdog.sh
#
# This script monitors go2rtc and automatically restarts it if issues are
# detected. Run via cron every 5 minutes for continuous monitoring.
#
# IMPORTANT: Replace {PI_USER} with your actual username before deploying.
# =============================================================================

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
LOG_FILE="/home/{PI_USER}/watchdog.log"
MAX_CPU=50          # Restart if rpicam-vid exceeds this CPU %
MAX_MEM_MB=600      # Restart if go2rtc exceeds this memory (MB)
API_URL="http://localhost:1984/api/streams"

# -----------------------------------------------------------------------------
# Logging Function
# -----------------------------------------------------------------------------
log_message() {
    echo "[$(date -Iseconds)] $1" >> "$LOG_FILE"
}

# -----------------------------------------------------------------------------
# Check: Is go2rtc running?
# -----------------------------------------------------------------------------
if ! systemctl is-active --quiet go2rtc; then
    log_message "WARNING: go2rtc is not running, starting it..."
    sudo systemctl start go2rtc
    exit 0
fi

# -----------------------------------------------------------------------------
# Check: rpicam-vid CPU usage
# -----------------------------------------------------------------------------
# If any rpicam-vid process exceeds MAX_CPU, restart go2rtc
for pid in $(pgrep rpicam-vid); do
    cpu_usage=$(ps -p "$pid" -o %cpu= 2>/dev/null | tr -d ' ')
    if [ -n "$cpu_usage" ]; then
        cpu_int=${cpu_usage%.*}

        if [ "$cpu_int" -gt "$MAX_CPU" ]; then
            log_message "WARNING: rpicam-vid PID $pid using ${cpu_usage}% CPU (threshold: ${MAX_CPU}%), restarting go2rtc..."
            sudo systemctl restart go2rtc
            exit 0
        fi
    fi
done

# -----------------------------------------------------------------------------
# Check: go2rtc memory usage
# -----------------------------------------------------------------------------
go2rtc_pid=$(pgrep -x go2rtc)
if [ -n "$go2rtc_pid" ]; then
    mem_kb=$(ps -p "$go2rtc_pid" -o rss= 2>/dev/null | tr -d ' ')
    if [ -n "$mem_kb" ]; then
        mem_mb=$((mem_kb / 1024))

        if [ "$mem_mb" -gt "$MAX_MEM_MB" ]; then
            log_message "WARNING: go2rtc using ${mem_mb}MB memory (threshold: ${MAX_MEM_MB}MB), restarting..."
            sudo systemctl restart go2rtc
            exit 0
        fi
    fi
fi

# -----------------------------------------------------------------------------
# Check: API responsiveness
# -----------------------------------------------------------------------------
# Check: API responsiveness (with retry)
# -----------------------------------------------------------------------------
for i in {1..3}; do
    if curl -sf "$API_URL" > /dev/null 2>&1; then
        api_ok=true
        break
    fi
    sleep 2
done

if [ "$api_ok" != "true" ]; then
    log_message "ERROR: go2rtc API not responding at $API_URL after 3 attempts, restarting..."
    sudo systemctl restart go2rtc
    exit 0
fi

# -----------------------------------------------------------------------------
# Check: Camera processes
# -----------------------------------------------------------------------------
camera_count=$(pgrep rpicam-vid | wc -l)
if [ "$camera_count" -lt 2 ]; then
    log_message "WARNING: Only $camera_count camera(s) running (expected 2), restarting go2rtc..."
    sudo systemctl restart go2rtc
    exit 0
fi

# All checks passed - optional: log success periodically
# Uncomment the following line for verbose logging:
# log_message "INFO: All checks passed - go2rtc healthy"

exit 0

# =============================================================================
# INSTALLATION
# =============================================================================
#
# 1. Copy script to Pi:
#    scp watchdog.sh {PI_USER}@{PI_IP}:~/
#
# 2. Make executable:
#    chmod +x ~/watchdog.sh
#
# 3. Test manually:
#    ./watchdog.sh
#    cat ~/watchdog.log
#
# 4. Add to crontab:
#    crontab -e
#
#    # Add these lines:
#    # Run watchdog every 5 minutes
#    */5 * * * * /home/{PI_USER}/watchdog.sh
#
#    # Optional: Preventive restart every 4 hours
#    0 */4 * * * sudo systemctl restart go2rtc
#
# =============================================================================
# LOG ROTATION
# =============================================================================
#
# To prevent log file from growing too large, add to crontab:
#
#    # Rotate log weekly, keep 4 weeks
#    0 0 * * 0 mv /home/{PI_USER}/watchdog.log /home/{PI_USER}/watchdog.log.old
#
# Or use logrotate by creating /etc/logrotate.d/watchdog:
#
#    /home/{PI_USER}/watchdog.log {
#        weekly
#        rotate 4
#        compress
#        missingok
#        notifempty
#    }
#
# =============================================================================
