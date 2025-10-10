#!/usr/bin/env python3
"""
Universal Audio Splitter
========================

Portable, idempotent, universal audio splitter that works with any Linux system.
Integrates with the universal audio detector for comprehensive output management.

Features:
- Universal GPU and audio output detection
- Portable across distributions
- Safe to run multiple times
- Works with any audio configuration
- Professional audio pipeline management
"""

import gi
import subprocess
import json
import os
import sys
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Use the built-in tomllib in Python 3.11+, fallback to tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

# Import the universal detector
try:
    from universal_audio_detector import UniversalAudioDetector
except ImportError:
    print("❌ Universal audio detector not found. Please ensure universal_audio_detector.py is in the same directory.")
    sys.exit(1)

APP_ID = "com.universal.AudioSplitter"

class UniversalAudioSplitter:
    """Universal audio splitter with comprehensive output detection."""
    
    def __init__(self):
        self.detector = UniversalAudioDetector()
        self.audio_report = None
        self.pipeline_active = False
        self.pipeline_modules = []
        
    def detect_system(self) -> Dict:
        """Detect all audio and GPU information."""
        print("🔍 Detecting system audio configuration...")
        self.audio_report = self.detector.detect_all()
        return self.audio_report
    
    def get_available_sinks(self) -> List[Dict]:
        """Get list of available audio sinks for routing."""
        if not self.audio_report:
            return []
        
        # Filter out internal pipeline sinks
        internal_sinks = {"splitter", "compressor", "null"}
        available_sinks = []
        
        for sink in self.audio_report["sinks"]:
            if sink["name"] not in internal_sinks:
                available_sinks.append(sink)
        
        return available_sinks
    
    def create_audio_pipeline(self, front_sink: str, rear_l_sink: str, rear_r_sink: str) -> bool:
        """Create the audio splitter pipeline."""
        print("🚀 Creating universal audio pipeline...")
        
        try:
            # Stop existing pipeline first
            self.stop_audio_pipeline()
            
            # Create splitter sink
            print("  Creating splitter sink...")
            result = subprocess.run([
                "pactl", "load-module", "module-null-sink",
                "sink_name=universal_splitter",
                "sink_properties=device.description=Universal_Audio_Splitter"
            ], capture_output=True, text=True, check=True)
            
            splitter_module = result.stdout.strip()
            self.pipeline_modules.append(("module-null-sink", splitter_module))
            
            # Create compressor sink
            print("  Creating compressor sink...")
            result = subprocess.run([
                "pactl", "load-module", "module-ladspa-sink",
                "sink_name=universal_compressor",
                "sink_master=universal_splitter",
                "plugin=sc4_1882",
                "label=sc4",
                "control=1,5.0,100.0,-20.0,4.0,6.0,0.0"
            ], capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                compressor_module = result.stdout.strip()
                self.pipeline_modules.append(("module-ladspa-sink", compressor_module))
                print("    Compressor enabled")
            else:
                print("    Compressor not available, using basic splitter")
            
            # Create channel splits
            print("  Creating L/R channel splits...")
            result = subprocess.run([
                "pactl", "load-module", "module-remap-source",
                "source_name=universal_left",
                "master=universal_splitter.monitor",
                "channels=1",
                "channel_map=mono",
                "master_channel_map=front-left"
            ], capture_output=True, text=True, check=True)
            
            left_module = result.stdout.strip()
            self.pipeline_modules.append(("module-remap-source", left_module))
            
            result = subprocess.run([
                "pactl", "load-module", "module-remap-source",
                "source_name=universal_right",
                "master=universal_splitter.monitor",
                "channels=1",
                "channel_map=mono",
                "master_channel_map=front-right"
            ], capture_output=True, text=True, check=True)
            
            right_module = result.stdout.strip()
            self.pipeline_modules.append(("module-remap-source", right_module))
            
            # Route to outputs
            if front_sink:
                print(f"  Routing both channels to front: {front_sink}")
                result = subprocess.run([
                    "pactl", "load-module", "module-loopback",
                    "source=universal_left",
                    f"sink={front_sink}",
                    "latency_msec=50"
                ], capture_output=True, text=True, check=True)
                
                front_module = result.stdout.strip()
                self.pipeline_modules.append(("module-loopback", front_module))
                
                result = subprocess.run([
                    "pactl", "load-module", "module-loopback",
                    "source=universal_right",
                    f"sink={front_sink}",
                    "latency_msec=50"
                ], capture_output=True, text=True, check=True)
                
                front_module2 = result.stdout.strip()
                self.pipeline_modules.append(("module-loopback", front_module2))
            
            if rear_l_sink:
                print(f"  Routing left channel to rear left: {rear_l_sink}")
                result = subprocess.run([
                    "pactl", "load-module", "module-loopback",
                    "source=universal_left",
                    f"sink={rear_l_sink}",
                    "latency_msec=50"
                ], capture_output=True, text=True, check=True)
                
                rear_l_module = result.stdout.strip()
                self.pipeline_modules.append(("module-loopback", rear_l_module))
            
            if rear_r_sink:
                print(f"  Routing right channel to rear right: {rear_r_sink}")
                result = subprocess.run([
                    "pactl", "load-module", "module-loopback",
                    "source=universal_right",
                    f"sink={rear_r_sink}",
                    "latency_msec=50"
                ], capture_output=True, text=True, check=True)
                
                rear_r_module = result.stdout.strip()
                self.pipeline_modules.append(("module-loopback", rear_r_module))
            
            # Set default sink
            subprocess.run(["pactl", "set-default-sink", "universal_compressor"], check=False)
            
            self.pipeline_active = True
            print("✅ Universal audio pipeline created successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to create pipeline: {e}")
            self.stop_audio_pipeline()
            return False
    
    def stop_audio_pipeline(self) -> None:
        """Stop the audio pipeline and clean up modules."""
        if not self.pipeline_modules:
            return
        
        print("🛑 Stopping universal audio pipeline...")
        
        # Unload modules in reverse order
        for module_type, module_id in reversed(self.pipeline_modules):
            try:
                subprocess.run(["pactl", "unload-module", module_id], check=False)
                print(f"  Unloaded {module_type}: {module_id}")
            except Exception as e:
                print(f"  Warning: Failed to unload {module_type}: {e}")
        
        self.pipeline_modules.clear()
        self.pipeline_active = False
        print("✅ Pipeline stopped")

class UniversalAudioSplitterWindow(Gtk.ApplicationWindow):
    """Main window for the universal audio splitter."""
    
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Universal Audio Splitter")
        self.set_default_size(800, 900)
        
        # Initialize the universal splitter
        self.splitter = UniversalAudioSplitter()
        
        # UI setup
        self.setup_ui()
        
        # Initial system detection
        self.refresh_system()
    
    def setup_ui(self):
        """Setup the user interface."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, 
                        margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        self.set_child(outer)
        
        # Title
        title = Gtk.Label(label="🎛️ Universal Audio Splitter")
        title.set_markup("<span size='x-large' weight='bold' color='#4a9eff'>🎛️ Universal Audio Splitter</span>")
        outer.append(title)
        
        # System Information Frame
        system_frame = self._create_frame("🔍 System Information", [])
        outer.append(system_frame)
        self.system_info_label = Gtk.Label(label="Detecting system...")
        self.system_info_label.set_markup("<span color='#4a9eff'>🔍 Detecting system...</span>")
        system_frame.get_child().append(self.system_info_label)
        
        # Output Selection Frame
        output_frame = self._create_frame("🎵 Output Selection", [])
        outer.append(output_frame)
        output_grid = Gtk.Grid(column_spacing=12, row_spacing=8, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        output_frame.get_child().append(output_grid)
        
        # Front output
        front_label = Gtk.Label(label="Front Output:", xalign=0)
        self.front_combo = Gtk.DropDown()
        output_grid.attach(front_label, 0, 0, 1, 1)
        output_grid.attach(self.front_combo, 1, 0, 1, 1)
        
        # Rear Left output
        rear_l_label = Gtk.Label(label="Rear Left Output:", xalign=0)
        self.rear_l_combo = Gtk.DropDown()
        output_grid.attach(rear_l_label, 0, 1, 1, 1)
        output_grid.attach(self.rear_l_combo, 1, 1, 1, 1)
        
        # Rear Right output
        rear_r_label = Gtk.Label(label="Rear Right Output:", xalign=0)
        self.rear_r_combo = Gtk.DropDown()
        output_grid.attach(rear_r_label, 0, 2, 1, 1)
        output_grid.attach(self.rear_r_combo, 1, 2, 1, 1)
        
        # Control Buttons
        button_frame = self._create_frame("🎮 Controls", [])
        outer.append(button_frame)
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_frame.get_child().append(button_box)
        
        self.refresh_btn = Gtk.Button(label="🔄 Refresh System")
        self.refresh_btn.connect("clicked", self.refresh_system)
        button_box.append(self.refresh_btn)
        
        self.start_btn = Gtk.Button(label="🚀 Start Pipeline")
        self.start_btn.connect("clicked", self.start_pipeline)
        button_box.append(self.start_btn)
        
        self.stop_btn = Gtk.Button(label="⏹️ Stop Pipeline")
        self.stop_btn.connect("clicked", self.stop_pipeline)
        self.stop_btn.set_sensitive(False)
        button_box.append(self.stop_btn)
        
        # Status Frame
        status_frame = self._create_frame("📊 Status", [])
        outer.append(status_frame)
        self.status_label = Gtk.Label(label="Ready to detect system")
        self.status_label.set_markup("<span color='#4caf50'>Ready to detect system</span>")
        status_frame.get_child().append(self.status_label)
    
    def _create_frame(self, title: str, widgets: List[Tuple[str, Gtk.Widget]]) -> Gtk.Frame:
        """Create a frame with title and optional widgets."""
        frame = Gtk.Frame(label=title)
        if widgets:
            grid = Gtk.Grid(column_spacing=12, row_spacing=8, 
                           margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
            frame.set_child(grid)
            for i, (label, widget) in enumerate(widgets):
                grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
                widget.set_hexpand(True)
                grid.attach(widget, 1, i, 1, 1)
        else:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                         margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
            frame.set_child(box)
        return frame
    
    def refresh_system(self, *args):
        """Refresh system detection and update UI."""
        try:
            # Detect system
            report = self.splitter.detect_system()
            
            # Update system info display
            self.update_system_info(report)
            
            # Update output selection
            self.update_output_selection()
            
            # Update status
            self.status_label.set_markup("<span color='#4caf50'>System detected successfully</span>")
            
        except Exception as e:
            self.status_label.set_markup(f"<span color='#ff6b6b'>Detection failed: {e}</span>")
    
    def update_system_info(self, report: Dict):
        """Update the system information display."""
        info_text = f"""<b>🎮 GPU Devices: {report['summary']['total_gpus']}</b>
"""
        
        for gpu_id, gpu in report['gpus'].items():
            info_text += f"  {gpu_id}: {gpu['name']} ({gpu['type']})\n"
        
        info_text += f"\n<b>🔊 Audio Cards: {report['summary']['total_audio_cards']}</b>\n"
        
        for card_id, card in report['audio_cards'].items():
            info_text += f"  {card['name']}: {card['description']}\n"
            info_text += f"    Active Profile: {card['active_profile']}\n"
            info_text += f"    Available Profiles: {len(card['profiles'])}\n"
            info_text += f"    Available Ports: {len(card['ports'])}\n"
        
        info_text += f"\n<b>🎵 Audio Sinks: {report['summary']['total_sinks']}</b>\n"
        
        for sink in report['sinks'][:5]:  # Show first 5 sinks
            status = "✓" if sink['state'] == 'RUNNING' else "○"
            info_text += f"  {status} {sink['name']}: {sink['description']}\n"
        
        if len(report['sinks']) > 5:
            info_text += f"  ... and {len(report['sinks']) - 5} more\n"
        
        self.system_info_label.set_markup(info_text)
    
    def update_output_selection(self):
        """Update the output selection dropdowns."""
        sinks = self.splitter.get_available_sinks()
        
        # Create string list for dropdowns
        sink_list = Gtk.StringList()
        sink_list.append("[ Disabled ]")
        
        for sink in sinks:
            display_name = f"{sink['name']}: {sink['description']}"
            sink_list.append(display_name)
        
        # Update dropdowns
        self.front_combo.set_model(sink_list)
        self.rear_l_combo.set_model(sink_list)
        self.rear_r_combo.set_model(sink_list)
        
        # Set default selections
        if len(sinks) >= 1:
            self.front_combo.set_selected(1)  # First available sink
        if len(sinks) >= 2:
            self.rear_l_combo.set_selected(2)  # Second available sink
        if len(sinks) >= 3:
            self.rear_r_combo.set_selected(3)  # Third available sink
    
    def start_pipeline(self, *args):
        """Start the audio pipeline."""
        try:
            # Get selected sinks
            front_idx = self.front_combo.get_selected()
            rear_l_idx = self.rear_l_combo.get_selected()
            rear_r_idx = self.rear_r_combo.get_selected()
            
            # Get sink names
            sinks = self.splitter.get_available_sinks()
            
            front_sink = sinks[front_idx - 1]['name'] if front_idx > 0 else None
            rear_l_sink = sinks[rear_l_idx - 1]['name'] if rear_l_idx > 0 else None
            rear_r_sink = sinks[rear_r_idx - 1]['name'] if rear_r_idx > 0 else None
            
            # Create pipeline
            if self.splitter.create_audio_pipeline(front_sink, rear_l_sink, rear_r_sink):
                self.start_btn.set_sensitive(False)
                self.stop_btn.set_sensitive(True)
                self.status_label.set_markup("<span color='#4caf50'>Pipeline active</span>")
            else:
                self.status_label.set_markup("<span color='#ff6b6b'>Pipeline creation failed</span>")
                
        except Exception as e:
            self.status_label.set_markup(f"<span color='#ff6b6b'>Error: {e}</span>")
    
    def stop_pipeline(self, *args):
        """Stop the audio pipeline."""
        try:
            self.splitter.stop_audio_pipeline()
            self.start_btn.set_sensitive(True)
            self.stop_btn.set_sensitive(False)
            self.status_label.set_markup("<span color='#4caf50'>Pipeline stopped</span>")
            
        except Exception as e:
            self.status_label.set_markup(f"<span color='#ff6b6b'>Error: {e}</span>")

class UniversalAudioSplitterApp(Gtk.Application):
    """Application class for the universal audio splitter."""
    
    def __init__(self):
        super().__init__(application_id=APP_ID)
    
    def do_activate(self, *args):
        """Activate the application."""
        window = UniversalAudioSplitterWindow(self)
        window.present()

def main():
    """Main function."""
    app = UniversalAudioSplitterApp()
    return app.run()

if __name__ == "__main__":
    sys.exit(main())
