# NeuroSurveillance System

A production-ready video surveillance system designed for neuroscience research labs, featuring dual Raspberry Pi 5 cameras streaming to Frigate NVR with Intel QSV hardware acceleration.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%205-red.svg)
![Frigate](https://img.shields.io/badge/Frigate-0.14+-green.svg)

## Overview

This system provides 24/7 video recording for behavioral analysis in research environments. It's battle-tested for continuous operation with automatic recovery, hardware watchdog, and optimized for minimal resource usage.

### Key Features

- **Dual Camera Support**: Two Pi Camera modules per Raspberry Pi 5
- **H.264 Hardware Encoding**: Stable, efficient encoding via libav
- **Intel QSV Decoding**: GPU-accelerated processing on NVR (9-12% CPU vs 100%)
- **Automatic Recovery**: Hardware watchdog + monitoring scripts
- **TCP RTSP Transport**: Reliable streaming without frame drops
- **7-Day Retention**: Configurable recording retention

### Architecture

```
┌─────────────────────┐         RTSP/TCP          ┌─────────────────────┐
│   Raspberry Pi 5    │ ──────────────────────────│    NVR Server       │
│                     │    192.168.x.x:8554       │    (Ubuntu/Docker)  │
│  ┌───────────────┐  │                           │                     │
│  │ Camera 0      │  │                           │  ┌───────────────┐  │
│  │ (pi_cam_0)    │──│───────────────────────────│──│   Frigate     │  │
│  └───────────────┘  │                           │  │   Container   │  │
│  ┌───────────────┐  │                           │  │               │  │
│  │ Camera 1      │──│───────────────────────────│──│  Intel QSV    │  │
│  │ (pi_cam_1)    │  │                           │  │  HW Accel     │  │
│  └───────────────┘  │                           │  └───────────────┘  │
│                     │                           │                     │
│  go2rtc + ffmpeg    │                           │  Web UI :5000       │
│  Port 1984 (API)    │                           │  RTSP   :8554       │
│  Port 8554 (RTSP)   │                           │  WebRTC :8555       │
└─────────────────────┘                           └─────────────────────┘
```

## Quick Start

### Prerequisites

**Raspberry Pi 5:**
- Raspberry Pi OS Lite (64-bit)
- Two Pi Camera modules connected
- Ethernet connection (WiFi not recommended)
- Static IP configured

**NVR Server:**
- Ubuntu 22.04+ or similar
- Docker & Docker Compose
- Intel CPU with QSV support (6th gen+)

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/neurosurveillance-system.git
cd neurosurveillance-system
```

### 2. Configure Variables

Copy and edit the configuration files, replacing all `{VARIABLES}`:

| Variable | Description | Example |
|----------|-------------|---------|
| `{PI_IP}` | Raspberry Pi static IP | `192.168.1.100` |
| `{PI_USER}` | Pi username | `pi` |
| `{PI_HOME}` | Pi home directory | `/home/pi` |
| `{NVR_IP}` | NVR server IP | `192.168.1.50` |
| `{CAMERA_0_ID}` | First camera stream name | `pi_cam_0` |
| `{CAMERA_1_ID}` | Second camera stream name | `pi_cam_1` |
| `{TIMEZONE}` | Your timezone | `America/New_York` |

### 3. Deploy to Raspberry Pi

```bash
# Copy go2rtc binary
sudo mkdir -p /opt/go2rtc
sudo wget -O /opt/go2rtc/go2rtc https://github.com/AlexxIT/go2rtc/releases/latest/download/go2rtc_linux_arm64
sudo chmod +x /opt/go2rtc/go2rtc

# Copy configuration (edit variables first!)
sudo cp configs/go2rtc.yaml /opt/go2rtc/
sudo cp configs/go2rtc.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable go2rtc
sudo systemctl start go2rtc
```

### 4. Deploy Frigate on NVR

```bash
# On your NVR server
mkdir -p /srv/frigate/{config,storage}
cd /srv/frigate

# Copy configurations (edit variables first!)
cp configs/docker-compose.yml .
cp configs/frigate-config.yml config/config.yml

# Start Frigate
docker compose up -d
```

### 5. Verify

```bash
# Test Pi streams
curl http://{PI_IP}:1984/api/streams

# Test Frigate
curl http://{NVR_IP}:5000/api/stats

# Open Frigate UI
# http://{NVR_IP}:5000
```

## Configuration Files

| File | Location | Purpose |
|------|----------|---------|
| `go2rtc.yaml` | `/opt/go2rtc/` | Camera streaming configuration |
| `go2rtc.service` | `/etc/systemd/system/` | Systemd service with process management |
| `config.txt` | `/boot/firmware/` | Pi boot hardening (append to existing) |
| `docker-compose.yml` | `/srv/frigate/` | Frigate container setup |
| `frigate-config.yml` | `/srv/frigate/config/` | Frigate recording settings |

## Documentation

- [Complete Setup Guide](docs/setup-guide.md) - Step-by-step deployment
- [Troubleshooting Guide](docs/troubleshooting.md) - Common issues and solutions
- [Video Parameters](docs/video-parameters.md) - Resolution, FPS, bitrate options

## Critical Configuration Notes

### ⚠️ H.264 Only - Never Use H.265

H.265/HEVC encoding causes kernel panics on Raspberry Pi 5. Always use:
```yaml
--codec libav --libav-format h264
```

### ⚠️ KillMode=control-group is Mandatory

The systemd service MUST use `KillMode=control-group` to properly terminate child processes. Without this, zombie `rpicam-vid` processes will accumulate and freeze the system.

### ⚠️ TCP Transport Required

Always use TCP for RTSP transport to prevent frame drops:
```yaml
input_args:
  - -rtsp_transport
  - tcp
```

## Performance Expectations

### Raspberry Pi 5 (with proper config)
| Metric | Value |
|--------|-------|
| CPU Usage | 20-30% |
| Memory | 400-500 MB |
| Temperature | 55-60°C |
| Network | 3-4 Mbps |

### NVR Server (with Intel QSV)
| Metric | Value |
|--------|-------|
| CPU Usage | 9-12% |
| GPU Usage | 3-4% |
| Memory | ~870 MB |
| Disk I/O | 3-4 MB/s |

## Monitoring & Recovery

The system includes automatic monitoring and recovery:

1. **Hardware Watchdog**: Auto-reboots Pi on system freeze
2. **Monitoring Script**: Checks CPU, memory, API response every 5 minutes
3. **Scheduled Restart**: Preventive restart every 4 hours
4. **Health Checks**: System validation scripts

See [scripts/](scripts/) for monitoring implementations.

## Storage Calculator

```
Daily Storage = Bitrate(Mbps) × 24 × 3600 × Cameras ÷ 8 (bytes to bits)

Examples:
- 2 cameras @ 1.5 Mbps = ~32 GB/day
- 2 cameras @ 1.0 Mbps = ~22 GB/day
- 4 cameras @ 1.5 Mbps = ~65 GB/day
```

With 7-day retention: multiply by 7 for total storage needed.

## Project Structure

```
neurosurveillance-system/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── configs/
│   ├── go2rtc.yaml           # go2rtc streaming config
│   ├── go2rtc.service        # systemd service
│   ├── config.txt            # Pi boot hardening
│   ├── docker-compose.yml    # Frigate Docker setup
│   └── frigate-config.yml    # Frigate NVR config
├── scripts/
│   ├── watchdog.sh           # Monitoring script
│   ├── health-check.sh       # System health check
│   └── validate-system.sh    # Full validation
└── docs/
    ├── setup-guide.md        # Complete setup instructions
    ├── troubleshooting.md    # Problem solving guide
    └── video-parameters.md   # Video configuration options
```

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- [go2rtc](https://github.com/AlexxIT/go2rtc) - Excellent RTSP streaming server
- [Frigate](https://github.com/blakeblackshear/frigate) - Outstanding NVR solution
- Raspberry Pi Foundation for the Pi 5 and camera modules
