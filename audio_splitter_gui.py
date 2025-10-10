#!/usr/bin/env python3
import gi
import subprocess
import shlex
from typing import List, Tuple, Optional
import os

# Use the built-in tomllib in Python 3.11+, fallback to tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

APP_ID = "com.brandon.AudioSplitterGUI"

# --- Configuration Loading ---
def load_config():
    """Loads settings from config.toml, with hardcoded fallbacks."""
    defaults = {
        "pipeline": {
            "left_source_name": "splitter_left", "right_source_name": "splitter_right",
            "splitter_sink_name": "splitter", "compressor_sink_name": "compressor",
        },
        "ladspa_plugins": {"compressor_plugin": "sc4_1882"},
        "compressor_defaults": {
            "threshold_db": -20.0, "ratio": 4.0, "knee_db": 6.0,
            "attack_ms": 5.0, "release_ms": 100.0, "makeup_gain_db": 0.0,
        },
        "auto_selection_hints": {
            "front_sink": ["iec958", "digital", "spdif"],
            "rear_left_sink": ["pci-0000_03_00.1"],
            "rear_right_sink": ["pci-0000_00_1f.3"],
        }
    }
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'config.toml')
        with open(config_path, 'rb') as f:
            user_config = tomllib.load(f)
        # Deep merge user config into defaults
        for section, values in defaults.items():
            if section in user_config:
                values.update(user_config[section])
    except (IOError, tomllib.TOMLDecodeError):
        pass # Fallback to defaults if file is missing or invalid
    return defaults

CONFIG = load_config()

# Pipeline component names from config
LEFT_SRC = CONFIG["pipeline"]["left_source_name"]
RIGHT_SRC = CONFIG["pipeline"]["right_source_name"]
SPLITTER_SINK = CONFIG["pipeline"]["splitter_sink_name"]
COMPRESSOR_SINK = CONFIG["pipeline"]["compressor_sink_name"]
SC4_PLUGIN = CONFIG["ladspa_plugins"]["compressor_plugin"]
DISABLED_SINK_TEXT = "[ Disabled ]"


def run_cmd(cmd: str) -> Tuple[int, str, str]:
    proc = subprocess.run(shlex.split(cmd), capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def pactl_sinks() -> List[str]:
    """Returns a list of sink names, excluding internal pipeline sinks."""
    code, out, _ = run_cmd("pactl list short sinks")
    if code != 0:
        return []
    
    # Exclude sinks that are part of our internal pipeline
    internal_sinks = {
        CONFIG["pipeline"]["splitter_sink_name"],
        CONFIG["pipeline"]["compressor_sink_name"],
        "null" # Also exclude the generic null sink if it exists
    }
    
    valid_sinks = []
    for line in out.splitlines():
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1] not in internal_sinks:
            valid_sinks.append(parts[1])
            
    return valid_sinks


def find_module_ids(patterns: List[str]) -> List[str]:
    code, text, _ = run_cmd("pactl list modules")
    if code != 0: return []
    blocks, ids = text.split("\n\n"), []
    for b in blocks:
        if all(p in b for p in patterns):
            if mid_line := next((line for line in b.splitlines() if line.strip().startswith("Module #")), None):
                ids.append(mid_line.strip().split("#", 1)[1])
    return ids


def unload_modules_by_patterns(patterns: List[str]) -> None:
    for mid in find_module_ids(patterns):
        run_cmd(f"pactl unload-module {mid}")


def stop_pipeline() -> None:
    """AGGRESSIVELY clean up ALL pipeline modules to ensure idempotent behavior"""
    # Clean up in reverse order of creation (loopbacks first)
    unload_modules_by_patterns(["module-loopback", "source=splitter_left"])
    unload_modules_by_patterns(["module-loopback", "source=splitter_right"])
    
    # Clean up remap sources
    unload_modules_by_patterns(["module-remap-source", "source_name=splitter_left"])
    unload_modules_by_patterns(["module-remap-source", "source_name=splitter_right"])
    
    # Clean up LADSPA sinks (limiter and compressor)
    unload_modules_by_patterns(["module-ladspa-sink", "sink_name=limiter"])
    unload_modules_by_patterns(["module-ladspa-sink", "sink_name=compressor"])
    
    # Clean up ALL splitter null sinks (including numbered duplicates)
    unload_modules_by_patterns(["module-null-sink", "sink_name=splitter"])
    
    print("🧹 Cleaned up existing pipeline modules")


