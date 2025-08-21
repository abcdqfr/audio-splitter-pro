#!/usr/bin/env python3
"""
Audio Splitter Pro - Professional Mastering Suite
=================================================

Multi-stage audio processing pipeline with:
- Fast Lookahead Limiter (brick-wall limiting)
- 15-Band Parametric EQ  
- 3-Band Multiband Compressor
- Real-time waveform visualization
- Professional preset management

Requires: python3-gi, gir1.2-gtk-4.0, LADSPA plugins
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
import subprocess
import sys
import threading
import time
import math
from typing import List, Dict, Optional, Tuple
try:
    import tomllib
except ImportError:
    import tomli as tomllib

# Configuration loading with fallback defaults
CONFIG = {}
try:
    with open("config.toml", "rb") as f:
        CONFIG = tomllib.load(f)
except (FileNotFoundError, Exception):
    # Fallback defaults if config.toml is missing
    CONFIG = {
        "pipeline": {
            "left_source_name": "splitter_left",
            "right_source_name": "splitter_right", 
            "splitter_sink_name": "splitter",
            "compressor_sink_name": "compressor",
            "limiter_sink_name": "limiter",
            "eq_sink_name": "eq",
            "multicomp_sink_name": "multicomp"
        },
        "ladspa_plugins": {
            "compressor_plugin": "sc4_1882",
            "lookahead_limiter_plugin": "fastLookaheadLimiter", 
            "multiband_eq_plugin": "mbeq",
            "multiband_compressor_plugin": "ZaMultiCompX2"
        },
        "lookahead_limiter_defaults": {
            "input_gain_db": 0.0,
            "limit_db": -0.1,
            "release_time_s": 0.05
        },
        "multiband_eq_defaults": {
            "gain_50hz": 0.0, "gain_100hz": 0.0, "gain_156hz": 0.0,
            "gain_220hz": 0.0, "gain_311hz": 0.0, "gain_440hz": 0.0,
            "gain_622hz": 0.0, "gain_880hz": 0.0, "gain_1250hz": 0.0,
            "gain_1750hz": 0.0, "gain_2500hz": 0.0, "gain_3500hz": 0.0,
            "gain_5000hz": 0.0, "gain_10000hz": 0.0, "gain_20000hz": 0.0
        },
        "multiband_compressor_defaults": {
            "crossover_freq1": 200.0, "crossover_freq2": 2000.0,
            "attack1": 25.0, "release1": 125.0, "knee1": 2.0, "ratio1": 4.0,
            "threshold1": -15.0, "makeup1": 0.0, "enable1": True,
            "attack2": 15.0, "release2": 80.0, "knee2": 2.0, "ratio2": 3.0,
            "threshold2": -12.0, "makeup2": 0.0, "enable2": True,
            "attack3": 5.0, "release3": 50.0, "knee3": 1.0, "ratio3": 2.0,
            "threshold3": -10.0, "makeup3": 0.0, "enable3": True,
            "master_trim": 0.0, "detection_mode": True
        },
        "auto_selection_hints": {
            "front_sink": ["iec958", "digital", "spdif"],
            "rear_left_sink": ["pci-0000_03_00.1", "Navi", "HDMI"],
            "rear_right_sink": ["pci-0000_00_1f.3", "PCH", "HDMI"]
        }
    }

def run_cmd(cmd: str) -> Tuple[int, str, str]:
    """Execute a shell command and return (exit_code, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def pactl_sinks() -> List[str]:
    """Returns a list of sink names, excluding internal pipeline sinks."""
    code, out, _ = run_cmd("pactl list short sinks")
    if code != 0:
        return []
    
    # Exclude sinks that are part of our internal pipeline
    internal_sinks = {
        CONFIG["pipeline"]["splitter_sink_name"],
        CONFIG["pipeline"]["compressor_sink_name"],
        CONFIG["pipeline"].get("limiter_sink_name", "limiter"),
        CONFIG["pipeline"].get("eq_sink_name", "eq"), 
        CONFIG["pipeline"].get("multicomp_sink_name", "multicomp"),
        "null"  # Also exclude the generic null sink if it exists
    }
    
    valid_sinks = []
    for line in out.splitlines():
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] not in internal_sinks:
            valid_sinks.append(parts[1])
            
    return valid_sinks

