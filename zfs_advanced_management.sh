#!/bin/bash
# Advanced ZFS Management Extensions
# Next-level control features beyond basic deployment

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

log() {
    echo -e "${2:-}$1${NC}" | tee -a "/var/log/zfs_advanced_$(date +%Y%m%d).log"
}

# Dynamic NVMe wear-leveling prioritization
optimize_nvme_assignment() {
    log "🔄 Analyzing NVMe wear levels for optimal assignment..." "$BLUE"
    
    local best_l2arc_device=""
    local best_slog_device=""
    local lowest_wear=999999
    local fastest_write=0
    
    # Analyze each NVMe for optimal role assignment
    for nvme in /dev/nvme*n1; do
        [[ -b "$nvme" ]] || continue
        
        # Get wear leveling info
        local wear_level=$(sudo nvme smart-log "$nvme" 2>/dev/null | grep "percentage_used" | awk '{print $3}' | tr -d '%' || echo "0")
        local write_speed=$(sudo smartctl -a "$nvme" 2>/dev/null | grep "Write:" | awk '{print $2}' | tr -d ',' || echo "0")
        
        # L2ARC prefers lower wear (longevity)
        if [[ $wear_level -lt $lowest_wear ]]; then
            lowest_wear=$wear_level
            best_l2arc_device="$nvme"
        fi
        
        # SLOG prefers highest write speed (performance)
        if [[ $write_speed -gt $fastest_write ]]; then
            fastest_write=$write_speed
            best_slog_device="$nvme"
        fi
        
        log "  $nvme: ${wear_level}% wear, ${write_speed} MB/s write" "$YELLOW"
    done
    
    log "  Optimal L2ARC: $best_l2arc_device (${lowest_wear}% wear)" "$GREEN"
    log "  Optimal SLOG: $best_slog_device (${fastest_write} MB/s)" "$GREEN"
    
    # Export for use by main script
    export OPTIMAL_L2ARC_DEVICE="$best_l2arc_device"
    export OPTIMAL_SLOG_DEVICE="$best_slog_device"
}

