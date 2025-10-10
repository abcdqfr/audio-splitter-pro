#!/bin/bash
# CLI Audio Splitter - Comprehensive Sink Management & L/R Channel Routing
# Based on CLI investigation findings

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SPLITTER_NAME="lr_splitter_master"
LEFT_SOURCE="lr_left"
RIGHT_SOURCE="lr_right"

echo -e "${BLUE}🎛️  CLI Audio Splitter - Comprehensive Sink Management${NC}"
echo "=================================================="

# Function to check if PulseAudio is running
check_pulseaudio() {
    if ! pactl info >/dev/null 2>&1; then
        echo -e "${RED}❌ PulseAudio is not running${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ PulseAudio is running${NC}"
}

# Function to list all available sinks with details
list_all_sinks() {
    echo -e "\n${BLUE}🔍 All Available Sinks:${NC}"
    echo "------------------------"
    pactl list short sinks | while IFS=$'\t' read -r id name module format state; do
        echo -e "  ${YELLOW}ID:${NC} $id  ${YELLOW}Name:${NC} $name  ${YELLOW}Format:${NC} $format  ${YELLOW}State:${NC} $state"
    done
}

# Function to list all available sources with details
list_all_sources() {
    echo -e "\n${BLUE}🔍 All Available Sources:${NC}"
    echo "------------------------"
    pactl list short sources | while IFS=$'\t' read -r id name module format state; do
        echo -e "  ${YELLOW}ID:${NC} $id  ${YELLOW}Name:${NC} $name  ${YELLOW}Format:${NC} $format  ${YELLOW}State:${NC} $state"
    done
}

# Function to detect and enable HDMI/DP profiles
enable_hdmi_profiles() {
    echo -e "\n${BLUE}🎮 Enabling HDMI/DP Profiles:${NC}"
    echo "------------------------"
    
    # Get Navi card (usually card 0)
    NAVI_CARD=$(pactl list short cards | grep "alsa_card.pci-0000_03_00.1" | cut -f1)
    if [ -n "$NAVI_CARD" ]; then
        echo -e "  ${YELLOW}Navi card found:${NC} $NAVI_CARD"
        
        # Enable HDMI profiles
        echo -e "  ${YELLOW}Enabling HDMI profiles...${NC}"
        pactl set-card-profile $NAVI_CARD output:hdmi-stereo-extra1
        pactl set-card-profile $NAVI_CARD output:hdmi-stereo-extra3
        
        echo -e "  ${GREEN}✅ HDMI profiles enabled${NC}"
    else
        echo -e "  ${RED}❌ Navi card not found${NC}"
    fi
}

# Function to create L/R splitter pipeline
create_lr_pipeline() {
    local left_sink="$1"
    local right_sink="$2"
    
    echo -e "\n${BLUE}🚀 Creating L/R Splitter Pipeline:${NC}"
    echo "----------------------------------------"
    echo -e "  ${YELLOW}Left Channel:${NC} $left_sink"
    echo -e "  ${YELLOW}Right Channel:${NC} $right_sink"
    
    # Clean up existing pipeline first
    cleanup_lr_pipeline
    
    # Create master splitter sink
    echo -e "  ${YELLOW}Creating master splitter sink...${NC}"
    SPLITTER_MODULE=$(pactl load-module module-null-sink \
        sink_name="$SPLITTER_NAME" \
        sink_properties=device.description="L/R_Channel_Splitter")
    echo -e "  ${GREEN}✅ Splitter sink created (Module: $SPLITTER_MODULE)${NC}"
    
    # Create left channel source
    echo -e "  ${YELLOW}Creating left channel source...${NC}"
    LEFT_MODULE=$(pactl load-module module-remap-source \
        source_name="$LEFT_SOURCE" \
        master="$SPLITTER_NAME.monitor" \
        channels=1 \
        channel_map=mono \
        master_channel_map=front-left)
    echo -e "  ${GREEN}✅ Left channel source created (Module: $LEFT_MODULE)${NC}"
    
    # Create right channel source
    echo -e "  ${YELLOW}Creating right channel source...${NC}"
    RIGHT_MODULE=$(pactl load-module module-remap-source \
        source_name="$RIGHT_SOURCE" \
        master="$SPLITTER_NAME.monitor" \
        channels=1 \
        channel_map=mono \
        master_channel_map=front-right)
    echo -e "  ${GREEN}✅ Right channel source created (Module: $RIGHT_MODULE)${NC}"
    
    # Route left channel to left sink
    if [ -n "$left_sink" ]; then
        echo -e "  ${YELLOW}Routing left channel to $left_sink...${NC}"
        LEFT_LOOPBACK=$(pactl load-module module-loopback \
            source="$LEFT_SOURCE" \
            sink="$left_sink" \
            latency_msec=50)
        echo -e "  ${GREEN}✅ Left channel routed (Module: $LEFT_LOOPBACK)${NC}"
    fi
    
    # Route right channel to right sink
    if [ -n "$right_sink" ]; then
        echo -e "  ${YELLOW}Routing right channel to $right_sink...${NC}"
        RIGHT_LOOPBACK=$(pactl load-module module-loopback \
            source="$RIGHT_SOURCE" \
            sink="$right_sink" \
            latency_msec=50)
        echo -e "  ${GREEN}✅ Right channel routed (Module: $RIGHT_LOOPBACK)${NC}"
    fi
    
    # Set as default sink
    echo -e "  ${YELLOW}Setting as default sink...${NC}"
    pactl set-default-sink "$SPLITTER_NAME"
    echo -e "  ${GREEN}✅ Default sink set to $SPLITTER_NAME${NC}"
    
    echo -e "\n${GREEN}🎉 L/R Splitter Pipeline Created Successfully!${NC}"
    echo -e "  ${YELLOW}Master Sink:${NC} $SPLITTER_NAME"
    echo -e "  ${YELLOW}Left Source:${NC} $LEFT_SOURCE"
    echo -e "  ${YELLOW}Right Source:${NC} $RIGHT_SOURCE"
}

