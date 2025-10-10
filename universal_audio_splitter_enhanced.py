#!/usr/bin/env python3
"""
Universal Audio Splitter Enhanced
=================================

Portable, idempotent, universal audio splitter that works with any Linux system.
Integrates with the outsourced pactl sink management module for comprehensive output display.

Features:
- Universal GPU and audio output detection
- Professional pactl sink management integration
- Portable across distributions
- Safe to run multiple times
- Works with any audio configuration
- Displays ALL detected outputs properly
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

# Import the universal detector and sink manager
try:
    from universal_audio_detector import UniversalAudioDetector
    sys.path.append('..')  # Add parent directory to path
    from pulseaudio_sink_manager import PulseAudioSinkManager
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Please ensure both modules are available:")
    print("  - universal_audio_detector.py")
    print("  - pulseaudio_sink_manager.py")
    sys.exit(1)

APP_ID = "com.universal.AudioSplitter.enhanced"

class EnhancedAudioSplitter:
    """Enhanced audio splitter with professional sink management."""
    
    def __init__(self):
        self.detector = UniversalAudioDetector()
        self.sink_manager = PulseAudioSinkManager()
        self.audio_report = None
        self.pipeline_active = False
        self.pipeline_modules = []
        
    def detect_system(self) -> Dict:
        """Detect all audio and GPU information."""
        print("🔍 Detecting system audio configuration...")
        self.audio_report = self.detector.detect_all()
        return self.audio_report
    
    def get_comprehensive_sink_info(self) -> List[Dict]:
        """Get comprehensive sink information using the professional sink manager."""
        try:
            # Get sinks via professional manager
            sinks = self.sink_manager.get_sinks()
            sink_inputs = self.sink_manager.get_sink_inputs()
            
            # Convert to our format
            comprehensive_sinks = []
            for sink in sinks:
                sink_info = {
                    "id": str(sink.id),
                    "name": sink.name,
                    "description": f"{sink.sample_format} {sink.channels}ch {sink.sample_rate}Hz",
                    "driver": sink.module,
                    "state": sink.state.value,
                    "sample_spec": f"{sink.sample_format} {sink.channels}ch {sink.sample_rate}Hz",
                    "channel_map": f"{sink.channels} channels",
                    "properties": {}
                }
                
                # Add properties if available
                if hasattr(sink, 'properties') and sink.properties:
                    sink_info["properties"] = sink.properties
                
                comprehensive_sinks.append(sink_info)
            
            print(f"✅ Professional sink manager found {len(comprehensive_sinks)} sinks")
            return comprehensive_sinks
            
        except Exception as e:
            print(f"⚠️  Professional sink manager failed: {e}")
            print("  Falling back to basic detection...")
            
            # Fallback to basic detection
            if not self.audio_report:
                return []
            
            # Filter out internal pipeline sinks
            internal_sinks = {"splitter", "compressor", "null", "universal_splitter", "universal_compressor"}
            available_sinks = []
            
            for sink in self.audio_report["sinks"]:
                if sink["name"] not in internal_sinks:
                    available_sinks.append(sink)
            
            return available_sinks
    
    def create_audio_pipeline(self, front_sink: str, rear_l_sink: str, rear_r_sink: str) -> bool:
        """Create the audio splitter pipeline using professional sink management."""
        print("🚀 Creating enhanced audio pipeline...")
        
        try:
            # Stop existing pipeline first
            self.stop_audio_pipeline()
            
            # Create splitter sink using professional manager
            print("  Creating splitter sink...")
            splitter_name = "enhanced_splitter"
            splitter_id = self.sink_manager.create_null_sink(splitter_name, "Enhanced_Audio_Splitter")
            print(f"    Created splitter sink: {splitter_name} (ID: {splitter_id})")
            
            # Create compressor sink
            print("  Creating compressor sink...")
            try:
                compressor_name = "enhanced_compressor"
                compressor_id = self.sink_manager.create_ladspa_sink(
                    compressor_name, 
                    "sc4_1882", 
                    splitter_name,
                    {"threshold_db": -20.0, "ratio": 4.0, "knee_db": 6.0, "attack_ms": 5.0, "release_ms": 100.0, "makeup_gain_db": 0.0}
                )
                print(f"    Compressor enabled: {compressor_name} (ID: {compressor_id})")
            except Exception as e:
                print(f"    Compressor not available: {e}")
                compressor_name = splitter_name
            
            # Create channel splits using professional manager
            print("  Creating L/R channel splits...")
            left_source = self.sink_manager.create_remap_source(
                "enhanced_left", 
                f"{splitter_name}.monitor", 
                channels=1, 
                channel_map="mono", 
                master_channel_map="front-left"
            )
            print(f"    Left channel source created: {left_source}")
            
            right_source = self.sink_manager.create_remap_source(
                "enhanced_right", 
                f"{splitter_name}.monitor", 
                channels=1, 
                channel_map="mono", 
                master_channel_map="front-right"
            )
            print(f"    Right channel source created: {right_source}")
            
            # Route to outputs using professional manager
            if front_sink:
                print(f"  Routing both channels to front: {front_sink}")
                front_loopback = self.sink_manager.create_loopback(
                    "enhanced_left", front_sink, latency_msec=50
                )
                print(f"    Front left loopback: {front_loopback}")
                
                front_loopback2 = self.sink_manager.create_loopback(
                    "enhanced_right", front_sink, latency_msec=50
                )
                print(f"    Front right loopback: {front_loopback2}")
            
            if rear_l_sink:
                print(f"  Routing left channel to rear left: {rear_l_sink}")
                rear_l_loopback = self.sink_manager.create_loopback(
                    "enhanced_left", rear_l_sink, latency_msec=50
                )
                print(f"    Rear left loopback: {rear_l_loopback}")
            
            if rear_r_sink:
                print(f"  Routing right channel to rear right: {rear_r_sink}")
                rear_r_loopback = self.sink_manager.create_loopback(
                    "enhanced_right", rear_r_sink, latency_msec=50
                )
                print(f"    Rear right loopback: {rear_r_loopback}")
            
            # Set default sink
            self.sink_manager.set_default_sink(compressor_name)
            
            self.pipeline_active = True
            print("✅ Enhanced audio pipeline created successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Failed to create enhanced pipeline: {e}")
            self.stop_audio_pipeline()
            return False
    
    def stop_audio_pipeline(self) -> None:
        """Stop the audio pipeline and clean up modules."""
        if not self.pipeline_active:
            return
        
        print("🛑 Stopping enhanced audio pipeline...")
        
        try:
            # Clean up using professional sink manager
            self.sink_manager.delete_sink("enhanced_splitter")
            self.sink_manager.delete_sink("enhanced_compressor")
            
            # Clean up sources
            self.sink_manager.delete_source("enhanced_left")
            self.sink_manager.delete_source("enhanced_right")
            
            print("✅ Enhanced pipeline stopped")
            
        except Exception as e:
            print(f"⚠️  Professional cleanup failed: {e}")
            print("  Manual cleanup may be required")
        
        self.pipeline_active = False

class EnhancedAudioSplitterWindow(Gtk.ApplicationWindow):
    """Enhanced main window with professional sink management display."""
    
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Universal Audio Splitter Enhanced")
        self.set_default_size(900, 1000)
        
        # Initialize the enhanced splitter
        self.splitter = EnhancedAudioSplitter()
        
        # UI setup
        self.setup_ui()
        
        # Initial system detection
        self.refresh_system()
    
    def setup_ui(self):
        """Setup the enhanced user interface."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, 
                        margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        self.set_child(outer)
        
        # Title
        title = Gtk.Label(label="🎛️ Universal Audio Splitter Enhanced")
        title.set_markup("<span size='x-large' weight='bold' color='#4a9eff'>🎛️ Universal Audio Splitter Enhanced</span>")
        outer.append(title)
        
        # System Information Frame
        system_frame = self._create_frame("🔍 System Information", [])
        outer.append(system_frame)
        self.system_info_label = Gtk.Label(label="Detecting system...")
        self.system_info_label.set_markup("<span color='#4a9eff'>🔍 Detecting system...</span>")
        system_frame.get_child().append(self.system_info_label)
        
        # Comprehensive Output Display Frame
        output_display_frame = self._create_frame("🎵 All Detected Outputs", [])
        outer.append(output_display_frame)
        
        # Create scrolled window for outputs
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_min_content_height(200)
        output_display_frame.get_child().append(scrolled_window)
        
        # Create output list
        self.output_list = Gtk.ListBox()
        self.output_list.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled_window.set_child(self.output_list)
        
        # Output Selection Frame
        output_selection_frame = self._create_frame("🎮 Output Selection", [])
        outer.append(output_selection_frame)
        output_grid = Gtk.Grid(column_spacing=12, row_spacing=8, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        output_selection_frame.get_child().append(output_grid)
        
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
            
            # Update comprehensive output display
            self.update_output_display()
            
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
            info_text += f"  {card_id}: {card['description']}\n"
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
    
    def update_output_display(self):
        """Update the comprehensive output display using professional sink manager."""
        # Clear existing list
        while self.output_list.get_first_child():
            self.output_list.remove(self.output_list.get_first_child())
        
        try:
            # Get comprehensive sink info
            sinks = self.splitter.get_comprehensive_sink_info()
            
            # Add header
            header_row = Gtk.ListBoxRow()
            header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            header_row.set_child(header_box)
            
            header_box.append(Gtk.Label(label="ID", xalign=0))
            header_box.append(Gtk.Label(label="Name", xalign=0))
            header_box.append(Gtk.Label(label="Description", xalign=0))
            header_box.append(Gtk.Label(label="Driver", xalign=0))
            header_box.append(Gtk.Label(label="State", xalign=0))
            header_box.append(Gtk.Label(label="Format", xalign=0))
            
            # Style header
            header_row.add_css_class("header")
            self.output_list.append(header_row)
            
            # Add each sink
            for sink in sinks:
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.set_child(box)
                
                # ID
                id_label = Gtk.Label(label=sink.get('id', 'N/A'), xalign=0)
                id_label.set_size_request(50, -1)
                box.append(id_label)
                
                # Name
                name_label = Gtk.Label(label=sink.get('name', 'N/A'), xalign=0)
                name_label.set_size_request(150, -1)
                box.append(name_label)
                
                # Description
                desc_label = Gtk.Label(label=sink.get('description', 'N/A'), xalign=0)
                desc_label.set_size_request(200, -1)
                box.append(desc_label)
                
                # Driver
                driver_label = Gtk.Label(label=sink.get('driver', 'N/A'), xalign=0)
                driver_label.set_size_request(100, -1)
                box.append(driver_label)
                
                # State
                state = sink.get('state', 'UNKNOWN')
                state_label = Gtk.Label(label=state, xalign=0)
                state_label.set_size_request(80, -1)
                
                # Color code state
                if state == 'RUNNING':
                    state_label.set_markup("<span color='#4caf50'>RUNNING</span>")
                elif state == 'SUSPENDED':
                    state_label.set_markup("<span color='#ff9800'>SUSPENDED</span>")
                elif state == 'IDLE':
                    state_label.set_markup("<span color='#2196f3'>IDLE</span>")
                else:
                    state_label.set_markup("<span color='#9e9e9e'>UNKNOWN</span>")
                
                box.append(state_label)
                
                # Format
                format_label = Gtk.Label(label=sink.get('sample_spec', 'N/A'), xalign=0)
                format_label.set_size_request(120, -1)
                box.append(format_label)
                
                self.output_list.append(row)
            
            print(f"✅ Display updated with {len(sinks)} outputs")
            
        except Exception as e:
            print(f"❌ Failed to update output display: {e}")
            # Add error row
            error_row = Gtk.ListBoxRow()
            error_label = Gtk.Label(label=f"Error loading outputs: {e}")
            error_label.set_markup(f"<span color='#ff6b6b'>Error loading outputs: {e}</span>")
            error_row.set_child(error_label)
            self.output_list.append(error_row)
    
    def update_output_selection(self):
        """Update the output selection dropdowns."""
        try:
            sinks = self.splitter.get_comprehensive_sink_info()
            
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
                
        except Exception as e:
            print(f"❌ Failed to update output selection: {e}")
    
    def start_pipeline(self, *args):
        """Start the audio pipeline."""
        try:
            # Get selected sinks
            front_idx = self.front_combo.get_selected()
            rear_l_idx = self.rear_l_combo.get_selected()
            rear_r_idx = self.rear_r_combo.get_selected()
            
            # Get sink names
            sinks = self.splitter.get_comprehensive_sink_info()
            
            front_sink = sinks[front_idx - 1]['name'] if front_idx > 0 else None
            rear_l_sink = sinks[rear_l_idx - 1]['name'] if rear_l_idx > 0 else None
            rear_r_sink = sinks[rear_r_idx - 1]['name'] if rear_r_idx > 0 else None
            
            # Create pipeline
            if self.splitter.create_audio_pipeline(front_sink, rear_l_sink, rear_r_sink):
                self.start_btn.set_sensitive(False)
                self.stop_btn.set_sensitive(True)
                self.status_label.set_markup("<span color='#4caf50'>Pipeline active</span>")
                
                # Refresh display to show new pipeline
                self.refresh_system()
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
            
            # Refresh display to show pipeline removal
            self.refresh_system()
            
        except Exception as e:
            self.status_label.set_markup(f"<span color='#ff6b6b'>Error: {e}</span>")

class EnhancedAudioSplitterApp(Gtk.Application):
    """Application class for the enhanced universal audio splitter."""
    
    def __init__(self):
        super().__init__(application_id=APP_ID)
    
    def do_activate(self, *args):
        """Activate the application."""
        window = EnhancedAudioSplitterWindow(self)
        window.present()

def main():
    """Main function."""
    app = EnhancedAudioSplitterApp()
    return app.run()

if __name__ == "__main__":
    sys.exit(main())