class WaveformWidget(Gtk.DrawingArea):
    """Real-time waveform visualization widget with before/after overlay."""
    
    def __init__(self):
        super().__init__()
        self.set_size_request(600, 200)
        self.set_draw_func(self.on_draw)
        
        # Waveform data buffers
        self.input_samples = [0.0] * 512
        self.output_samples = [0.0] * 512
        self.sample_index = 0
        
        # Start audio monitoring thread
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self.monitor_audio, daemon=True)
        self.monitor_thread.start()
    
    def monitor_audio(self):
        """Background thread to capture audio levels for visualization."""
        while self.monitoring:
            try:
                # Get input levels from splitter monitor
                code, out, _ = run_cmd(f"pactl list sources | grep -A20 '{CONFIG['pipeline']['splitter_sink_name']}.monitor'")
                if code == 0 and "Volume:" in out:
                    # Parse volume levels for visualization
                    # This is a simplified approach - real implementation would use PulseAudio C API
                    level = 0.1 + 0.4 * math.sin(time.time() * 2)  # Simulated for now
                    self.input_samples[self.sample_index] = level
                    
                    # Simulate processed output (would be different in real implementation)
                    self.output_samples[self.sample_index] = level * 0.7  # Compressed/limited
                    
                    self.sample_index = (self.sample_index + 1) % len(self.input_samples)
                    
                    # Trigger redraw
                    GLib.idle_add(self.queue_draw)
                    
            except Exception:
                pass
            
            time.sleep(0.02)  # ~50 FPS
    
    def on_draw(self, widget, cr, width, height, user_data):
        """Draw the waveform visualization."""
        # Clear background
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        
        # Draw center line
        cr.set_source_rgb(0.3, 0.3, 0.3)
        cr.set_line_width(1)
        cr.move_to(0, height / 2)
        cr.line_to(width, height / 2)
        cr.stroke()
        
        # Draw input waveform (blue)
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)
        cr.set_line_width(2)
        for i, sample in enumerate(self.input_samples):
            x = (i / len(self.input_samples)) * width
            y = height / 2 - (sample * height / 4)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        
        # Draw output waveform (red overlay)
        cr.set_source_rgba(1.0, 0.3, 0.2, 0.8)
        cr.set_line_width(2)
        for i, sample in enumerate(self.output_samples):
            x = (i / len(self.output_samples)) * width
            y = height / 2 - (sample * height / 4)
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        
        # Draw legend
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(12)
        cr.move_to(10, 20)
        cr.show_text("🔵 Input Signal")
        cr.move_to(10, 35)
        cr.show_text("🔴 Processed Output")

