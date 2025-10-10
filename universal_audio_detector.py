#!/usr/bin/env python3
"""
Universal Audio Output Detector
==============================

Portable, idempotent, universal solution for detecting ALL audio outputs
across any Linux system with any GPU configuration.

Features:
- Uses standard Linux tools (udev, sysfs, pactl)
- Dynamic detection without hardcoded values
- Portable across distributions
- Safe to run multiple times
- Works with any audio card configuration
"""

import subprocess
import json
import os
import sys
from typing import Dict, List, Optional, Tuple
from pathlib import Path

class UniversalAudioDetector:
    """Universal audio output detection using standard Linux tools."""
    
    def __init__(self):
        self.audio_cards = {}
        self.gpu_info = {}
        
    def run_cmd_safe(self, cmd: List[str], capture_output: bool = True) -> Tuple[int, str, str]:
        """Run command safely with proper error handling."""
        try:
            result = subprocess.run(cmd, capture_output=capture_output, text=True, timeout=10)
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except FileNotFoundError:
            return -1, "", f"Command not found: {cmd[0]}"
        except Exception as e:
            return -1, "", str(e)
    
    def detect_gpus_via_sysfs(self) -> Dict:
        """Detect GPUs using sysfs (universal method)."""
        gpu_info = {}
        
        # Check for GPU devices in sysfs
        gpu_paths = [
            "/sys/class/drm",  # Modern DRM devices
            "/sys/bus/pci/devices",  # PCI devices
        ]
        
        for base_path in gpu_paths:
            if not os.path.exists(base_path):
                continue
                
            try:
                if base_path == "/sys/class/drm":
                    # Modern DRM-based detection
                    for item in os.listdir(base_path):
                        if item.startswith("card"):
                            card_path = os.path.join(base_path, item)
                            device_path = os.path.join(card_path, "device")
                            
                            if os.path.exists(device_path):
                                # Get vendor and device info
                                vendor_path = os.path.join(device_path, "vendor")
                                device_path_file = os.path.join(device_path, "device")
                                
                                if os.path.exists(vendor_path) and os.path.exists(device_path_file):
                                    with open(vendor_path) as f:
                                        vendor_id = f.read().strip()
                                    with open(device_path_file) as f:
                                        device_id = f.read().strip()
                                    
                                    # Get device name from uevent
                                    uevent_path = os.path.join(device_path, "uevent")
                                    device_name = "Unknown GPU"
                                    if os.path.exists(uevent_path):
                                        with open(uevent_path) as f:
                                            for line in f:
                                                if line.startswith("PCI_ID="):
                                                    device_name = line.split("=", 1)[1].strip()
                                                    break
                                    
                                    gpu_info[f"card{item}"] = {
                                        "type": "drm",
                                        "vendor_id": vendor_id,
                                        "device_id": device_id,
                                        "name": device_name,
                                        "path": card_path
                                    }
                
                elif base_path == "/sys/bus/pci/devices":
                    # PCI-based detection
                    for item in os.listdir(base_path):
                        if item.startswith("0000:"):
                            device_path = os.path.join(base_path, item)
                            class_path = os.path.join(device_path, "class")
                            
                            if os.path.exists(class_path):
                                with open(class_path) as f:
                                    device_class = f.read().strip()
                                
                                # Check if it's a VGA/3D controller
                                if device_class in ["0x030000", "0x030200"]:
                                    vendor_path = os.path.join(device_path, "vendor")
                                    device_path_file = os.path.join(device_path, "device")
                                    
                                    if os.path.exists(vendor_path) and os.path.exists(device_path_file):
                                        with open(vendor_path) as f:
                                            vendor_id = f.read().strip()
                                        with open(device_path_file) as f:
                                            device_id = f.read().strip()
                                        
                                        # Get device name
                                        device_name = "Unknown GPU"
                                        uevent_path = os.path.join(device_path, "uevent")
                                        if os.path.exists(uevent_path):
                                            with open(uevent_path) as f:
                                                for line in f:
                                                    if line.startswith("PCI_ID="):
                                                        device_name = line.split("=", 1)[1].strip()
                                                        break
                                        
                                        gpu_info[item] = {
                                            "type": "pci",
                                            "vendor_id": vendor_id,
                                            "device_id": device_id,
                                            "name": device_name,
                                            "path": device_path
                                        }
                                        
            except (OSError, IOError) as e:
                continue
        
        return gpu_info
    
    def detect_audio_cards_via_pactl(self) -> Dict:
        """Detect audio cards using pactl (universal method)."""
        audio_cards = {}
        
        # Use pactl to list cards
        code, output, error = self.run_cmd_safe(["pactl", "list", "cards"])
        if code != 0:
            print(f"Warning: pactl failed: {error}")
            return audio_cards
        
        current_card = None
        current_section = None
        
        for line in output.splitlines():
            line = line.strip()
            
            if line.startswith("Card #"):
                if current_card:
                    audio_cards[current_card["id"]] = current_card
                
                card_id = line.split("#")[1].strip()
                current_card = {
                    "id": card_id,
                    "name": "",
                    "description": "",
                    "driver": "",
                    "profiles": [],
                    "active_profile": "",
                    "ports": [],
                    "properties": {}
                }
                current_section = None
                
            elif current_card:
                if line.startswith("Name:"):
                    current_card["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Driver:"):
                    current_card["driver"] = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    current_card["description"] = line.split(":", 1)[1].strip()
                elif line.startswith("Active Profile:"):
                    current_card["active_profile"] = line.split(":", 1)[1].strip()
                elif line.startswith("Profiles:"):
                    current_section = "profiles"
                elif line.startswith("Ports:"):
                    current_section = "ports"
                elif line.startswith("Properties:"):
                    current_section = "properties"
                elif current_section == "profiles" and line.startswith("output:"):
                    # Parse profile line
                    if "available: yes" in line:
                        try:
                            # Extract profile name and description
                            parts = line.split(":", 2)
                            if len(parts) >= 3:
                                profile_name = parts[1].strip()
                                description = parts[2].split("(")[0].strip()
                                
                                current_card["profiles"].append({
                                    "name": profile_name,
                                    "description": description,
                                    "available": True
                                })
                        except Exception:
                            continue
                elif current_section == "ports" and line.startswith("hdmi-output-"):
                    # Parse HDMI port
                    try:
                        port_parts = line.split(":", 2)
                        if len(port_parts) >= 3:
                            port_name = port_parts[1].strip()
                            port_info = port_parts[2].split("(")[0].strip()
                            
                            # Check availability
                            available = "available" in line and "not available" not in line
                            
                            current_card["ports"].append({
                                "name": port_name,
                                "info": port_info,
                                "available": available
                            })
                    except Exception:
                        continue
                elif current_section == "properties" and "=" in line:
                    # Parse properties
                    try:
                        key, value = line.split("=", 1)
                        current_card["properties"][key.strip()] = value.strip()
                    except Exception:
                        continue
        
        # Add the last card
        if current_card:
            audio_cards[current_card["id"]] = current_card
        
        return audio_cards
    
    def detect_audio_cards_via_sysfs(self) -> Dict:
        """Detect audio cards using sysfs (fallback method)."""
        audio_cards = {}
        
        # Check for sound devices in sysfs
        sound_path = "/sys/class/sound"
        if not os.path.exists(sound_path):
            return audio_cards
        
        try:
            for item in os.listdir(sound_path):
                if item.startswith("card"):
                    card_path = os.path.join(sound_path, item)
                    device_path = os.path.join(card_path, "device")
                    
                    if os.path.exists(device_path):
                        card_info = {
                            "id": item,
                            "name": item,
                            "description": f"Sound card {item}",
                            "driver": "unknown",
                            "profiles": [],
                            "active_profile": "",
                            "ports": [],
                            "properties": {}
                        }
                        
                        # Try to get more info from device
                        uevent_path = os.path.join(device_path, "uevent")
                        if os.path.exists(uevent_path):
                            with open(uevent_path) as f:
                                for line in f:
                                    if line.startswith("PCI_ID="):
                                        card_info["description"] = line.split("=", 1)[1].strip()
                                        break
                        
                        audio_cards[item] = card_info
                        
        except (OSError, IOError):
            pass
        
        return audio_cards
    
    def get_available_sinks(self) -> List[Dict]:
        """Get available audio sinks using pactl."""
        sinks = []
        
        code, output, error = self.run_cmd_safe(["pactl", "list", "sinks"])
        if code != 0:
            print(f"Warning: pactl list sinks failed: {error}")
            return sinks
        
        current_sink = None
        
        for line in output.splitlines():
            line = line.strip()
            
            if line.startswith("Sink #"):
                if current_sink:
                    sinks.append(current_sink)
                
                sink_id = line.split("#")[1].strip()
                current_sink = {
                    "id": sink_id,
                    "name": "",
                    "description": "",
                    "driver": "",
                    "state": "",
                    "sample_spec": "",
                    "channel_map": "",
                    "properties": {}
                }
                
            elif current_sink:
                if line.startswith("Name:"):
                    current_sink["name"] = line.split(":", 1)[1].strip()
                elif line.startswith("Description:"):
                    current_sink["description"] = line.split(":", 1)[1].strip()
                elif line.startswith("Driver:"):
                    current_sink["driver"] = line.split(":", 1)[1].strip()
                elif line.startswith("State:"):
                    current_sink["state"] = line.split(":", 1)[1].strip()
                elif line.startswith("Sample Specification:"):
                    current_sink["sample_spec"] = line.split(":", 1)[1].strip()
                elif line.startswith("Channel Map:"):
                    current_sink["channel_map"] = line.split(":", 1)[1].strip()
                elif line.startswith("device.") and "=" in line:
                    try:
                        key, value = line.split("=", 1)
                        current_sink["properties"][key.strip()] = value.strip()
                    except Exception:
                        continue
        
        # Add the last sink
        if current_sink:
            sinks.append(current_sink)
        
        return sinks
    
    def enable_optimal_profiles(self) -> None:
        """Enable optimal audio profiles for maximum output availability."""
        print("🔧 Enabling optimal audio profiles...")
        
        for card_id, card in self.audio_cards.items():
            if not card["profiles"]:
                continue
            
            # Find the profile with the most available outputs
            best_profile = None
            max_outputs = 0
            
            for profile in card["profiles"]:
                if profile["available"]:
                    # Count how many ports this profile supports
                    port_count = len([p for p in card["ports"] if p["available"]])
                    if port_count > max_outputs:
                        max_outputs = port_count
                        best_profile = profile["name"]
            
            if best_profile and best_profile != card["active_profile"]:
                print(f"  Setting {card['name']} to {best_profile}")
                self.run_cmd_safe(["pactl", "set-card-profile", card["name"], best_profile])
        
        # Wait for profiles to activate
        import time
        time.sleep(1)
    
    def detect_all(self) -> Dict:
        """Detect all audio and GPU information."""
        print("🔍 Universal Audio Detection Starting...")
        
        # Detect GPUs
        print("  Detecting GPUs via sysfs...")
        self.gpu_info = self.detect_gpus_via_sysfs()
        print(f"    Found {len(self.gpu_info)} GPU devices")
        
        # Detect audio cards via pactl (primary method)
        print("  Detecting audio cards via pactl...")
        self.audio_cards = self.detect_audio_cards_via_pactl()
        
        # Fallback to sysfs if pactl fails
        if not self.audio_cards:
            print("  Fallback: Detecting audio cards via sysfs...")
            self.audio_cards = self.detect_audio_cards_via_sysfs()
        
        print(f"    Found {len(self.audio_cards)} audio cards")
        
        # Get available sinks
        print("  Detecting available audio sinks...")
        sinks = self.get_available_sinks()
        print(f"    Found {len(sinks)} audio sinks")
        
        # Enable optimal profiles
        self.enable_optimal_profiles()
        
        # Compile comprehensive report
        report = {
            "gpus": self.gpu_info,
            "audio_cards": self.audio_cards,
            "sinks": sinks,
            "summary": {
                "total_gpus": len(self.gpu_info),
                "total_audio_cards": len(self.audio_cards),
                "total_sinks": len(sinks),
                "available_outputs": sum(len(card["profiles"]) for card in self.audio_cards.values()),
                "available_ports": sum(len(card["ports"]) for card in self.audio_cards.values())
            }
        }
        
        return report
    
    def print_report(self, report: Dict) -> None:
        """Print a human-readable report."""
        print("\n" + "="*60)
        print("🎮 UNIVERSAL AUDIO DETECTION REPORT")
        print("="*60)
        
        # GPU Summary
        print(f"\n🎮 GPU Devices: {report['summary']['total_gpus']}")
        for gpu_id, gpu in report['gpus'].items():
            print(f"  {gpu_id}: {gpu['name']} ({gpu['type']})")
            print(f"    Vendor: {gpu['vendor_id']}, Device: {gpu['device_id']}")
        
        # Audio Cards Summary
        print(f"\n🔊 Audio Cards: {report['summary']['total_audio_cards']}")
        for card_id, card in report['audio_cards'].items():
            print(f"  {card['name']}: {card['description']}")
            print(f"    Driver: {card['driver']}")
            print(f"    Active Profile: {card['active_profile']}")
            print(f"    Available Profiles: {len(card['profiles'])}")
            print(f"    Available Ports: {len(card['ports'])}")
            
            if card['profiles']:
                print("      Profiles:")
                for profile in card['profiles']:
                    if profile['available']:
                        print(f"        ✓ {profile['name']}: {profile['description']}")
            
            if card['ports']:
                print("      Ports:")
                for port in card['ports']:
                    status = "✓" if port['available'] else "✗"
                    print(f"        {status} {port['name']}: {port['info']}")
        
        # Sinks Summary
        print(f"\n🎵 Audio Sinks: {report['summary']['total_sinks']}")
        for sink in report['sinks']:
            status = "✓" if sink['state'] == 'RUNNING' else "○"
            print(f"  {status} {sink['name']}: {sink['description']}")
            print(f"    Driver: {sink['driver']}, State: {sink['state']}")
        
        # Summary
        print(f"\n📊 SUMMARY:")
        print(f"  Total GPU Devices: {report['summary']['total_gpus']}")
        print(f"  Total Audio Cards: {report['summary']['total_audio_cards']}")
        print(f"  Total Audio Sinks: {report['summary']['total_sinks']}")
        print(f"  Available Outputs: {report['summary']['available_outputs']}")
        print(f"  Available Ports: {report['summary']['available_ports']}")
        
        print("="*60)
    
    def save_report(self, report: Dict, filename: str = "audio_detection_report.json") -> None:
        """Save the detection report to a JSON file."""
        try:
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2)
            print(f"📄 Report saved to {filename}")
        except Exception as e:
            print(f"❌ Failed to save report: {e}")

def main():
    """Main function for command-line usage."""
    detector = UniversalAudioDetector()
    
    try:
        # Detect all audio and GPU information
        report = detector.detect_all()
        
        # Print human-readable report
        detector.print_report(report)
        
        # Save detailed report
        detector.save_report(report)
        
        return 0
        
    except KeyboardInterrupt:
        print("\n⚠️  Detection interrupted by user")
        return 1
    except Exception as e:
        print(f"❌ Detection failed: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