# Function to cleanup L/R pipeline
cleanup_lr_pipeline() {
    echo -e "\n${BLUE}🧹 Cleaning Up L/R Pipeline:${NC}"
    echo "------------------------------"
    
    # Find and remove loopback modules
    pactl list short modules | grep "module-loopback" | grep -E "(lr_left|lr_right)" | while read -r id rest; do
        echo -e "  ${YELLOW}Removing loopback module:${NC} $id"
        pactl unload-module "$id"
    done
    
    # Find and remove remap source modules
    pactl list short modules | grep "module-remap-source" | grep -E "(lr_left|lr_right)" | while read -r id rest; do
        echo -e "  ${YELLOW}Removing remap source module:${NC} $id"
        pactl unload-module "$id"
    done
    
    # Find and remove splitter sink
    pactl list short modules | grep "module-null-sink" | grep "$SPLITTER_NAME" | while read -r id rest; do
        echo -e "  ${YELLOW}Removing splitter sink module:${NC} $id"
        pactl unload-module "$id"
    done
    
    echo -e "  ${GREEN}✅ Pipeline cleanup complete${NC}"
}

# Function to show pipeline status
show_pipeline_status() {
    echo -e "\n${BLUE}📊 Pipeline Status:${NC}"
    echo "------------------"
    
    # Check if splitter exists
    if pactl list short sinks | grep -q "$SPLITTER_NAME"; then
        echo -e "  ${GREEN}✅ Splitter sink exists${NC}"
        pactl list short sinks | grep "$SPLITTER_NAME"
    else
        echo -e "  ${RED}❌ Splitter sink not found${NC}"
    fi
    
    # Check if sources exist
    if pactl list short sources | grep -q "$LEFT_SOURCE"; then
        echo -e "  ${GREEN}✅ Left channel source exists${NC}"
        pactl list short sources | grep "$LEFT_SOURCE"
    else
        echo -e "  ${RED}❌ Left channel source not found${NC}"
    fi
    
    if pactl list short sources | grep -q "$RIGHT_SOURCE"; then
        echo -e "  ${GREEN}✅ Right channel source exists${NC}"
        pactl list short sources | grep "$RIGHT_SOURCE"
    else
        echo -e "  ${RED}❌ Right channel source not found${NC}"
    fi
}

# Function to edit sink properties
edit_sink_properties() {
    local sink_name="$1"
    local volume="$2"
    
    if [ -n "$sink_name" ] && [ -n "$volume" ]; then
        echo -e "\n${BLUE}🎛️  Editing Sink Properties:${NC}"
        echo "---------------------------"
        echo -e "  ${YELLOW}Sink:${NC} $sink_name"
        echo -e "  ${YELLOW}Volume:${NC} $volume%"
        
        pactl set-sink-volume "$sink_name" "$volume%"
        echo -e "  ${GREEN}✅ Volume set to $volume%${NC}"
        
        # Show new volume
        echo -e "  ${YELLOW}New volume:${NC}"
        pactl get-sink-volume "$sink_name"
    fi
}

# Function to show help
show_help() {
    echo -e "\n${BLUE}📖 Usage:${NC}"
    echo "------"
    echo "  $0 [command] [options]"
    echo ""
    echo -e "${BLUE}Commands:${NC}"
    echo "  list-sinks          - List all available sinks"
    echo "  list-sources        - List all available sources"
    echo "  enable-hdmi         - Enable HDMI/DP profiles"
    echo "  create-pipeline     - Create L/R splitter pipeline"
    echo "  cleanup-pipeline    - Clean up L/R pipeline"
    echo "  show-status         - Show pipeline status"
    echo "  edit-sink <name> <volume> - Edit sink volume (0-100)"
    echo "  help                - Show this help"
    echo ""
    echo -e "${BLUE}Examples:${NC}"
    echo "  $0 create-pipeline"
    echo "  $0 edit-sink dp_output_1 75"
    echo "  $0 cleanup-pipeline"
}

# Main script logic
main() {
    check_pulseaudio
    
    case "${1:-help}" in
        "list-sinks")
            list_all_sinks
            ;;
        "list-sources")
            list_all_sources
            ;;
        "enable-hdmi")
            enable_hdmi_profiles
            ;;
        "create-pipeline")
            create_lr_pipeline "${2:-}" "${3:-}"
            ;;
        "cleanup-pipeline")
            cleanup_lr_pipeline
            ;;
        "show-status")
            show_pipeline_status
            ;;
        "edit-sink")
            edit_sink_properties "$2" "$3"
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@"
