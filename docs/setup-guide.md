# Complete Setup Guide

Step-by-step instructions for deploying the NeuroSurveillance system.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Raspberry Pi Setup](#raspberry-pi-setup)
3. [NVR Server Setup](#nvr-server-setup)
4. [Verification](#verification)
5. [Post-Installation](#post-installation)

---

## Prerequisites

### Hardware Requirements

**Raspberry Pi 5:**
- Raspberry Pi 5 (4GB or 8GB RAM)
- Official Pi 5 power supply (5V/5A)
- Two Raspberry Pi Camera Module v2 or v3
- MicroSD card (32GB+ recommended)
- Ethernet cable (WiFi not recommended)
- Heatsink or active cooling (recommended for 24/7 operation)

**NVR Server:**
- Intel-based PC/server (6th gen or newer for QSV)
- Ubuntu 22.04 LTS or similar
- Minimum 8GB RAM
- Storage: ~50GB per camera per week at default settings
- Ethernet connection

### Software Requirements

**Raspberry Pi:**
- Raspberry Pi OS Lite (64-bit) - Bookworm or newer
- SSH enabled

**NVR Server:**
- Docker Engine 24.0+
- Docker Compose v2.0+

---

## Raspberry Pi Setup

### Step 1: Flash Raspberry Pi OS

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Select "Raspberry Pi OS Lite (64-bit)"
3. Click the gear icon for advanced options:
   - Set hostname
   - Enable SSH
   - Set username and password
   - Configure WiFi (optional, for initial setup only)
4. Flash to SD card

### Step 2: Initial Configuration

```bash
# SSH into the Pi
ssh {PI_USER}@{PI_IP}

# Update system
sudo apt update && sudo apt full-upgrade -y

# Install dependencies
sudo apt install -y curl wget ffmpeg

# Verify cameras are detected
rpicam-hello --list-cameras
# Should show 2 cameras
```

### Step 3: Network Configuration

Configure a static IP address:

```bash
sudo nano /etc/dhcpcd.conf
```

Add at the end:
```
interface eth0
static ip_address={PI_IP}/24
static routers={GATEWAY_IP}
static domain_name_servers={DNS_IP}
```

### Step 4: Install go2rtc

```bash
# Create directory
sudo mkdir -p /opt/go2rtc
cd /opt/go2rtc

# Download latest go2rtc
sudo wget https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64
sudo mv go2rtc_linux_arm64 go2rtc
sudo chmod +x go2rtc

# Set ownership
sudo chown -R {PI_USER}:video /opt/go2rtc
```

### Step 5: Configure go2rtc

Copy the configuration file:

```bash
sudo nano /opt/go2rtc/go2rtc.yaml
```

Paste the contents from `configs/go2rtc.yaml`, replacing all `{VARIABLES}`.

**Test the configuration:**

```bash
# Run manually to test
/opt/go2rtc/go2rtc -config /opt/go2rtc/go2rtc.yaml

# In another terminal, verify streams
curl http://localhost:1984/api/streams

# Press Ctrl+C to stop
```

### Step 6: Create Systemd Service

```bash
sudo nano /etc/systemd/system/go2rtc.service
```

Paste the contents from `configs/go2rtc.service`, replacing `{PI_USER}`.

**Enable and start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable go2rtc.service
sudo systemctl start go2rtc.service

# Verify status
sudo systemctl status go2rtc.service
```

### Step 7: Boot Configuration

```bash
# Backup existing config
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.backup

# Edit boot config
sudo nano /boot/firmware/config.txt
```

Append the contents from `configs/config.txt` to the end.

**Reboot:**

```bash
sudo reboot
```

### Step 8: Verify Pi Setup

After reboot:

```bash
# Check temperature
vcgencmd measure_temp
# Should be < 70°C

# Check throttling
vcgencmd get_throttled
# Should be 0x0

# Check GPU memory
vcgencmd get_mem gpu
# Should be gpu=128M

# Check cameras
ps aux | grep rpicam-vid | grep -v grep | wc -l
# Should be 2

# Check streams
curl http://localhost:1984/api/streams
```

---

## NVR Server Setup

### Step 1: Install Docker

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Add user to docker group
sudo usermod -aG docker $USER

# Log out and back in, then verify
docker --version
docker compose version
```

### Step 2: Create Directory Structure

```bash
sudo mkdir -p /srv/frigate/{config,storage}
cd /srv/frigate
sudo chown -R $USER:$USER /srv/frigate
```

### Step 3: Verify GPU Access

```bash
# Check for Intel GPU
ls -la /dev/dri

# Get group IDs
getent group render
getent group video

# Note these numbers for docker-compose.yml
```

### Step 4: Configure Frigate

Copy and edit docker-compose.yml:

```bash
nano /srv/frigate/docker-compose.yml
```

Paste contents from `configs/docker-compose.yml`, updating:
- `{RENDER_GROUP_ID}` and `{VIDEO_GROUP_ID}` with actual values
- `{TIMEZONE}` with your timezone

Copy and edit Frigate config:

```bash
nano /srv/frigate/config/config.yml
```

Paste contents from `configs/frigate-config.yml`, updating all variables.

### Step 5: Start Frigate

```bash
cd /srv/frigate
docker compose up -d

# Watch logs for errors
docker compose logs -f frigate

# Press Ctrl+C when satisfied
```

### Step 6: Verify Frigate

```bash
# Check container status
docker ps

# Check API
curl http://localhost:5000/api/stats

# Check for QSV
curl http://localhost:5000/api/stats | grep -i intel
```

Access web UI: `http://{NVR_IP}:5000`

---

## Verification

Run the validation script:

```bash
chmod +x scripts/validate-system.sh
./scripts/validate-system.sh
```

All checks should pass.

### Manual Verification Checklist

- [ ] Pi accessible via SSH
- [ ] Temperature < 70°C
- [ ] No throttling (0x0)
- [ ] go2rtc service running
- [ ] 2 camera processes running
- [ ] RTSP streams accessible
- [ ] Frigate container running
- [ ] Frigate web UI accessible
- [ ] QSV acceleration active
- [ ] Recordings being created

---

## Post-Installation

### Install Monitoring Script

On Raspberry Pi:

```bash
# Copy watchdog script
nano ~/watchdog.sh
# Paste contents from scripts/watchdog.sh

chmod +x ~/watchdog.sh

# Add to crontab
crontab -e

# Add these lines:
*/5 * * * * /home/{PI_USER}/watchdog.sh
0 */4 * * * sudo systemctl restart go2rtc
```

### Install Health Check

On NVR server:

```bash
# Copy health check script
sudo cp scripts/health-check.sh /srv/frigate/
sudo chmod +x /srv/frigate/health-check.sh

# Set up SSH key authentication to Pi
ssh-keygen -t rsa
ssh-copy-id {PI_USER}@{PI_IP}

# Test
/srv/frigate/health-check.sh
```

### Configure Backups

Consider backing up:
- `/opt/go2rtc/go2rtc.yaml` (Pi)
- `/srv/frigate/config/config.yml` (NVR)
- `/srv/frigate/docker-compose.yml` (NVR)

### Set Up Alerts (Optional)

For email alerts on failures, add to your monitoring scripts:
```bash
# Example: Send email on failure
if [ $FAIL_COUNT -gt 0 ]; then
    echo "System check failed" | mail -s "Surveillance Alert" your@email.com
fi
```

---

## Next Steps

- Read [Troubleshooting Guide](troubleshooting.md) for common issues
- Review [Video Parameters](video-parameters.md) to optimize settings
- Set up regular backup procedures
- Configure retention settings based on storage capacity