# Intelligent notification system
setup_alert_system() {
    log "📢 Setting up intelligent alert system..." "$BLUE"
    
    # Create webhook notification script
    cat > /usr/local/bin/zfs_alert.sh << 'EOF'
#!/bin/bash
# ZFS Alert System

WEBHOOK_URL="${ZFS_WEBHOOK_URL:-}"
EMAIL="${ZFS_ALERT_EMAIL:-}"
POOL_NAME="${1:-tank}"
ALERT_TYPE="${2:-health}"
MESSAGE="${3:-ZFS alert triggered}"

send_webhook() {
    if [[ -n "$WEBHOOK_URL" ]]; then
        curl -X POST "$WEBHOOK_URL" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"🚨 ZFS Alert: $MESSAGE\", \"pool\":\"$POOL_NAME\", \"type\":\"$ALERT_TYPE\"}" \
            2>/dev/null || echo "Webhook failed"
    fi
}

send_email() {
    if [[ -n "$EMAIL" ]] && command -v mail >/dev/null; then
        echo "$MESSAGE" | mail -s "ZFS Alert: $POOL_NAME" "$EMAIL" 2>/dev/null || echo "Email failed"
    fi
}

# Log to system
logger "ZFS Alert: $ALERT_TYPE - $MESSAGE"

# Send notifications
send_webhook
send_email

echo "Alert sent: $MESSAGE"
EOF
    
    chmod +x /usr/local/bin/zfs_alert.sh
    
    # Enhanced monitoring with alerts
    cat > /usr/local/bin/zfs_smart_monitor.sh << 'EOF'
#!/bin/bash
# Smart ZFS Monitoring with Predictive Alerts

POOL="tank"
ARC_HIT_THRESHOLD=85  # Alert if ARC hit rate below 85%
POOL_USAGE_THRESHOLD=80  # Alert if pool usage above 80%

check_advanced_health() {
    # Pool degradation
    if zpool status "$POOL" | grep -q "DEGRADED\|FAULTED\|OFFLINE"; then
        /usr/local/bin/zfs_alert.sh "$POOL" "degraded" "Pool $POOL is degraded or has failed components"
    fi
    
    # High pool usage
    local usage=$(zpool list -H -o cap "$POOL" | tr -d '%')
    if [[ $usage -gt $POOL_USAGE_THRESHOLD ]]; then
        /usr/local/bin/zfs_alert.sh "$POOL" "space" "Pool $POOL usage at ${usage}% (threshold: ${POOL_USAGE_THRESHOLD}%)"
    fi
    
    # Low ARC hit rate
    local arc_hits=$(awk '/^hits/ {print $3}' /proc/spl/kstat/zfs/arcstats)
    local arc_misses=$(awk '/^misses/ {print $3}' /proc/spl/kstat/zfs/arcstats)
    local hit_rate=$((arc_hits * 100 / (arc_hits + arc_misses)))
    
    if [[ $hit_rate -lt $ARC_HIT_THRESHOLD ]]; then
        /usr/local/bin/zfs_alert.sh "$POOL" "performance" "ARC hit rate at ${hit_rate}% (threshold: ${ARC_HIT_THRESHOLD}%)"
    fi
    
    # NVMe wear monitoring
    for device in $(zpool status "$POOL" | grep nvme | awk '{print $1}'); do
        if [[ -b "/dev/$device" ]]; then
            local wear=$(sudo nvme smart-log "/dev/$device" 2>/dev/null | grep percentage_used | awk '{print $3}' | tr -d '%' || echo "0")
            if [[ $wear -gt 90 ]]; then
                /usr/local/bin/zfs_alert.sh "$POOL" "wear" "NVMe device $device wear at ${wear}%"
            fi
        fi
    done
}

check_advanced_health
EOF
    
    chmod +x /usr/local/bin/zfs_smart_monitor.sh
    
    # Update cron for enhanced monitoring
    (crontab -l 2>/dev/null | grep -v zfs_monitor) | crontab -
    (crontab -l 2>/dev/null; echo "*/15 * * * * /usr/local/bin/zfs_smart_monitor.sh") | crontab -
    
    log "  Alert system configured!" "$GREEN"
    log "  Set ZFS_WEBHOOK_URL and ZFS_ALERT_EMAIL environment variables for notifications" "$YELLOW"
}

# Dynamic loop image resizing
implement_dynamic_resizing() {
    log "📏 Implementing dynamic loop image resizing..." "$BLUE"
    
    cat > /usr/local/bin/zfs_resize_loops.sh << 'EOF'
#!/bin/bash
# Dynamic Loop Image Resizing

POOL="tank"
MIN_FREE_SPACE_GB=100
TARGET_FREE_SPACE_GB=500

resize_if_needed() {
    local loop_file="$1"
    local loop_device="$2"
    local vdev_type="$3"
    
    # Get current filesystem free space
    local mount_point=$(df "$loop_file" | tail -1 | awk '{print $6}')
    local free_space_gb=$(df -BG "$mount_point" | tail -1 | awk '{print $4}' | tr -d 'G')
    
    # Get current loop file size
    local current_size_gb=$(du -BG "$loop_file" | awk '{print $1}' | tr -d 'G')
    
    if [[ $free_space_gb -lt $MIN_FREE_SPACE_GB ]]; then
        echo "Warning: Low free space ($free_space_gb GB) for $loop_file"
        return 1
    fi
    
    # Check if we can expand (and should)
    local pool_usage=$(zpool list -H -o cap "$POOL" | tr -d '%')
    local expansion_needed=false
    
    case "$vdev_type" in
        "l2arc")
            # Expand L2ARC if ARC hit rate is low
            local arc_hits=$(awk '/^hits/ {print $3}' /proc/spl/kstat/zfs/arcstats)
            local arc_misses=$(awk '/^misses/ {print $3}' /proc/spl/kstat/zfs/arcstats)
            local hit_rate=$((arc_hits * 100 / (arc_hits + arc_misses)))
            [[ $hit_rate -lt 85 ]] && expansion_needed=true
            ;;
        "slog")
            # Expand SLOG if high sync write latency
            expansion_needed=false  # SLOG rarely needs expansion
            ;;
        "special")
            # Expand special if metadata usage high
            local special_usage=$(zpool list -v "$POOL" | grep special | awk '{print $5}' | tr -d '%' || echo "0")
            [[ $special_usage -gt 70 ]] && expansion_needed=true
            ;;
    esac
    
    if [[ "$expansion_needed" == "true" && $free_space_gb -gt $TARGET_FREE_SPACE_GB ]]; then
        local new_size_gb=$((current_size_gb + 200))  # Expand by 200GB
        echo "Expanding $loop_file from ${current_size_gb}GB to ${new_size_gb}GB"
        
        # Expand the loop file
        truncate -s "${new_size_gb}G" "$loop_file"
        
        # Refresh loop device
        sudo losetup -c "$loop_device"
        
        echo "Expansion complete for $vdev_type"
    fi
}