def apply_pipeline(front_sink: str, rear_l_sink: str, rear_r_sink: str, comp_cfg: dict) -> None:
    # AGGRESSIVE cleanup to ensure idempotent behavior
    stop_pipeline()
    
    # Check existing sinks (including internal ones for this check)
    code, out, _ = run_cmd("pactl list short sinks")
    all_existing = [line.split()[1] for line in out.splitlines() if line] if code == 0 else []
    
    # Use existing splitter if available, otherwise create new one
    if SPLITTER_SINK in all_existing:
        splitter = SPLITTER_SINK
        print(f"✅ Reusing existing splitter: {splitter}")
    elif "null" in all_existing:
        splitter = "null"
        print(f"✅ Reusing null sink as splitter")
    else:
        run_cmd(f"pactl load-module module-null-sink sink_name={SPLITTER_SINK} sink_properties=device.description='🎛️ ASP Input'")
        splitter = SPLITTER_SINK
        print(f"✅ Created new splitter: {splitter}")

    # Build effects chain: Limiter (optional) -> Compressor
    master_sink = splitter
    
    # Add Fast Lookahead Limiter if configured (non-zero settings)
    if comp_cfg.get('limiter_input_gain', 0) != 0 or comp_cfg.get('limiter_limit', 0) != 0:
        limiter_controls = f"{comp_cfg['limiter_input_gain']},{comp_cfg['limiter_limit']},{comp_cfg['limiter_release']}"
        run_cmd(f"pactl load-module module-ladspa-sink sink_name=limiter sink_master={master_sink} plugin=fast_lookahead_limiter_1913 label=fastLookaheadLimiter control={limiter_controls} sink_properties=device.description='🧱 ASP Brick-Wall Limiter'")
        master_sink = "limiter"
        print(f"✅ Added limiter: input={comp_cfg['limiter_input_gain']}dB, limit={comp_cfg['limiter_limit']}dB")
    
    # Add SC4 Compressor
    controls = (f"1,{comp_cfg['attack_ms']},{comp_cfg['release_ms']},"
                f"{comp_cfg['threshold_db']},{comp_cfg['ratio']},"
                f"{comp_cfg['knee_db']},{comp_cfg['makeup_gain_db']}")
    run_cmd(f"pactl load-module module-ladspa-sink sink_name={COMPRESSOR_SINK} sink_master={master_sink} plugin={SC4_PLUGIN} label=sc4 control={controls} sink_properties=device.description='🎛️ ASP SC4 Compressor'")
    final_sink = COMPRESSOR_SINK
    run_cmd(f"pactl set-default-sink {final_sink}")

    run_cmd(f"pactl load-module module-remap-source source_name={LEFT_SRC} master={splitter}.monitor channels=1 channel_map=mono master_channel_map=front-left")
    run_cmd(f"pactl load-module module-remap-source source_name={RIGHT_SRC} master={splitter}.monitor channels=1 channel_map=mono master_channel_map=front-right")
    
    if front_sink:
        run_cmd(f"pactl load-module module-loopback source={LEFT_SRC} sink={front_sink} latency_msec=50")
        run_cmd(f"pactl load-module module-loopback source={RIGHT_SRC} sink={front_sink} latency_msec=50")
    if rear_l_sink: run_cmd(f"pactl load-module module-loopback source={LEFT_SRC} sink={rear_l_sink} latency_msec=50")
    if rear_r_sink: run_cmd(f"pactl load-module module-loopback source={RIGHT_SRC} sink={rear_r_sink} latency_msec=50")


