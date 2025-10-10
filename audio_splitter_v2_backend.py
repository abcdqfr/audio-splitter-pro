#!/usr/bin/env python3
"""
Audio Splitter v2 Backend - Focused on Sink Management & Channel Routing
=======================================================================

Rebased on v2 with focus on:
- Sink manipulation capabilities
- Cleanup functionality
- Independent L/R channel mapping
- Visibility of ALL DP sinks
- Integration with outsourced pactl sink manager
"""

import gi
import subprocess
import shlex
from typing import List, Tuple, Optional, Dict
import os
import json
import sys

# Use the built-in tomllib in Python 3.11+, fallback to tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

# Import the outsourced pactl sink manager
try:
    sys.path.append('..')
    from pulseaudio_sink_manager import PulseAudioSinkManager
    SINK_MANAGER_AVAILABLE = True
except ImportError:
    SINK_MANAGER_AVAILABLE = False
    print("⚠️  PulseAudio sink manager not available, using basic functionality")

APP_ID = "com.brandon.AudioSplitterGUI.v2.backend"

# Configuration
CONFIG = {
    "pipeline": {
        "left_source_name": "splitter_left", 
        "right_source_name": "splitter_right",
        "splitter_sink_name": "splitter", 
        "compressor_sink_name": "compressor",
    },
    "ladspa_plugins": {"compressor_plugin": "sc4_1882"},
    "compressor_defaults": {
        "threshold_db": -20.0, "ratio": 4.0, "knee_db": 6.0,
        "attack_ms": 5.0, "release_ms": 100.0, "makeup_gain_db": 0.0,
    }
}

SETTINGS_FILE = "compressor_settings.json"