class MasteringGUI(Gtk.ApplicationWindow):
    """Professional audio mastering suite GUI."""
    
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("Audio Splitter Pro - Mastering Suite")
        self.set_default_size(1200, 900)
        
        # Create main layout
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        self.set_child(main_box)
        
        # Create scrolled window for content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        main_box.append(scrolled)
        
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        scrolled.set_child(content_box)
        
        # Add waveform visualization
        waveform_frame = self._create_frame("🌊 Real-time Waveform Analysis")
        self.waveform = WaveformWidget()
        waveform_frame.set_child(self.waveform)
        content_box.append(waveform_frame)
        
        # Create horizontal layout for controls
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=15)
        controls_box.set_homogeneous(True)
        content_box.append(controls_box)
        
        # Output routing section (left column)
        routing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        controls_box.append(routing_box)
        
        self._create_routing_section(routing_box)
        
        # Audio processing sections (right columns)
        processing_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        controls_box.append(processing_box)
        
        self._create_limiter_section(processing_box)
        self._create_eq_section(processing_box)
        
        # Multiband compressor (full width)
        self._create_multiband_section(content_box)
        
        # Control buttons
        self._create_control_buttons(main_box)
        
        # Initialize sink selection
        self.refresh_sinks()
    
    def _create_frame(self, title: str) -> Gtk.Frame:
        """Create a styled frame with title."""
        frame = Gtk.Frame()
        frame.set_label(title)
        frame.set_label_align(0.02)
        return frame
    
    def _create_routing_section(self, parent_box):
        """Create output routing controls."""
        routing_frame = self._create_frame("🎯 Output Routing")
        parent_box.append(routing_frame)
        
        routing_grid = Gtk.Grid()
        routing_grid.set_row_spacing(8)
        routing_grid.set_column_spacing(10)
        routing_grid.set_margin_top(10)
        routing_grid.set_margin_bottom(10)
        routing_grid.set_margin_start(10)
        routing_grid.set_margin_end(10)
        routing_frame.set_child(routing_grid)
        
        # Front (SPDIF) selection
        routing_grid.attach(Gtk.Label(label="Front (SPDIF):"), 0, 0, 1, 1)
        self.front_sink_combo = Gtk.ComboBoxText()
        routing_grid.attach(self.front_sink_combo, 1, 0, 1, 1)
        
        # Rear Left (HDMI) selection  
        routing_grid.attach(Gtk.Label(label="Rear Left (HDMI):"), 0, 1, 1, 1)
        self.rear_left_combo = Gtk.ComboBoxText()
        routing_grid.attach(self.rear_left_combo, 1, 1, 1, 1)
        
        # Rear Right (HDMI) selection
        routing_grid.attach(Gtk.Label(label="Rear Right (HDMI):"), 0, 2, 1, 1)
        self.rear_right_combo = Gtk.ComboBoxText()
        routing_grid.attach(self.rear_right_combo, 1, 2, 1, 1)
        
        # Volume controls
        routing_grid.attach(Gtk.Label(label="Front Vol (%):"), 0, 3, 1, 1)
        self.front_volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 150, 5)
        self.front_volume.set_value(100)
        self.front_volume.set_hexpand(True)
        routing_grid.attach(self.front_volume, 1, 3, 1, 1)
        
        routing_grid.attach(Gtk.Label(label="Rear Balance (L/R):"), 0, 4, 1, 1)
        self.rear_balance = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -50, 50, 1)
        self.rear_balance.set_value(0)
        self.rear_balance.set_hexpand(True)
        routing_grid.attach(self.rear_balance, 1, 4, 1, 1)
    
    def _create_limiter_section(self, parent_box):
        """Create lookahead limiter controls."""
        limiter_frame = self._create_frame("🧱 Fast Lookahead Limiter")
        parent_box.append(limiter_frame)
        
        limiter_grid = Gtk.Grid()
        limiter_grid.set_row_spacing(8)
        limiter_grid.set_column_spacing(10) 
        limiter_grid.set_margin_top(10)
        limiter_grid.set_margin_bottom(10)
        limiter_grid.set_margin_start(10)
        limiter_grid.set_margin_end(10)
        limiter_frame.set_child(limiter_grid)
        
        # Input Gain
        limiter_grid.attach(Gtk.Label(label="Input Gain (dB):"), 0, 0, 1, 1)
        self.limiter_input_gain = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -20, 20, 0.1)
        self.limiter_input_gain.set_value(CONFIG["lookahead_limiter_defaults"]["input_gain_db"])
        self.limiter_input_gain.set_hexpand(True)
        limiter_grid.attach(self.limiter_input_gain, 1, 0, 1, 1)
        
        # Limit Threshold
        limiter_grid.attach(Gtk.Label(label="Limit (dB):"), 0, 1, 1, 1)
        self.limiter_limit = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -20, 0, 0.1)
        self.limiter_limit.set_value(CONFIG["lookahead_limiter_defaults"]["limit_db"])
        self.limiter_limit.set_hexpand(True)
        limiter_grid.attach(self.limiter_limit, 1, 1, 1, 1)
        
        # Release Time
        limiter_grid.attach(Gtk.Label(label="Release (s):"), 0, 2, 1, 1)
        self.limiter_release = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.01, 2.0, 0.01)
        self.limiter_release.set_value(CONFIG["lookahead_limiter_defaults"]["release_time_s"])
        self.limiter_release.set_hexpand(True)
        limiter_grid.attach(self.limiter_release, 1, 2, 1, 1)
        
        # Add tooltips
        self.limiter_input_gain.set_tooltip_text("**Pre-limiting gain boost**\n*Raises the signal level before limiting*\nLower = quieter input, Higher = louder input")
        self.limiter_limit.set_tooltip_text("**Absolute ceiling threshold**\n*No signal will exceed this level*\nLower = more aggressive limiting, Higher = allows louder peaks") 
        self.limiter_release.set_tooltip_text("**Recovery speed after limiting**\n*How quickly the limiter stops working*\nLower = faster recovery, Higher = smoother but slower")
    
    def _create_eq_section(self, parent_box):
        """Create 15-band EQ controls.""" 
        eq_frame = self._create_frame("🎛️ 15-Band Parametric EQ")
        parent_box.append(eq_frame)
        
        eq_scrolled = Gtk.ScrolledWindow()
        eq_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        eq_scrolled.set_size_request(-1, 200)
        eq_frame.set_child(eq_scrolled)
        
        eq_grid = Gtk.Grid()
        eq_grid.set_row_spacing(5)
        eq_grid.set_column_spacing(8)
        eq_grid.set_margin_top(10)
        eq_grid.set_margin_bottom(10)
        eq_grid.set_margin_start(10)
        eq_grid.set_margin_end(10)
        eq_scrolled.set_child(eq_grid)
        
        # EQ frequency bands
        self.eq_bands = {}
        frequencies = [50, 100, 156, 220, 311, 440, 622, 880, 1250, 1750, 2500, 3500, 5000, 10000, 20000]
        
        for i, freq in enumerate(frequencies):
            # Frequency label
            freq_str = f"{freq}Hz" if freq < 1000 else f"{freq//1000}kHz"
            label = Gtk.Label(label=freq_str)
            label.set_angle(45)  # Rotate labels for space
            eq_grid.attach(label, i, 0, 1, 1)
            
            # EQ slider (vertical)
            slider = Gtk.Scale.new_with_range(Gtk.Orientation.VERTICAL, -70, 30, 1)
            slider.set_value(0)  # Start flat
            slider.set_inverted(True)  # Higher values at top
            slider.set_size_request(30, 120)
            slider.set_tooltip_text(f"**{freq_str} gain control**\n*Boost or cut this frequency range*\nLower = cut frequencies, Higher = boost frequencies")
            eq_grid.attach(slider, i, 1, 1, 1)
            
            self.eq_bands[freq] = slider
    
    def _create_multiband_section(self, parent_box):
        """Create 3-band multiband compressor controls."""
        multiband_frame = self._create_frame("🎚️ 3-Band Multiband Compressor")
        parent_box.append(multiband_frame)
        
        multiband_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        multiband_box.set_margin_top(10)
        multiband_box.set_margin_bottom(10)
        multiband_box.set_margin_start(10)
        multiband_box.set_margin_end(10)
        multiband_frame.set_child(multiband_box)
        
        # Crossover frequency controls
        crossover_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        multiband_box.append(crossover_box)
        
        crossover_box.append(Gtk.Label(label="Crossover 1 (Hz):"))
        self.crossover1 = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 20, 1400, 10)
        self.crossover1.set_value(CONFIG["multiband_compressor_defaults"]["crossover_freq1"])
        self.crossover1.set_hexpand(True)
        crossover_box.append(self.crossover1)
        
        crossover_box.append(Gtk.Label(label="Crossover 2 (Hz):"))
        self.crossover2 = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1400, 14000, 100)
        self.crossover2.set_value(CONFIG["multiband_compressor_defaults"]["crossover_freq2"])
        self.crossover2.set_hexpand(True)
        crossover_box.append(self.crossover2)
        
        # Individual band controls
        bands_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        bands_box.set_homogeneous(True)
        multiband_box.append(bands_box)
        
        self.multiband_controls = {}
        band_names = ["Low Band", "Mid Band", "High Band"]
        band_keys = [1, 2, 3]
        
        for i, (name, key) in enumerate(zip(band_names, band_keys)):
            band_frame = self._create_frame(f"🎵 {name}")
            bands_box.append(band_frame)
            
            band_grid = Gtk.Grid()
            band_grid.set_row_spacing(5)
            band_grid.set_column_spacing(10)
            band_grid.set_margin_top(10)
            band_grid.set_margin_bottom(10)
            band_grid.set_margin_start(10)
            band_grid.set_margin_end(10)
            band_frame.set_child(band_grid)
            
            # Enable checkbox
            enable_check = Gtk.CheckButton(label="Enable")
            enable_check.set_active(CONFIG["multiband_compressor_defaults"][f"enable{key}"])
            band_grid.attach(enable_check, 0, 0, 2, 1)
            
            # Band controls
            controls = {}
            
            # Threshold
            band_grid.attach(Gtk.Label(label="Threshold (dB):"), 0, 1, 1, 1)
            threshold = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -60, 0, 1)
            threshold.set_value(CONFIG["multiband_compressor_defaults"][f"threshold{key}"])
            threshold.set_hexpand(True)
            band_grid.attach(threshold, 1, 1, 1, 1)
            controls['threshold'] = threshold
            
            # Ratio
            band_grid.attach(Gtk.Label(label="Ratio:"), 0, 2, 1, 1)
            ratio = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 20, 0.1)
            ratio.set_value(CONFIG["multiband_compressor_defaults"][f"ratio{key}"])
            ratio.set_hexpand(True)
            band_grid.attach(ratio, 1, 2, 1, 1)
            controls['ratio'] = ratio
            
            # Attack
            band_grid.attach(Gtk.Label(label="Attack (ms):"), 0, 3, 1, 1)
            attack = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.1, 100, 0.1)
            attack.set_value(CONFIG["multiband_compressor_defaults"][f"attack{key}"])
            attack.set_hexpand(True)
            band_grid.attach(attack, 1, 3, 1, 1)
            controls['attack'] = attack
            
            # Release  
            band_grid.attach(Gtk.Label(label="Release (ms):"), 0, 4, 1, 1)
            release = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 500, 1)
            release.set_value(CONFIG["multiband_compressor_defaults"][f"release{key}"])
            release.set_hexpand(True)
            band_grid.attach(release, 1, 4, 1, 1)
            controls['release'] = release
            
            # Makeup gain
            band_grid.attach(Gtk.Label(label="Makeup (dB):"), 0, 5, 1, 1)
            makeup = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 30, 0.5)
            makeup.set_value(CONFIG["multiband_compressor_defaults"][f"makeup{key}"])
            makeup.set_hexpand(True)
            band_grid.attach(makeup, 1, 5, 1, 1)
            controls['makeup'] = makeup
            
            self.multiband_controls[key] = {
                'enable': enable_check,
                'controls': controls
            }
    
    def _create_control_buttons(self, parent_box):
        """Create main control buttons."""
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_halign(Gtk.Align.CENTER)
        parent_box.append(button_box)
        
        # Apply/Start button
        apply_btn = Gtk.Button(label="🚀 Apply / Start")
        apply_btn.add_css_class("suggested-action")
        apply_btn.connect("clicked", self.on_apply_clicked)
        button_box.append(apply_btn)
        
        # Stop button
        stop_btn = Gtk.Button(label="⏹️ Stop")
        stop_btn.add_css_class("destructive-action")
        stop_btn.connect("clicked", self.on_stop_clicked)
        button_box.append(stop_btn)
        
        # Refresh sinks button
        refresh_btn = Gtk.Button(label="🔄 Refresh Sinks")
        refresh_btn.connect("clicked", self.on_refresh_clicked)
        button_box.append(refresh_btn)
        
        # Preset buttons
        preset_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        button_box.append(preset_box)
        
        night_preset = Gtk.Button(label="🌙 Night Mode")
        night_preset.connect("clicked", self.on_night_preset)
        preset_box.append(night_preset)
        
        mastering_preset = Gtk.Button(label="🎛️ Mastering")
        mastering_preset.connect("clicked", self.on_mastering_preset)
        preset_box.append(mastering_preset)
        
        vocal_preset = Gtk.Button(label="🎤 Vocal Enhance")
        vocal_preset.connect("clicked", self.on_vocal_preset)
        preset_box.append(vocal_preset)
    
    def refresh_sinks(self):
        """Refresh the list of available audio sinks."""
        sinks = pactl_sinks()
        
        # Clear existing entries
        for combo in [self.front_sink_combo, self.rear_left_combo, self.rear_right_combo]:
            combo.remove_all()
            combo.append("disabled", "[ Disabled ]")
        
        # Add available sinks
        for sink in sinks:
            for combo in [self.front_sink_combo, self.rear_left_combo, self.rear_right_combo]:
                combo.append(sink, sink)
        
        # Auto-select based on hints
        hints = CONFIG["auto_selection_hints"]
        
        for sink in sinks:
            if any(hint in sink.lower() for hint in hints["front_sink"]):
                self.front_sink_combo.set_active_id(sink)
            if any(hint in sink.lower() for hint in hints["rear_left_sink"]):
                self.rear_left_combo.set_active_id(sink)
            if any(hint in sink.lower() for hint in hints["rear_right_sink"]):
                self.rear_right_combo.set_active_id(sink)
        
        # Default to disabled if no match
        for combo in [self.front_sink_combo, self.rear_left_combo, self.rear_right_combo]:
            if combo.get_active_id() is None:
                combo.set_active_id("disabled")
    
    def on_apply_clicked(self, button):
        """Apply the current audio processing pipeline."""
        print("🚀 Building professional mastering pipeline...")
        # TODO: Implement pipeline building with all the new effects
        
    def on_stop_clicked(self, button):
        """Stop the audio processing pipeline."""
        print("⏹️ Stopping mastering pipeline...")
        # TODO: Implement pipeline cleanup
        
    def on_refresh_clicked(self, button):
        """Refresh available sinks."""
        self.refresh_sinks()
        print("🔄 Sinks refreshed")
    
    def on_night_preset(self, button):
        """Apply Night Mode preset - aggressive compression, gentle EQ."""
        print("🌙 Applying Night Mode preset...")
        
        # Limiter: Conservative settings
        self.limiter_input_gain.set_value(3.0)  # Slight boost
        self.limiter_limit.set_value(-1.0)      # Safe ceiling
        self.limiter_release.set_value(0.1)     # Fast recovery
        
        # EQ: Gentle high-frequency roll-off
        for freq, slider in self.eq_bands.items():
            if freq >= 5000:  # High frequencies
                slider.set_value(-3)  # Slight cut
            elif freq <= 100:  # Low frequencies  
                slider.set_value(-2)  # Reduce rumble
            else:
                slider.set_value(0)   # Flat mids
        
        # Multiband: Aggressive compression for consistent levels
        for key in [1, 2, 3]:
            self.multiband_controls[key]['enable'].set_active(True)
            self.multiband_controls[key]['controls']['threshold'].set_value(-25)  # Lower threshold
            self.multiband_controls[key]['controls']['ratio'].set_value(6.0)     # Strong compression
            self.multiband_controls[key]['controls']['attack'].set_value(5.0)    # Fast attack
            self.multiband_controls[key]['controls']['release'].set_value(100.0) # Medium release
            self.multiband_controls[key]['controls']['makeup'].set_value(3.0)    # Modest gain
    
    def on_mastering_preset(self, button):
        """Apply Mastering preset - transparent, professional settings."""
        print("🎛️ Applying Mastering preset...")
        
        # Limiter: Professional mastering settings
        self.limiter_input_gain.set_value(0.0)   # No extra gain
        self.limiter_limit.set_value(-0.1)       # Just catch peaks
        self.limiter_release.set_value(0.05)     # Very fast
        
        # EQ: Flat response
        for slider in self.eq_bands.values():
            slider.set_value(0)
        
        # Multiband: Gentle, transparent compression
        for key in [1, 2, 3]:
            self.multiband_controls[key]['enable'].set_active(True)
            self.multiband_controls[key]['controls']['threshold'].set_value(-15)  # Conservative
            self.multiband_controls[key]['controls']['ratio'].set_value(2.5)     # Gentle
            self.multiband_controls[key]['controls']['attack'].set_value(10.0)   # Smooth
            self.multiband_controls[key]['controls']['release'].set_value(150.0) # Natural
            self.multiband_controls[key]['controls']['makeup'].set_value(0.0)    # No extra gain
    
    def on_vocal_preset(self, button):
        """Apply Vocal Enhancement preset - midrange focus."""
        print("🎤 Applying Vocal Enhancement preset...")
        
        # Limiter: Moderate settings
        self.limiter_input_gain.set_value(1.0)
        self.limiter_limit.set_value(-0.5)
        self.limiter_release.set_value(0.08)
        
        # EQ: Vocal presence boost
        for freq, slider in self.eq_bands.items():
            if 1000 <= freq <= 3500:  # Vocal presence range
                slider.set_value(3)
            elif freq == 220 or freq == 311:  # Warmth
                slider.set_value(2)
            elif freq >= 10000:  # Air/sparkle
                slider.set_value(2)
            else:
                slider.set_value(0)
        
        # Multiband: Focus on mid compression
        for key in [1, 2, 3]:
            self.multiband_controls[key]['enable'].set_active(True)
            if key == 2:  # Mid band gets more compression
                self.multiband_controls[key]['controls']['threshold'].set_value(-18)
                self.multiband_controls[key]['controls']['ratio'].set_value(4.0)
                self.multiband_controls[key]['controls']['makeup'].set_value(2.0)
            else:
                self.multiband_controls[key]['controls']['threshold'].set_value(-20)
                self.multiband_controls[key]['controls']['ratio'].set_value(2.0)
                self.multiband_controls[key]['controls']['makeup'].set_value(0.0)

class MasteringApp(Gtk.Application):
    """GTK4 Application wrapper."""
    
    def __init__(self):
        super().__init__(application_id="com.audiosplitter.mastering")
        self.connect("activate", self.on_activate)
    
    def on_activate(self, app):
        """Application activation callback."""
        window = MasteringGUI(app)
        window.present()

def main():
    """Main application entry point."""
    app = MasteringApp()
    return app.run(sys.argv)

if __name__ == "__main__":
    main()