class WaveformWidget(Gtk.DrawingArea):
    """Real-time waveform visualization with before/after overlay"""
    
    def __init__(self):
        super().__init__()
        self.set_size_request(380, 150)  # More compact for screen fit
        self.set_draw_func(self.on_draw, None)
        
        # Waveform data buffers (circular buffers)
        self.buffer_size = 512
        self.input_samples = [0.0] * self.buffer_size   # Before processing (blue)
        self.output_samples = [0.0] * self.buffer_size  # After processing (red)
        self.sample_index = 0
        
        # Colors for before/after
        self.input_color = (0.2, 0.6, 1.0, 0.8)   # Blue - input
        self.output_color = (1.0, 0.4, 0.2, 0.8)  # Red - output
        
        # Start monitoring
        self.monitoring = True
        GLib.timeout_add(50, self.update_waveform)  # 20 FPS
    
    def update_waveform(self):
        """Monitor ACTUAL INPUT vs COMPRESSED OUTPUT from real pipeline"""
        if not self.monitoring:
            return False
            
        input_level = 0.0
        output_level = 0.0
        
        try:
            # SOURCE: Monitor the INPUT (before compression) - splitter.monitor
            code1, input_data, _ = run_cmd("timeout 0.05s parec --device=splitter.monitor --format=s16le --rate=8000 --channels=1 2>/dev/null | od -t d2 | head -1 | awk '{print $2}'")
            if code1 == 0 and input_data.strip():
                try:
                    input_level = int(input_data.strip()) / 32768.0
                except:
                    input_level = 0.0
            
            # OUTPUT: Monitor the COMPRESSED signal - compressor.monitor 
            code2, output_data, _ = run_cmd("timeout 0.05s parec --device=compressor.monitor --format=s16le --rate=8000 --channels=1 2>/dev/null | od -t d2 | head -1 | awk '{print $2}'")
            if code2 == 0 and output_data.strip():
                try:
                    output_level = int(output_data.strip()) / 32768.0
                except:
                    output_level = 0.0
                    
        except Exception:
            input_level = 0.0
            output_level = 0.0
        
        # Store real data
        self.input_samples[self.sample_index] = input_level
        self.output_samples[self.sample_index] = output_level
        self.sample_index = (self.sample_index + 1) % self.buffer_size
        
        self.queue_draw()
        return True
    
    def on_draw(self, widget, cr, width, height, user_data):
        """Draw the waveform visualization"""
        # Clear background
        cr.set_source_rgb(0.1, 0.1, 0.1)  # Dark background
        cr.paint()
        
        # Draw grid lines
        cr.set_source_rgba(0.3, 0.3, 0.3, 0.5)
        cr.set_line_width(1)
        
        # Horizontal center line
        cr.move_to(0, height / 2)
        cr.line_to(width, height / 2)
        cr.stroke()
        
        # Quarter lines
        cr.move_to(0, height / 4)
        cr.line_to(width, height / 4)
        cr.move_to(0, 3 * height / 4)
        cr.line_to(width, 3 * height / 4)
        cr.stroke()
        
        # Draw waveforms
        x_scale = width / self.buffer_size
        y_scale = height / 2
        
        # Draw input waveform (blue)
        cr.set_source_rgba(*self.input_color)
        cr.set_line_width(2)
        cr.move_to(0, height / 2)
        
        for i in range(self.buffer_size):
            idx = (self.sample_index + i) % self.buffer_size
            x = i * x_scale
            y = height / 2 - self.input_samples[idx] * y_scale * 0.8
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        
        # Draw output waveform (red)
        cr.set_source_rgba(*self.output_color)
        cr.set_line_width(2)
        cr.move_to(0, height / 2)
        
        for i in range(self.buffer_size):
            idx = (self.sample_index + i) % self.buffer_size
            x = i * x_scale
            y = height / 2 - self.output_samples[idx] * y_scale * 0.8
            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()
        
        # Draw legend
        cr.set_source_rgba(*self.input_color)
        cr.rectangle(10, 10, 20, 10)
        cr.fill()
        
        cr.set_source_rgba(*self.output_color)
        cr.rectangle(10, 25, 20, 10)
        cr.fill()
        
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(35, 19)
        cr.show_text("Input")
        cr.move_to(35, 34)
        cr.show_text("Output")

class AudioSplitterWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Audio Splitter Pro")
        self.set_default_size(780, 400)  # Even more compact for screen fit

        self.comp_adjs = {k: Gtk.Adjustment(value=v, lower=l, upper=u, step_increment=s, page_increment=p) for k, (v,l,u,s,p) in {
            "threshold_db": (CONFIG["compressor_defaults"]["threshold_db"], -60, 0, 1, 5), 
            "ratio": (CONFIG["compressor_defaults"]["ratio"], 1, 20, 0.5, 2),
            "knee_db": (CONFIG["compressor_defaults"]["knee_db"], 0, 20, 1, 5), 
            "attack_ms": (CONFIG["compressor_defaults"]["attack_ms"], 0.1, 200, 0.1, 10),
            "release_ms": (CONFIG["compressor_defaults"]["release_ms"], 1, 1000, 1, 50), 
            "makeup_gain_db": (CONFIG["compressor_defaults"]["makeup_gain_db"], 0, 40, 1, 5),
        }.items()}
        self.front_vol_adj = Gtk.Adjustment(value=100, lower=0, upper=150, step_increment=1, page_increment=10)
        self.rear_balance_adj = Gtk.Adjustment(value=0, lower=-100, upper=100, step_increment=5, page_increment=20)
        
        # Create main horizontal layout for compact design
        main_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10, margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        self.set_child(main_hbox)
        
        # Left column - controls
        left_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        left_column.set_size_request(380, -1)
        main_hbox.append(left_column)
        
        # Right column - waveform and status  
        right_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_hbox.append(right_column)
        
        # Status bar at the bottom
        self.status_label = Gtk.Label(label="🎛️ Audio Splitter Pro - Ready")
        self.status_label.set_xalign(0)  # Left align
        self.status_label.set_wrap(True)
        self.status_label.set_selectable(True)  # Allow copying error text
        status_frame = Gtk.Frame(label="Status")
        status_frame.set_child(self.status_label)
        status_frame.set_margin_top(10)

        # Sink selection
        self.sinks_store = Gtk.StringList()
        self.front_combo = Gtk.DropDown(model=self.sinks_store)
        self.rear_l_combo = Gtk.DropDown(model=self.sinks_store)
        self.rear_r_combo = Gtk.DropDown(model=self.sinks_store)
        sink_frame = self._create_frame("Output Sinks", [
            ("Front (SPDIF)", self.front_combo), ("Rear Left (HDMI)", self.rear_l_combo), ("Rear Right (HDMI)", self.rear_r_combo)
        ])
        left_column.append(sink_frame)

        # Volume controls
        self.front_vol_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.front_vol_adj, draw_value=True)
        self.rear_balance_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.rear_balance_adj, draw_value=True)
        vol_frame = self._create_frame("Output Volumes", [
            ("Front Vol (%)", self.front_vol_scale),
            ("Rear Balance (L/R)", self.rear_balance_scale)
        ])
        left_column.append(vol_frame)

        # Fast Lookahead Limiter controls
        self.limiter_input_gain = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -20, 20, 0.1)
        self.limiter_input_gain.set_value(0.0)
        self.limiter_input_gain.set_tooltip_text("**Pre-limiting gain boost**\n*Raises signal before limiting*\nLower = quieter, Higher = louder")
        
        self.limiter_limit = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -20, 0, 0.1)
        self.limiter_limit.set_value(-0.1)
        self.limiter_limit.set_tooltip_text("**Absolute ceiling threshold**\n*No signal exceeds this level*\nLower = more limiting, Higher = allows peaks")
        
        self.limiter_release = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.01, 2.0, 0.01)
        self.limiter_release.set_value(0.05)
        self.limiter_release.set_tooltip_text("**Recovery speed after limiting**\n*How fast limiter stops working*\nLower = faster, Higher = smoother")
        
        limiter_frame = self._create_frame("🧱 Fast Lookahead Limiter", [
            ("Input Gain (dB)", self.limiter_input_gain),
            ("Limit (dB)", self.limiter_limit),
            ("Release (s)", self.limiter_release)
        ])
        left_column.append(limiter_frame)

        # Compressor controls
        comp_frame = self._create_frame(f"Compressor ({SC4_PLUGIN})", [])
        left_column.append(comp_frame)
        comp_grid = comp_frame.get_child()

        comp_controls_with_tooltips = [
            ("Threshold (dB)", self.comp_adjs["threshold_db"], 1, 
             """<b>Threshold (dB)</b>
The level at which gain reduction begins.

<i>When the input signal exceeds this level, the compressor starts working. Signals below the threshold are unaffected. This is the primary control for determining how much of your signal gets compressed.
Lower values start turning the sound down sooner; higher values only act on the very loudest parts.</i>"""),
            ("Ratio (1:n)", self.comp_adjs["ratio"], 1,
             """<b>Ratio (n:1)</b>
The amount of gain reduction applied to signals above the threshold.

<i>A 4:1 ratio means for every 4 dB the input goes over the threshold, the output only increases by 1 dB. Higher ratios result in more aggressive compression. An infinite ratio makes the compressor a limiter.
Lower values turn the volume down gently; higher values squash the volume down hard.</i>"""),
            ("Knee (dB)", self.comp_adjs["knee_db"], 1,
             """<b>Knee (dB)</b>
Controls the transition from uncompressed to compressed state.

<i>A 'hard knee' (0 dB) is an abrupt switch. A 'soft knee' creates a smoother, more gradual transition around the threshold, which can sound more natural.
Lower values are like a sudden switch; higher values are like a slow, gentle fade-in.</i>"""),
            ("Attack (ms)", self.comp_adjs["attack_ms"], 1,
             """<b>Attack (ms)</b>
How quickly the compressor reduces gain once the threshold is exceeded.

<i>Measured in milliseconds. Fast attacks clamp down on transients immediately, providing tight peak control. Slower attacks let initial transients pass through, preserving punch and impact.
Lower values react instantly to loud sounds; higher values let the first 'hit' of a sound pass through.</i>"""),
            ("Release (ms)", self.comp_adjs["release_ms"], 0,
             """<b>Release (ms)</b>
How quickly the compressor stops reducing gain after the signal falls below the threshold.

<i>Measured in milliseconds. Fast releases can sometimes cause audible 'pumping', while slow releases provide smoother, less noticeable compression.
Lower values let go of the sound quickly; higher values hold on to it for longer.</i>"""),
            ("Makeup Gain (dB)", self.comp_adjs["makeup_gain_db"], 1,
             """<b>Makeup Gain (dB)</b>
A final volume boost applied to the entire signal after compression.

<i>This is the crucial step that "raises the valleys." By reducing peaks, the other controls create headroom. Makeup Gain then raises the entire signal—peaks and valleys alike—to fill that headroom, increasing perceived loudness.
Lower values make the final sound quieter; higher values make it much louder.</i>"""),
        ]

        for i, (label_text, adj, digits, tooltip) in enumerate(comp_controls_with_tooltips):
            label_widget = Gtk.Label(label=label_text, xalign=0)
            scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj, hexpand=True, draw_value=True, digits=digits)
            label_widget.set_tooltip_markup(tooltip)
            scale.set_tooltip_markup(tooltip)
            comp_grid.attach(label_widget, 0, i, 1, 1)
            comp_grid.attach(scale, 1, i, 1, 1)

        # Actions
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8, halign=Gtk.Align.END)
        left_column.append(btn_box)
        for label, callback in [("Apply / Start", self.on_apply), ("Stop", self.on_stop), ("Refresh Sinks", self.on_refresh)]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", callback)
            btn_box.append(btn)
        
        # Waveform visualization widget (right column)
        self.waveform_widget = WaveformWidget()
        waveform_frame = Gtk.Frame(label="🌊 Real-time Waveform Analysis")
        waveform_frame.set_child(self.waveform_widget)
        right_column.append(waveform_frame)
        
        # Add status bar at the bottom (right column)
        right_column.append(status_frame)

        self.front_vol_adj.connect("value-changed", self.on_front_volume_changed)
        self.rear_balance_adj.connect("value-changed", self.on_rear_balance_changed)
        
        self.front_combo.connect("notify::selected-item", self.on_sink_selection_changed)
        self.rear_l_combo.connect("notify::selected-item", self.on_sink_selection_changed)
        self.rear_r_combo.connect("notify::selected-item", self.on_sink_selection_changed)
        
        self.on_refresh()
    
    def update_status(self, message: str) -> None:
        """Update the status bar with current operation info"""
        GLib.idle_add(lambda: self.status_label.set_text(message))

    def _create_frame(self, title: str, widgets: List[Tuple[str, Gtk.Widget]]) -> Gtk.Frame:
        frame = Gtk.Frame(label=title)
        grid = Gtk.Grid(column_spacing=12, row_spacing=8, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        frame.set_child(grid)
        for i, (label, widget) in enumerate(widgets):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, i, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, i, 1, 1)
        return frame

    def on_refresh(self, *args):
        self.update_status("🔄 Refreshing available sinks...")
        selections = self.current_selection()
        names = [DISABLED_SINK_TEXT] + pactl_sinks()
        self.sinks_store.splice(0, self.sinks_store.get_n_items(), names)
        self.update_status(f"✅ Found {len(names)-1} available sinks")
        
        def select(combo: Gtk.DropDown, saved: str, hints: List[str]):
            if saved in names: 
                combo.set_selected(names.index(saved))
                return
            
            for i, n in enumerate(names):
                if any(h in n for h in hints):
                    combo.set_selected(i)
                    return
            combo.set_selected(0) # Default to disabled
        
        select(self.front_combo, selections[0], CONFIG["auto_selection_hints"]["front_sink"])
        select(self.rear_l_combo, selections[1], CONFIG["auto_selection_hints"]["rear_left_sink"])
        select(self.rear_r_combo, selections[2], CONFIG["auto_selection_hints"]["rear_right_sink"])
        self.on_sink_selection_changed() # Update sensitive state

    def on_sink_selection_changed(self, *args):
        front, rear_l, rear_r = self.current_selection()
        self.front_vol_scale.set_sensitive(bool(front))
        self.rear_balance_scale.set_sensitive(bool(rear_l) and bool(rear_r))

    def current_selection(self) -> Tuple[str, str, str]:
        def get_name(combo: Gtk.DropDown) -> str:
            item = combo.get_selected_item()
            name = item.get_string() if item else ""
            return name if name != DISABLED_SINK_TEXT else ""
        return get_name(self.front_combo), get_name(self.rear_l_combo), get_name(self.rear_r_combo)

    def _set_volume_async(self, sink: str, vol: int):
        run_cmd(f"pactl set-sink-volume {shlex.quote(sink)} {vol}%")
        return GLib.SOURCE_REMOVE

    def on_front_volume_changed(self, adj: Gtk.Adjustment):
        if sink := self.current_selection()[0]: self._set_volume_async(sink, int(adj.get_value()))

    def on_rear_balance_changed(self, adj: Gtk.Adjustment):
        balance, max_vol = adj.get_value(), 150
        _, rear_l, rear_r = self.current_selection()
        
        right_vol = 100 * (1 + balance / 100) if balance < 0 else 100
        left_vol = 100 * (1 - balance / 100) if balance > 0 else 100

        if rear_l: self._set_volume_async(rear_l, int(left_vol * max_vol / 100))
        if rear_r: self._set_volume_async(rear_r, int(right_vol * max_vol / 100))

    def on_apply(self, *args):
        self.update_status("🚀 Building Audio Splitter Pro pipeline...")
        sinks = self.current_selection()
        comp_cfg = {k: adj.get_value() for k, adj in self.comp_adjs.items()}
        
        # Add limiter configuration
        comp_cfg.update({
            'limiter_input_gain': self.limiter_input_gain.get_value(),
            'limiter_limit': self.limiter_limit.get_value(),
            'limiter_release': self.limiter_release.get_value()
        })
        
        def run_and_update():
            try:
                apply_pipeline(*sinks, comp_cfg)
                self.update_status("✅ Pipeline active! L→Rear L, R→Rear R")
            except Exception as e:
                self.update_status(f"❌ Pipeline failed: {str(e)}")
        
        GLib.idle_add(run_and_update)

    def on_stop(self, *args): 
        self.update_status("🛑 Stopping pipeline...")
        def run_and_update():
            stop_pipeline()
            self.update_status("⏹️ Pipeline stopped")
        GLib.idle_add(run_and_update)

class AudioSplitterApp(Gtk.Application):
    def __init__(self): super().__init__(application_id=APP_ID)
    def do_activate(self, *args): AudioSplitterWindow(self).present()

if __name__ == "__main__":
    AudioSplitterApp().run()
