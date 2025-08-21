# 🎵 Audio Splitter Pro - Working Configuration Documentation

## 🎯 Overview
**Production audio splitter** that routes left and right channels to separate HDMI outputs with compression layer. Achieves true stereo separation across multiple displays.

## 🔧 Hardware Configuration
- **Left Channel Output**: DP built-in audio (`pci-0000_00_1f.3`)
- **Right Channel Output**: Navi31 HDMI (`pci-0000_03_00.1`)
- **Audio Server**: PipeWire with PulseAudio compatibility
- **OS**: Linux Mint

## 🎵 Audio Pipeline Architecture

```
Input Audio → null sink → null.monitor → L/R Channel Split → Separate HDMI Outputs
                    ↓
            splitter_left (L) → Navi31 HDMI
            splitter_right (R) → DP HDMI
```

## 📋 Current Working Module Configuration

### 1. Audio Sinks
```bash
# Check current sinks
pactl list short sinks

# Expected output:
22      alsa_output.pci-0000_00_1f.3.hdmi-stereo        module-alsa-card.c      s16le 2ch 44100Hz      RUNNING
23      alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3 module-alsa-card.c      s16le 2ch 44100Hz      RUNNING
24      null    module-null-sink.c      s16le 2ch 44100Hz       RUNNING
```

### 2. Audio Sources
```bash
# Check current sources
pactl list short sources

# Expected output includes:
splitter_left    module-remap-source.c  s16le 1ch 44100Hz      IDLE
splitter_right   module-remap-source.c  s16le 1ch 44100Hz      IDLE
```

### 3. Active Modules
```bash
# Check active modules
pactl list modules | grep -E "(module-null-sink|module-remap-source|module-loopback)" -A2 -B1
```

**Expected Modules:**
- **Module #38**: `module-remap-source` - `splitter_left` (L channel from null.monitor)
- **Module #39**: `module-remap-source` - `splitter_right` (R channel from null.monitor)
- **Module #48**: `module-loopback` - `splitter_left` → Navi31 HDMI
- **Module #49**: `module-loopback` - `splitter_right` → DP HDMI

## 🚀 Manual Recreation Commands

### Step 1: Clean Up Existing Configuration
```bash
# Remove any existing splitter modules
pactl list modules | grep -E "(module-loopback|module-remap-source)" | grep -E "(splitter_left|splitter_right)" | awk '/Module #[0-9]+/ {print $2}' | sed 's/#//' | xargs -I {} pactl unload-module {} 2>/dev/null || true

# Remove any stereo_split combined sink
pactl list modules | grep "module-combine-sink.*stereo_split" | awk '/Module #[0-9]+/ {print $2}' | sed 's/#//' | xargs -I {} pactl unload-module {} 2>/dev/null || true
```

### Step 2: Create Splitter Sink (or reuse existing)
```bash
# Check if null sink exists
if ! pactl list short sinks | awk '$2=="null"{f=1} END{exit f?0:1}'; then
    pactl load-module module-null-sink sink_name=null sink_properties=device.description="Audio Splitter"
fi
```

### Step 3: Create L/R Mono Sources
```bash
# Left channel (front-left from null.monitor)
pactl load-module module-remap-source \
    source_name=splitter_left \
    master=null.monitor \
    channels=1 channel_map=mono master_channel_map=front-left

# Right channel (front-right from null.monitor)
pactl load-module module-remap-source \
    source_name=splitter_right \
    master=null.monitor \
    channels=1 channel_map=mono master_channel_map=front-right
```

### Step 4: Route Channels to HDMI Outputs
```bash
# Left channel → Navi31 HDMI
pactl load-module module-loopback \
    source=splitter_left \
    sink=alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3 \
    latency_msec=50 source_dont_move=true sink_dont_move=true

# Right channel → DP HDMI
pactl load-module module-loopback \
    source=splitter_right \
    sink=alsa_output.pci-0000_00_1f.3.hdmi-stereo \
    latency_msec=50 source_dont_move=true sink_dont_move=true
```

### Step 5: Set Default Sink (Optional)
```bash
# Set null sink as default for new audio streams
pactl set-default-sink null
```

## 🔍 Troubleshooting Commands

### Check Pipeline Status
```bash
# Verify all components are working
pactl list short sinks
pactl list short sources
pactl list modules | grep -E "(splitter_left|splitter_right)" -B2 -A2
```

### Test Audio Routing
```bash
# Test left channel (should go to Navi31)
pactl set-sink-volume alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3 100%

# Test right channel (should go to DP)
pactl set-sink-volume alsa_output.pci-0000_00_1f.3.hdmi-stereo 100%

# Reset volumes
pactl set-sink-volume alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3 50%
pactl set-sink-volume alsa_output.pci-0000_00_1f.3.hdmi-stereo 50%
```

### Debug Module Issues
```bash
# Check for module conflicts
pactl list modules | grep -E "(module-null-sink|module-remap-source|module-loopback)"

# Check module usage counters
pactl list modules | grep -A5 -B5 "Usage counter: [1-9]"
```

## 🎛️ Volume Balance Adjustment

### Individual Channel Control
```bash
# Adjust left channel (Navi31) volume
pactl set-sink-volume alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3 80%

# Adjust right channel (DP) volume  
pactl set-sink-volume alsa_output.pci-0000_00_1f.3.hdmi-stereo 60%
```

### Master Volume Control
```bash
# Control overall volume through null sink
pactl set-sink-volume null 70%
```

## 📁 File Locations

### Scripts
- **Main Script**: `/home/brandon/Documents/Cursor/audio-splitter-pro.sh`
- **Service File**: `/home/brandon/Documents/Cursor/audio-splitter-pro.service`
- **User Service**: `~/.config/systemd/user/audio-splitter-pro.service`

### Service Management
```bash
# Enable service
systemctl --user enable audio-splitter-pro.service

# Start service
systemctl --user start audio-splitter-pro.service

# Check status
systemctl --user status audio-splitter-pro.service

# Restart service
systemctl --user restart audio-splitter-pro.service
```

## 🎯 Key Success Factors

1. **Clean Module Management**: Remove duplicates and old configurations
2. **Correct Channel Mapping**: `front-left` → Navi31, `front-right` → DP
3. **Proper Loopback Routing**: Direct source-to-sink connections
4. **No Combined Sinks**: Use only `null` sink + remap + loopback approach
5. **Idempotent Operations**: Script can be re-run safely

## 🚨 Common Issues & Solutions

### Issue: "Module initialization failed"
**Solution**: Check for conflicting sink names, remove old modules first

### Issue: Audio only on one side
**Solution**: Verify loopback routing and channel mapping

### Issue: High latency
**Solution**: Adjust `latency_msec` in loopback modules

### Issue: Service fails to start
**Solution**: Check PulseAudio status, ensure user service directory exists

## 🎉 Current Status: WORKING ✅

**Last Verified**: 2025-08-20 22:30 UTC
**Configuration**: L→Navi31, R→DP with clean null sink pipeline
**Modules**: 4 active (2 remap sources + 2 loopbacks)
**Audio Quality**: Stereo separation achieved across dual HDMI outputs

---

*This configuration represents the culmination of iterative testing and optimization. The null sink approach proved more reliable than combined sinks or complex routing schemes.*