class BackendAudioManager:
    """Backend audio management with sink manipulation and cleanup."""
    
    def __init__(self):
        self.sink_manager = PulseAudioSinkManager() if SINK_MANAGER_AVAILABLE else None
        self.active_modules = []
        self.active_sinks = []
        
    def get_all_sinks(self) -> List[Dict]:
        """Get ALL available sinks including DP sinks."""
        if self.sink_manager:
            try:
                # Use professional sink manager
                sinks = self.sink_manager.get_sinks()
                return [{"id": str(s.id), "name": s.name, "state": s.state.value, 
                        "description": f"{s.sample_format} {s.channels}ch {s.sample_rate}Hz"} 
                       for s in sinks]
            except Exception as e:
                print(f"Professional sink manager failed: {e}")
        
        # Fallback to basic detection
        return self._get_sinks_basic()
    
    def _get_sinks_basic(self) -> List[Dict]:
        """Basic sink detection fallback."""
        try:
            result = subprocess.run(['pactl', 'list', 'short', 'sinks'], 
                                  capture_output=True, text=True, check=True)
            sinks = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        sinks.append({
                            "id": parts[0],
                            "name": parts[1],
                            "state": parts[4] if len(parts) > 4 else "UNKNOWN",
                            "description": parts[2] if len(parts) > 2 else "Unknown"
                        })
            return sinks
        except Exception as e:
            print(f"Basic sink detection failed: {e}")
            return []
    
    def create_splitter_pipeline(self, left_sink: str, right_sink: str) -> bool:
        """Create independent L/R channel splitter pipeline."""
        print(f"🚀 Creating L/R splitter pipeline: Left={left_sink}, Right={right_sink}")
        
        try:
            # Clean up existing pipeline
            self.cleanup_pipeline()
            
            # Create splitter sink
            splitter_name = "lr_splitter"
            if self.sink_manager:
                splitter_id = self.sink_manager.create_null_sink(splitter_name, "L/R_Channel_Splitter")
                print(f"  Created splitter sink: {splitter_name} (ID: {splitter_id})")
            else:
                result = subprocess.run([
                    'pactl', 'load-module', 'module-null-sink',
                    f'sink_name={splitter_name}',
                    'sink_properties=device.description="L/R_Channel_Splitter"'
                ], capture_output=True, text=True, check=True)
                splitter_id = result.stdout.strip()
                self.active_modules.append(("module-null-sink", splitter_id))
                print(f"  Created splitter sink: {splitter_name}")
            
            # Create left channel source
            left_source = self._create_channel_source("left_channel", f"{splitter_name}.monitor", "front-left")
            
            # Create right channel source  
            right_source = self._create_channel_source("right_channel", f"{splitter_name}.monitor", "front-right")
            
            # Route left channel to left sink
            if left_sink:
                self._create_loopback("left_channel", left_sink)
                print(f"  Left channel routed to: {left_sink}")
            
            # Route right channel to right sink
            if right_sink:
                self._create_loopback("right_channel", right_sink)
                print(f"  Right channel routed to: {right_sink}")
            
            # Set default sink
            subprocess.run(['pactl', 'set-default-sink', splitter_name], check=False)
            
            print("✅ L/R splitter pipeline created successfully!")
            return True
            
        except Exception as e:
            print(f"❌ Pipeline creation failed: {e}")
            self.cleanup_pipeline()
            return False
    
    def _create_channel_source(self, name: str, master: str, channel: str) -> str:
        """Create a single channel source."""
        if self.sink_manager:
            try:
                source_id = self.sink_manager.create_remap_source(
                    name, master, channels=1, channel_map="mono", master_channel_map=channel
                )
                self.active_modules.append(("module-remap-source", source_id))
                return source_id
            except Exception as e:
                print(f"  Professional source creation failed: {e}")
        
        # Fallback to basic creation
        result = subprocess.run([
            'pactl', 'load-module', 'module-remap-source',
            f'source_name={name}',
            f'master={master}',
            'channels=1',
            'channel_map=mono',
            f'master_channel_map={channel}'
        ], capture_output=True, text=True, check=True)
        
        source_id = result.stdout.strip()
        self.active_modules.append(("module-remap-source", source_id))
        return source_id
    
    def _create_loopback(self, source: str, sink: str) -> str:
        """Create a loopback connection."""
        if self.sink_manager:
            try:
                loopback_id = self.sink_manager.create_loopback(source, sink, latency_msec=50)
                self.active_modules.append(("module-loopback", loopback_id))
                return loopback_id
            except Exception as e:
                print(f"  Professional loopback creation failed: {e}")
        
        # Fallback to basic creation
        result = subprocess.run([
            'pactl', 'load-module', 'module-loopback',
            f'source={source}',
            f'sink={sink}',
            'latency_msec=50'
        ], capture_output=True, text=True, check=True)
        
        loopback_id = result.stdout.strip()
        self.active_modules.append(("module-loopback", loopback_id))
        return loopback_id
    
    def cleanup_pipeline(self) -> None:
        """Clean up all active pipeline modules."""
        if not self.active_modules:
            return
        
        print("🧹 Cleaning up pipeline modules...")
        
        # Unload modules in reverse order
        for module_type, module_id in reversed(self.active_modules):
            try:
                if self.sink_manager:
                    # Try professional cleanup first
                    if module_type == "module-null-sink":
                        self.sink_manager.delete_sink("lr_splitter")
                    elif module_type == "module-remap-source":
                        if "left_channel" in module_id:
                            self.sink_manager.delete_source("left_channel")
                        elif "right_channel" in module_id:
                            self.sink_manager.delete_source("right_channel")
                    elif module_type == "module-loopback":
                        self.sink_manager.delete_module(module_id)
                else:
                    # Basic cleanup
                    subprocess.run(['pactl', 'unload-module', module_id], check=False)
                
                print(f"  Cleaned up {module_type}: {module_id}")
                
            except Exception as e:
                print(f"  Warning: Failed to clean up {module_type}: {e}")
        
        self.active_modules.clear()
        print("✅ Pipeline cleanup complete")
    
    def get_dp_sinks(self) -> List[Dict]:
        """Get specifically DP (DisplayPort) sinks."""
        all_sinks = self.get_all_sinks()
        dp_sinks = []
        
        for sink in all_sinks:
            name = sink["name"].lower()
            description = sink["description"].lower()
            
            # Check for DP indicators
            if any(indicator in name or indicator in description 
                   for indicator in ["dp", "displayport", "hdmi", "navi", "ati"]):
                dp_sinks.append(sink)
        
        return dp_sinks

