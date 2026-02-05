# Video Parameters Guide

Reference for configuring video resolution, framerate, and bitrate settings.

## Current Default Settings

| Parameter | Value | Notes |
|-----------|-------|-------|
| Resolution | 1024×768 | XGA format |
| Frame Rate | 15 fps | Balanced |
| Bitrate | 1.5 Mbps | ~16 GB/camera/day |
| Codec | H.264 | Required (no H.265!) |

---

## Resolution Options

| Setting | Resolution | Parameters | Storage/Day | Use Case |
|---------|------------|------------|-------------|----------|
| **HD** | 1280×720 | `--width 1280 --height 720` | ~20 GB | High detail analysis |
| **Standard** | 1024×768 | `--width 1024 --height 768` | ~16 GB | Default, balanced |
| **Efficient** | 800×600 | `--width 800 --height 600` | ~12 GB | Long-term studies |
| **Minimal** | 640×480 | `--width 640 --height 480` | ~8 GB | Extended recording |

### Choosing Resolution

- **Behavioral analysis**: 1024×768 or higher
- **General monitoring**: 800×600
- **Storage constrained**: 640×480

---

## Frame Rate Options

| FPS | Parameter | Storage Impact | Use Case |
|-----|-----------|----------------|----------|
| **30** | `--framerate 30` | +100% | Smooth motion, high detail |
| **15** | `--framerate 15` | Baseline | Default, good balance |
| **10** | `--framerate 10` | -33% | General monitoring |
| **5** | `--framerate 5` | -67% | Minimal storage |

### Choosing Frame Rate

- **Fast movement analysis**: 30 fps
- **Behavioral observation**: 15 fps (recommended)
- **Static scenes**: 10 fps
- **Very long recordings**: 5 fps

### Frame Rate and CPU

Higher frame rates increase CPU usage:
- 30 fps: ~35-40% CPU
- 15 fps: ~20-25% CPU
- 10 fps: ~15-20% CPU

---

## Bitrate Options

| Quality | Bitrate | Parameter | File Size |
|---------|---------|-----------|-----------|
| **High** | 3 Mbps | `--bitrate 3000000` | ~32 GB/day |
| **Medium** | 1.5 Mbps | `--bitrate 1500000` | ~16 GB/day |
| **Low** | 1 Mbps | `--bitrate 1000000` | ~11 GB/day |
| **Very Low** | 500 kbps | `--bitrate 500000` | ~5 GB/day |

### Choosing Bitrate

Bitrate affects image quality:
- **High motion scenes**: Use higher bitrate
- **Static scenes**: Lower bitrate acceptable
- **Fine detail needed**: Higher bitrate

---

## Preset Configurations

### High Quality Analysis

Best image quality, higher storage and CPU usage.

```yaml
--width 1280 --height 720 --framerate 30 --bitrate 2500000
```

- Storage: ~27 GB/camera/day
- CPU: 35-40%
- Use: Critical behavioral analysis

### Standard Monitoring (Default)

Balanced quality and resource usage.

```yaml
--width 1024 --height 768 --framerate 15 --bitrate 1500000
```

- Storage: ~16 GB/camera/day
- CPU: 20-25%
- Use: Daily research recording

### Long-Term Study

Reduced quality for extended recording periods.

```yaml
--width 800 --height 600 --framerate 10 --bitrate 1000000
```

- Storage: ~11 GB/camera/day
- CPU: 15-20%
- Use: Multi-week experiments

### Minimal Storage

Minimum viable quality for maximum retention.

```yaml
--width 640 --height 480 --framerate 5 --bitrate 500000
```

- Storage: ~5 GB/camera/day
- CPU: 10-15%
- Use: Very long-term observation

---

## Storage Calculator

### Formula

```
Daily Storage (GB) = Bitrate (Mbps) × 24 × 3600 ÷ 8 ÷ 1024

Or simplified:
Daily Storage (GB) ≈ Bitrate (Mbps) × 10.8
```

### Quick Reference

| Cameras | Bitrate | Daily | Weekly | Monthly |
|---------|---------|-------|--------|---------|
| 2 | 1.5 Mbps | 32 GB | 225 GB | 970 GB |
| 2 | 1.0 Mbps | 22 GB | 150 GB | 650 GB |
| 4 | 1.5 Mbps | 65 GB | 450 GB | 1.9 TB |
| 4 | 1.0 Mbps | 43 GB | 300 GB | 1.3 TB |

### Retention Planning

With 1 TB storage:
- 2 cameras @ 1.5 Mbps: ~31 days
- 2 cameras @ 1.0 Mbps: ~45 days
- 4 cameras @ 1.0 Mbps: ~23 days

---

## Changing Parameters

### Step 1: Edit Configuration

```bash
ssh {PI_USER}@{PI_IP}
sudo nano /opt/go2rtc/go2rtc.yaml
```

### Step 2: Modify Stream Settings

Find the exec line and change parameters:

```yaml
streams:
  pi_cam_0:
    exec: >
      rpicam-vid
      --width 800          # Changed
      --height 600         # Changed
      --framerate 10       # Changed
      --bitrate 1000000    # Changed
      # ... rest of options
```

### Step 3: Apply Changes

```bash
sudo systemctl restart go2rtc
```

### Step 4: Verify

```bash
# Check temperature (should stay < 70°C)
vcgencmd measure_temp

# Check for throttling
vcgencmd get_throttled

# Verify streams
curl http://localhost:1984/api/streams
```

---

## Thermal Guidelines

Higher quality settings generate more heat:

| Temperature | Status | Action |
|-------------|--------|--------|
| < 60°C | Normal | No action needed |
| 60-70°C | Warm | Monitor closely |
| 70-80°C | Hot | Consider reducing settings |
| > 80°C | Critical | Reduce settings immediately |

### If Overheating

1. Reduce frame rate first (biggest impact)
2. Then reduce resolution
3. Then reduce bitrate
4. Improve physical cooling

---

## EEG/EMG Synchronization

For research requiring video-EEG synchronization:

### Timing Considerations

- Frigate provides timestamps in recordings
- Frame rate should be compatible with EEG sampling rate
- Higher frame rates provide more precise alignment

### Recommended Settings

| EEG Rate | Video FPS | Notes |
|----------|-----------|-------|
| 256 Hz | 30 fps | Good sync, ~8.5 frames/sample |
| 512 Hz | 30 fps | ~17 frames/sample |
| 1 kHz | 30 fps | ~33 frames/sample |

### Timestamp Extraction

Frigate recordings include embedded timestamps. Extract with:

```bash
ffprobe -show_entries frame=pts_time -of csv=p=0 recording.mp4
```

---

## Important Notes

### ⚠️ Never Use H.265

H.265 (HEVC) encoding causes kernel panics on Raspberry Pi 5.

**Always use:**
```yaml
--codec libav --libav-format h264
```

**Never use:**
```yaml
--codec h265  # WILL CRASH
```

### ⚠️ Test Changes Incrementally

1. Change one parameter at a time
2. Monitor for 10+ minutes
3. Check temperature and CPU
4. Verify recordings in Frigate

### ⚠️ Backup Before Changes

```bash
sudo cp /opt/go2rtc/go2rtc.yaml /opt/go2rtc/go2rtc.yaml.backup
```