# Check each loop device
for loop_info in $(losetup -l | grep zfs_ | awk '{print $1":"$6}'); do
    loop_device=$(echo "$loop_info" | cut -d: -f1)
    loop_file=$(echo "$loop_info" | cut -d: -f2)
    
    case "$loop_file" in
        *l2arc*) resize_if_needed "$loop_file" "$loop_device" "l2arc" ;;
        *slog*) resize_if_needed "$loop_file" "$loop_device" "slog" ;;
        *special*) resize_if_needed "$loop_file" "$loop_device" "special" ;;
    esac
done
EOF
    
    chmod +x /usr/local/bin/zfs_resize_loops.sh
    
    # Add to daily cron
    (crontab -l 2>/dev/null; echo "0 3 * * * /usr/local/bin/zfs_resize_loops.sh") | crontab -
    
    log "  Dynamic resizing configured!" "$GREEN"
}

# Automated snapshot management
setup_smart_snapshots() {
    log "📸 Setting up intelligent snapshot management..." "$BLUE"
    
    cat > /usr/local/bin/zfs_smart_snapshots.sh << 'EOF'
#!/bin/bash
# Intelligent ZFS Snapshot Management

POOL="tank"
SNAPSHOT_PREFIX="auto"

create_snapshots() {
    local dataset="$1"
    local frequency="$2"  # hourly, daily, weekly, monthly
    local retention="$3"   # number to keep
    
    local timestamp=$(date +"%Y%m%d_%H%M%S")
    local snapshot_name="${dataset}@${SNAPSHOT_PREFIX}_${frequency}_${timestamp}"
    
    # Create snapshot
    zfs snapshot "$snapshot_name"
    echo "Created snapshot: $snapshot_name"
    
    # Clean old snapshots
    local old_snapshots=$(zfs list -t snapshot -o name -s creation | grep "${dataset}@${SNAPSHOT_PREFIX}_${frequency}" | head -n -"$retention")
    for old_snap in $old_snapshots; do
        zfs destroy "$old_snap"
        echo "Removed old snapshot: $old_snap"
    done
}

# Different snapshot frequencies for different datasets
create_snapshots "$POOL/dev" "hourly" 24      # Keep 24 hourly snapshots
create_snapshots "$POOL/vms" "hourly" 12      # Keep 12 hourly snapshots
create_snapshots "$POOL/media" "daily" 7      # Keep 7 daily snapshots
create_snapshots "$POOL/backup" "weekly" 4    # Keep 4 weekly snapshots

# Emergency rollback function
create_rollback_point() {
    local emergency_snap="${POOL}@emergency_$(date +%Y%m%d_%H%M%S)"
    zfs snapshot -r "$emergency_snap"
    echo "Emergency rollback point created: $emergency_snap"
    echo "To rollback: zfs rollback $emergency_snap"
}

# Check if this is an emergency snapshot call
if [[ "${1:-}" == "emergency" ]]; then
    create_rollback_point
fi
EOF
    
    chmod +x /usr/local/bin/zfs_smart_snapshots.sh
    
    # Setup snapshot cron jobs
    (crontab -l 2>/dev/null; echo "0 * * * * /usr/local/bin/zfs_smart_snapshots.sh") | crontab -      # Hourly
    (crontab -l 2>/dev/null; echo "0 2 * * 0 /usr/local/bin/zfs_smart_snapshots.sh") | crontab -     # Weekly
    
    log "  Smart snapshots configured!" "$GREEN"
    log "  Emergency rollback: /usr/local/bin/zfs_smart_snapshots.sh emergency" "$YELLOW"
}