class AudioSplitterWindow(Gtk.ApplicationWindow):
    """Main window based on v2 with backend focus."""
    
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Audio Splitter v2 Backend")
        self.set_default_size(700, 800)
        
        # Initialize backend manager
        self.backend = BackendAudioManager()
        
        # UI setup
        self.setup_ui()
        
        # Initial refresh
        self.refresh_sinks()
    
    def setup_ui(self):
        """Setup the user interface."""
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, 
                        margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        self.set_child(outer)
        
        # Title
        title = Gtk.Label(label="🎛️ Audio Splitter v2 Backend")
        title.set_markup("<span size='x-large' weight='bold' color='#4a9eff'>🎛️ Audio Splitter v2 Backend</span>")
        outer.append(title)
        
        # All Sinks Display
        sinks_frame = self._create_frame("🔍 All Available Sinks", [])
        outer.append(sinks_frame)
        
        # Scrolled sink list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(200)
        sinks_frame.get_child().append(scrolled)
        
        self.sinks_list = Gtk.ListBox()
        self.sinks_list.set_selection_mode(Gtk.SelectionMode.NONE)
        scrolled.set_child(self.sinks_list)
        
        # DP Sinks Display
        dp_frame = self._create_frame("🎮 DP/HDMI Sinks", [])
        outer.append(dp_frame)
        
        dp_scrolled = Gtk.ScrolledWindow()
        dp_scrolled.set_min_content_height(150)
        dp_frame.get_child().append(dp_scrolled)
        
        self.dp_list = Gtk.ListBox()
        self.dp_list.set_selection_mode(Gtk.SelectionMode.NONE)
        dp_scrolled.set_child(self.dp_list)
        
        # Channel Selection
        channel_frame = self._create_frame("🎵 Channel Routing", [])
        outer.append(channel_frame)
        channel_grid = Gtk.Grid(column_spacing=12, row_spacing=8, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        channel_frame.get_child().append(channel_grid)
        
        # Left channel
        left_label = Gtk.Label(label="Left Channel Sink:", xalign=0)
        self.left_combo = Gtk.DropDown()
        channel_grid.attach(left_label, 0, 0, 1, 1)
        channel_grid.attach(self.left_combo, 1, 0, 1, 1)
        
        # Right channel
        right_label = Gtk.Label(label="Right Channel Sink:", xalign=0)
        self.right_combo = Gtk.DropDown()
        channel_grid.attach(right_label, 0, 1, 1, 1)
        channel_grid.attach(self.right_combo, 1, 1, 1, 1)
        
        # Control buttons
        button_frame = self._create_frame("🎮 Controls", [])
        outer.append(button_frame)
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_frame.get_child().append(button_box)
        
        self.refresh_btn = Gtk.Button(label="🔄 Refresh Sinks")
        self.refresh_btn.connect("clicked", self.refresh_sinks)
        button_box.append(self.refresh_btn)
        
        self.start_btn = Gtk.Button(label="🚀 Start L/R Split")
        self.start_btn.connect("clicked", self.start_split)
        button_box.append(self.start_btn)
        
        self.stop_btn = Gtk.Button(label="⏹️ Stop Split")
        self.stop_btn.connect("clicked", self.stop_split)
        self.stop_btn.set_sensitive(False)
        button_box.append(self.stop_btn)
        
        # Status
        status_frame = self._create_frame("📊 Status", [])
        outer.append(status_frame)
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_markup("<span color='#4caf50'>Ready</span>")
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
    
    def refresh_sinks(self, *args):
        """Refresh all sink displays."""
        try:
            # Get all sinks
            all_sinks = self.backend.get_all_sinks()
            self.update_sinks_display(self.sinks_list, all_sinks, "All Sinks")
            
            # Get DP sinks
            dp_sinks = self.backend.get_dp_sinks()
            self.update_sinks_display(self.dp_list, dp_sinks, "DP/HDMI Sinks")
            
            # Update selection dropdowns
            self.update_selection_dropdowns(all_sinks)
            
            self.status_label.set_markup(f"<span color='#4caf50'>Found {len(all_sinks)} total sinks, {len(dp_sinks)} DP sinks</span>")
            
        except Exception as e:
            self.status_label.set_markup(f"<span color='#ff6b6b'>Refresh failed: {e}</span>")
    
    def update_sinks_display(self, listbox: Gtk.ListBox, sinks: List[Dict], title: str):
        """Update a sink list display."""
        # Clear existing
        while listbox.get_first_child():
            listbox.remove(listbox.get_first_child())
        
        # Add header
        header_row = Gtk.ListBoxRow()
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_row.set_child(header_box)
        
        header_box.append(Gtk.Label(label="ID", xalign=0))
        header_box.append(Gtk.Label(label="Name", xalign=0))
        header_box.append(Gtk.Label(label="State", xalign=0))
        header_box.append(Gtk.Label(label="Description", xalign=0))
        
        header_row.add_css_class("header")
        listbox.append(header_row)
        
        # Add sinks
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
            
            # Description
            desc_label = Gtk.Label(label=sink.get('description', 'N/A'), xalign=0)
            desc_label.set_size_request(200, -1)
            box.append(desc_label)
            
            listbox.append(row)
    
    def update_selection_dropdowns(self, sinks: List[Dict]):
        """Update the channel selection dropdowns."""
        sink_list = Gtk.StringList()
        sink_list.append("[ Disabled ]")
        
        for sink in sinks:
            display_name = f"{sink['name']}: {sink['description']}"
            sink_list.append(display_name)
        
        self.left_combo.set_model(sink_list)
        self.right_combo.set_model(sink_list)
        
        # Set defaults
        if len(sinks) >= 1:
            self.left_combo.set_selected(1)
        if len(sinks) >= 2:
            self.right_combo.set_selected(2)
    
    def start_split(self, *args):
        """Start the L/R channel split."""
        try:
            # Get selected sinks
            left_idx = self.left_combo.get_selected()
            right_idx = self.right_combo.get_selected()
            
            if left_idx < 0 and right_idx < 0:
                self.status_label.set_markup("<span color='#ff9800'>Please select at least one sink</span>")
                return
            
            # Get sink names
            all_sinks = self.backend.get_all_sinks()
            left_sink = all_sinks[left_idx - 1]['name'] if left_idx > 0 else None
            right_sink = all_sinks[right_idx - 1]['name'] if right_idx > 0 else None
            
            # Create pipeline
            if self.backend.create_splitter_pipeline(left_sink, right_sink):
                self.start_btn.set_sensitive(False)
                self.stop_btn.set_sensitive(True)
                self.status_label.set_markup("<span color='#4caf50'>L/R split active</span>")
                
                # Refresh to show new pipeline
                self.refresh_sinks()
            else:
                self.status_label.set_markup("<span color='#ff6b6b'>Pipeline creation failed</span>")
                
        except Exception as e:
            self.status_label.set_markup(f"<span color='#ff6b6b'>Error: {e}</span>")
    
    def stop_split(self, *args):
        """Stop the L/R channel split."""
        try:
            self.backend.cleanup_pipeline()
            self.start_btn.set_sensitive(True)
            self.stop_btn.set_sensitive(False)
            self.status_label.set_markup("<span color='#4caf50'>Split stopped</span>")
            
            # Refresh to show pipeline removal
            self.refresh_sinks()
            
        except Exception as e:
            self.status_label.set_markup(f"<span color='#ff6b6b'>Error: {e}</span>")

class AudioSplitterApp(Gtk.Application):
    """Application class."""
    
    def __init__(self):
        super().__init__(application_id=APP_ID)
    
    def do_activate(self, *args):
        """Activate the application."""
        window = AudioSplitterWindow(self)
        window.present()

def main():
    """Main function."""
    app = AudioSplitterApp()
    return app.run()

if __name__ == "__main__":
    sys.exit(main())