# Performance auto-tuning
implement_auto_tuning() {
    log "⚡ Implementing performance auto-tuning..." "$BLUE"
    
    cat > /usr/local/bin/zfs_auto_tune.sh << 'EOF'
#!/bin/bash
# ZFS Performance Auto-Tuning

POOL="tank"

tune_based_on_workload() {
    # Analyze I/O patterns
    local read_ops=$(zpool iostat "$POOL" 1 3 | tail -1 | awk '{print $5}')
    local write_ops=$(zpool iostat "$POOL" 1 3 | tail -1 | awk '{print $6}')
    local ratio=$((read_ops * 100 / (read_ops + write_ops + 1)))
    
    # Tune based on read/write ratio
    if [[ $ratio -gt 80 ]]; then
        # Read-heavy workload
        echo "1" > /sys/module/zfs/parameters/zfs_prefetch_disable
        echo "Tuned for read-heavy workload"
    elif [[ $ratio -lt 20 ]]; then
        # Write-heavy workload
        echo "0" > /sys/module/zfs/parameters/zfs_prefetch_disable
        echo "67108864" > /sys/module/zfs/parameters/zfs_txg_timeout  # 64MB
        echo "Tuned for write-heavy workload"
    else
        # Balanced workload
        echo "0" > /sys/module/zfs/parameters/zfs_prefetch_disable
        echo "Tuned for balanced workload"
    fi
    
    # Adjust ARC size based on memory pressure
    local mem_free=$(free -m | awk 'NR==2{printf "%.0f", $7/1024}')
    local current_arc_max=$(cat /sys/module/zfs/parameters/zfs_arc_max)
    local optimal_arc=$((mem_free * 1024 * 1024 * 1024 / 2))
    
    if [[ $optimal_arc -ne $current_arc_max ]]; then
        echo "$optimal_arc" > /sys/module/zfs/parameters/zfs_arc_max
        echo "Adjusted ARC max to $(numfmt --to=iec $optimal_arc)"
    fi
}

tune_based_on_workload
EOF
    
    chmod +x /usr/local/bin/zfs_auto_tune.sh
    
    # Run auto-tuning every hour
    (crontab -l 2>/dev/null; echo "0 * * * * /usr/local/bin/zfs_auto_tune.sh") | crontab -
    
    log "  Auto-tuning configured!" "$GREEN"
}

# Main function
main() {
    log "🚀 ZFS Advanced Management Setup" "$PURPLE"
    
    [[ $EUID -eq 0 ]] || exec sudo "$0" "$@"
    
    case "${1:-all}" in
        "wear")
            optimize_nvme_assignment
            ;;
        "alerts")
            setup_alert_system
            ;;
        "resize")
            implement_dynamic_resizing
            ;;
        "snapshots")
            setup_smart_snapshots
            ;;
        "tune")
            implement_auto_tuning
            ;;
        "all")
            optimize_nvme_assignment
            setup_alert_system
            implement_dynamic_resizing
            setup_smart_snapshots
            implement_auto_tuning
            ;;
        *)
            echo "Usage: $0 [wear|alerts|resize|snapshots|tune|all]"
            exit 1
            ;;
    esac
    
    log "🎯 Advanced management features activated!" "$GREEN"
}

main "$@"



