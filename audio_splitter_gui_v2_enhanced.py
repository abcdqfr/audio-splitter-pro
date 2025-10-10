#!/usr/bin/env python3
import gi
import subprocess
import shlex
from typing import List, Tuple, Optional, Dict
import os
import json
import re

# Use the built-in tomllib in Python 3.11+, fallback to tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

APP_ID = "com.brandon.AudioSplitterGUI.v2.enhanced"

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

# Define the path for the persistent compressor settings
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'compressor_settings.json')

# --- Enhanced GPU Detection Functions ---
def get_gpu_info() -> Dict:
    """Get comprehensive GPU information including all audio outputs."""
    gpu_info = {
        'intel': {'name': 'Intel UHD Graphics 630', 'card': None, 'outputs': []},
        'amd': {'name': 'AMD RX 7900 XT/XTX', 'card': None, 'outputs': []}
    }
    
    try:
        # Get GPU info from lspci
        result = subprocess.run(['lspci'], capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if 'VGA' in line:
                if 'Intel' in line:
                    gpu_info['intel']['pci'] = line.split()[0]
                elif 'AMD' in line or 'ATI' in line:
                    gpu_info['amd']['pci'] = line.split()[0]
        
        # Get audio card info
        result = subprocess.run(['pactl', 'list', 'cards'], capture_output=True, text=True, check=True)
        cards = []
        current_card = None
        
        print("🔍 Parsing audio cards...")
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('Card #'):
                if current_card:
                    cards.append(current_card)
                    print(f"  Added card: {current_card['name']} - {len(current_card['outputs'])} outputs")
                current_card = {
                    'id': line.split('#')[1].strip(),
                    'name': '',
                    'description': '',
                    'profiles': [],
                    'active_profile': '',
                    'outputs': []
                }
            elif line.startswith('Name:') and current_card:
                current_card['name'] = line.split('Name:')[1].strip()
            elif line.startswith('Description:') and current_card:
                current_card['description'] = line.split('Description:')[1].strip()
            elif line.startswith('Active Profile:') and current_card:
                current_card['active_profile'] = line.split('Active Profile:')[1].strip()
            elif line.startswith('output:') and current_card:
                # Parse profile line like: output:hdmi-stereo-extra1: Digital Stereo (HDMI 2) Output (sinks: 1, sources: 0, priority: 38468, available: yes)
                if 'available: yes' in line:
                    profile_match = re.search(r'output:([^:]+):\s*(.+?)\s*\(sinks:', line)
                    if profile_match:
                        profile_name = profile_match.group(1)
                        description = profile_match.group(2).strip()
                        current_card['outputs'].append({
                            'profile': profile_name,
                            'description': description,
                            'available': True
                        })
                        print(f"    Found output: {profile_name} - {description}")
        
        if current_card:
            cards.append(current_card)
            print(f"  Added final card: {current_card['name']} - {len(current_card['outputs'])} outputs")
        
        # Map cards to GPUs
        for card in cards:
            print(f"  Checking card: {card['name']} - Description: '{card['description']}'")
            if 'ATI' in card['description'] or 'Navi' in card['description'] or 'AMD' in card['description']:
                gpu_info['amd']['card'] = card
                print(f"  Mapped AMD card: {card['name']}")
            elif 'Intel' in card['description'] or 'PCH' in card['description']:
                gpu_info['intel']['card'] = card
                print(f"  Mapped Intel card: {card['name']}")
        
        print(f"🎮 GPU Detection Complete:")
        print(f"  Intel: {gpu_info['intel']['name']} - {len(gpu_info['intel']['card']['outputs']) if gpu_info['intel']['card'] else 0} outputs")
        print(f"  AMD: {gpu_info['amd']['name']} - {len(gpu_info['amd']['card']['outputs']) if gpu_info['amd']['card'] else 0} outputs")
        
    except Exception as e:
        print(f"Error detecting GPUs: {e}")
    
    return gpu_info

def enable_all_gpu_profiles(gpu_info: Dict) -> None:
    """Enable all available profiles for each GPU to maximize output options."""
    print("\n🔧 Enabling all available GPU profiles...")
    
    for gpu_type, info in gpu_info.items():
        if info['card']:
            card_name = info['card']['name']
            print(f"  Enabling profiles for {gpu_type.upper()} GPU ({card_name})...")
            
            # Try to enable pro-audio profile first if available
            pro_audio_available = any('pro-audio' in output['profile'] for output in info['card']['outputs'])
            if pro_audio_available:
                print(f"    Setting {gpu_type} to pro-audio profile...")
                subprocess.run(['pactl', 'set-card-profile', card_name, 'pro-audio'], check=False)
            else:
                # Enable the profile with the most outputs
                best_profile = None
                max_outputs = 0
                
                for output in info['card']['outputs']:
                    if output['available']:
                        # Count how many outputs this profile provides
                        profile_outputs = len([o for o in info['card']['outputs'] if o['profile'] == output['profile']])
                        if profile_outputs > max_outputs:
                            max_outputs = profile_outputs
                            best_profile = output['profile']
                
                if best_profile and best_profile != info['card']['active_profile']:
                    print(f"    Setting {gpu_type} to {best_profile} profile...")
                    subprocess.run(['pactl', 'set-card-profile', card_name, best_profile], check=False)
                else:
                    print(f"    {gpu_type} already using optimal profile: {info['card']['active_profile']}")
    
    # Wait for profiles to activate
    subprocess.run(['sleep', '1'], check=False)

# --- Persistence Functions ---
def save_compressor_settings(settings: dict):
    """Saves compressor slider values to a JSON file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=4)
        print(f"Compressor settings saved to {SETTINGS_FILE}")
    except IOError as e:
        print(f"Error saving compressor settings: {e}")

def load_compressor_settings() -> dict:
    """
    Loads compressor slider values from JSON, validating each value.
    If the file doesn't exist, is corrupt, or a value is invalid,
    it falls back to the defaults from config.toml.
    """
    defaults = CONFIG["compressor_defaults"]
    
    if not os.path.exists(SETTINGS_FILE):
        print("No settings file found. Using defaults.")
        return defaults

    try:
        with open(SETTINGS_FILE, 'r') as f:
            loaded_settings = json.load(f)
        
        # Validate the loaded settings
        validated_settings = {}
        for key, default_value in defaults.items():
            loaded_value = loaded_settings.get(key)
            if isinstance(loaded_value, (int, float)):
                validated_settings[key] = loaded_value
            else:
                print(f"Warning: Invalid or missing value for '{key}'. Using default.")
                validated_settings[key] = default_value
        
        print(f"Compressor settings loaded and validated from {SETTINGS_FILE}")
        return validated_settings

    except (IOError, json.JSONDecodeError) as e:
        print(f"Error loading or parsing {SETTINGS_FILE}: {e}. Using defaults.")
        return defaults

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
        if not line.strip():
            continue
        
        parts = line.strip().split(maxsplit=2)
        
        if len(parts) >= 2 and parts[1] not in internal_sinks:
            valid_sinks.append(parts[1])
    
    return valid_sinks

def get_sink_display_names() -> dict[str, str]:
    """
    Parses detailed sink information to create a mapping from raw sink names
    to user-friendly display names, prioritizing the 'Description' field.
    """
    print("Generating display names for sinks...")
    code, out, _ = run_cmd("pactl list sinks")
    if code != 0:
        return {}

    sink_map = {}
    current_sink_name = ""
    current_description = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith('Name:'):
            # Process the previous sink block before starting a new one
            if current_sink_name and current_description:
                sink_map[current_sink_name] = current_description
                print(f"  Mapping '{current_sink_name}' -> '{current_description}'")
            
            current_sink_name = line.split('Name:')[1].strip()
            current_description = "" # Reset for the new sink

        if line.startswith('Description:'):
            current_description = line.split('Description:')[1].strip()

    # Process the very last sink block in the output
    if current_sink_name and current_description:
        sink_map[current_sink_name] = current_description
        print(f"  Mapping '{current_sink_name}' -> '{current_description}'")

    return sink_map

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
    print("🛑 Stopping existing pipeline modules...")
    
    # Clean up in reverse order of creation for stability
    print("  Unloading loopback modules...")
    unload_modules_by_patterns(["module-loopback", LEFT_SRC])
    unload_modules_by_patterns(["module-loopback", RIGHT_SRC])
    
    print("  Unloading remap source modules...")
    unload_modules_by_patterns(["module-remap-source", LEFT_SRC])
    unload_modules_by_patterns(["module-remap-source", RIGHT_SRC])
    
    print("  Unloading effects modules...")
    unload_modules_by_patterns(["module-ladspa-sink", COMPRESSOR_SINK])

    # This is the critical step to ensure idempotency
    print(f"  Unloading null sink '{SPLITTER_SINK}'...")
    unload_modules_by_patterns(["module-null-sink", f"sink_name={SPLITTER_SINK}"])
    
    print("✅ Pipeline cleanup complete")

def apply_pipeline(front_sink: str, rear_l_sink: str, rear_r_sink: str, comp_cfg: dict) -> None:
    print("\n🚀 Building Audio Splitter Pro pipeline...")
    print(f"Selected outputs: Front={front_sink or 'DISABLED'}, Rear Left={rear_l_sink or 'DISABLED'}, Rear Right={rear_r_sink or 'DISABLED'}")
    
    stop_pipeline()
    
    # Enable all GPU profiles to ensure maximum output availability
    gpu_info = get_gpu_info()
    enable_all_gpu_profiles(gpu_info)

    sinks = pactl_sinks()
    print(f"Available sinks: {sinks}")
    
    splitter = SPLITTER_SINK if SPLITTER_SINK in sinks else "null" if "null" in sinks else ""
    if not splitter:
        print(f"Creating new splitter sink: {SPLITTER_SINK}")
        run_cmd(f"pactl load-module module-null-sink sink_name={SPLITTER_SINK} sink_properties=device.description=AudioSplitter")
        splitter = SPLITTER_SINK
    else:
        print(f"Using existing sink for splitter: {splitter}")

    # Set up compressor
    print("Setting up compressor...")
    controls = (f"1,{comp_cfg['attack_ms']},{comp_cfg['release_ms']},"
                f"{comp_cfg['threshold_db']},{comp_cfg['ratio']},"
                f"{comp_cfg['knee_db']},{comp_cfg['makeup_gain_db']}")
    run_cmd(f"pactl load-module module-ladspa-sink sink_name={COMPRESSOR_SINK} sink_master={splitter} plugin={SC4_PLUGIN} label=sc4 control={controls}")
    run_cmd(f"pactl set-default-sink {COMPRESSOR_SINK}")

    # Create split channels
    print("Creating L/R channel splits...")
    run_cmd(f"pactl load-module module-remap-source source_name={LEFT_SRC} master={splitter}.monitor channels=1 channel_map=mono master_channel_map=front-left")
    run_cmd(f"pactl load-module module-remap-source source_name={RIGHT_SRC} master={splitter}.monitor channels=1 channel_map=mono master_channel_map=front-right")
    
    # Route to outputs
    if front_sink:
        print(f"Routing both channels to front sink: {front_sink}")
        run_cmd(f"pactl load-module module-loopback source={LEFT_SRC} sink={front_sink} latency_msec=50 source_dont_move=true sink_dont_move=true")
        run_cmd(f"pactl load-module module-loopback source={RIGHT_SRC} sink={front_sink} latency_msec=50 source_dont_move=true sink_dont_move=true")
    
    if rear_l_sink:
        print(f"Routing left channel to rear left sink: {rear_l_sink}")
        run_cmd(f"pactl load-module module-loopback source={LEFT_SRC} sink={rear_l_sink} latency_msec=50 source_dont_move=true sink_dont_move=true")
        
    if rear_r_sink:
        print(f"Routing right channel to rear right sink: {rear_r_sink}")
        run_cmd(f"pactl load-module module-loopback source={RIGHT_SRC} sink={rear_r_sink} latency_msec=50 source_dont_move=true sink_dont_move=true")
        
    print("✅ Audio pipeline setup complete!")

class AudioSplitterWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application):
        super().__init__(application=app, title="Audio Splitter Pro v2 Enhanced - GPU Output Detection")
        self.set_default_size(700, 800)

        # Load persistent or default compressor settings
        compressor_settings = load_compressor_settings()

        self.comp_adjs = {k: Gtk.Adjustment(value=v, lower=l, upper=u, step_increment=s, page_increment=p) for k, (v,l,u,s,p) in {
            "threshold_db": (compressor_settings["threshold_db"], -60, 0, 1, 5), 
            "ratio": (compressor_settings["ratio"], 1, 20, 0.5, 2),
            "knee_db": (compressor_settings["knee_db"], 0, 20, 1, 5), 
            "attack_ms": (compressor_settings["attack_ms"], 0.1, 200, 0.1, 10),
            "release_ms": (compressor_settings["release_ms"], 1, 1000, 1, 50), 
            "makeup_gain_db": (compressor_settings["makeup_gain_db"], 0, 40, 1, 5),
        }.items()}
        self.front_vol_adj = Gtk.Adjustment(value=100, lower=0, upper=150, step_increment=1, page_increment=10)
        self.rear_balance_adj = Gtk.Adjustment(value=0, lower=-100, upper=100, step_increment=5, page_increment=20)
        
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15, margin_top=15, margin_bottom=15, margin_start=15, margin_end=15)
        self.set_child(outer)

        # GPU Information Display
        gpu_frame = self._create_gpu_info_frame()
        outer.append(gpu_frame)

        # Sink selection
        self.sinks_store = Gtk.StringList()
        self.sink_name_map = {} # To store {display_name: raw_name}
        self.front_combo = Gtk.DropDown(model=self.sinks_store)
        self.rear_l_combo = Gtk.DropDown(model=self.sinks_store)
        self.rear_r_combo = Gtk.DropDown(model=self.sinks_store)
        sink_frame = self._create_frame("Output Sinks", [
            ("Front (SPDIF)", self.front_combo), ("Rear Left (HDMI)", self.rear_l_combo), ("Rear Right (HDMI)", self.rear_r_combo)
        ])
        outer.append(sink_frame)

        # Volume controls
        self.front_vol_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.front_vol_adj, draw_value=True)
        self.rear_balance_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.rear_balance_adj, draw_value=True)
        vol_frame = self._create_frame("Output Volumes", [
            ("Front Vol (%)", self.front_vol_scale),
            ("Rear Balance (L/R)", self.rear_balance_scale)
        ])
        outer.append(vol_frame)

        # Compressor controls
        comp_frame = self._create_frame(f"Compressor ({SC4_PLUGIN})", [])
        outer.append(comp_frame)
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
        outer.append(btn_box)
        for label, callback in [("Apply / Start", self.on_apply), ("Stop", self.on_stop), ("Refresh Sinks", self.on_refresh)]:
            btn = Gtk.Button(label=label)
            btn.connect("clicked", callback)
            btn_box.append(btn)

        self.front_vol_adj.connect("value-changed", self.on_front_volume_changed)
        self.rear_balance_adj.connect("value-changed", self.on_rear_balance_changed)
        
        self.front_combo.connect("notify::selected-item", self.on_sink_selection_changed)
        self.rear_l_combo.connect("notify::selected-item", self.on_sink_selection_changed)
        self.rear_r_combo.connect("notify::selected-item", self.on_sink_selection_changed)
        
        self.on_refresh()

    def _create_gpu_info_frame(self) -> Gtk.Frame:
        """Create a frame displaying comprehensive GPU information."""
        frame = Gtk.Frame(label="🎮 GPU & Audio Output Detection")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8, margin_bottom=8, margin_start=8, margin_end=8)
        frame.set_child(box)
        
        # GPU info will be populated in on_refresh
        self.gpu_info_label = Gtk.Label(label="Detecting GPUs and audio outputs...")
        self.gpu_info_label.set_markup("<span color='#4a9eff'>🔍 Detecting GPUs and audio outputs...</span>")
        box.append(self.gpu_info_label)
        
        return frame

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
        print("\n🔍 Refreshing audio sinks with enhanced GPU detection...")
        
        # Get comprehensive GPU information
        gpu_info = get_gpu_info()
        
        # Update GPU info display
        gpu_text = "<b>🎮 GPU &amp; Audio Output Detection</b>\n\n"
        for gpu_type, info in gpu_info.items():
            if info['card']:
                gpu_text += f"<b>{gpu_type.upper()}:</b> {info['name']}\n"
                gpu_text += f"  Card: {info['card']['name']}\n"
                gpu_text += f"  Active Profile: {info['card']['active_profile']}\n"
                gpu_text += f"  Available Outputs: {len(info['card']['outputs'])}\n"
                for output in info['card']['outputs']:
                    if output['available']:
                        gpu_text += f"    ✓ {output['profile']}: {output['description']}\n"
                gpu_text += "\n"
            else:
                gpu_text += f"<b>{gpu_type.upper()}:</b> Not detected\n\n"
        
        self.gpu_info_label.set_markup(gpu_text)
        
        # Enable all GPU profiles to maximize output availability
        enable_all_gpu_profiles(gpu_info)

        selections = self.current_selection()
        
        # Get raw sink names and the display name map
        raw_sinks = pactl_sinks()
        self.sink_name_map = get_sink_display_names()

        # Create a list of display names for the UI
        display_names = [DISABLED_SINK_TEXT]
        # Create a reverse map for easy lookup: {raw_name: display_name}
        raw_to_display = {v: k for k, v in self.sink_name_map.items()}

        for raw_sink in raw_sinks:
            display_names.append(self.sink_name_map.get(raw_sink, raw_sink))

        self.sinks_store.splice(0, self.sinks_store.get_n_items(), display_names)
        
        print(f"Audio Splitter Pro Enhanced: Found {len(raw_sinks)} sinks.")
        
        def select(combo: Gtk.DropDown, saved_raw: str, hints: List[str], purpose: str):
            # Try to restore previous selection using the raw name
            if saved_raw and saved_raw in raw_to_display:
                saved_display = raw_to_display[saved_raw]
                if saved_display in display_names:
                    combo.set_selected(display_names.index(saved_display))
                    print(f"Audio Splitter Pro Enhanced: Reused previous {purpose} selection: {saved_display}")
                    return

            # Score-based selection
            best_score = -1
            best_index = 0
            
            used_display_names = set()
            # Get current display names from other combos
            for c in [self.front_combo, self.rear_l_combo, self.rear_r_combo]:
                if c is not combo and c.get_selected_item():
                    used_display_names.add(c.get_selected_item().get_string())

            for i, display_name in enumerate(display_names):
                if i == 0 or display_name in used_display_names:
                    continue
                    
                score = 0
                # Match hints against both display name and raw name for robustness
                raw_name = next((k for k, v in self.sink_name_map.items() if v == display_name), display_name)
                
                for h in hints:
                    if h.lower() in display_name.lower() or h.lower() in raw_name.lower():
                        score += 1

                if score > best_score:
                    best_score = score
                    best_index = i
            
            if best_score > 0:
                combo.set_selected(best_index)
                print(f"Audio Splitter Pro Enhanced: Auto-selected {purpose} sink: {display_names[best_index]} (score: {best_score})")
                return
                
            combo.set_selected(0)
            print(f"Audio Splitter Pro Enhanced: No match found for {purpose} sink, set to disabled.")
        
        select(self.front_combo, selections[0], CONFIG["auto_selection_hints"]["front_sink"], "front")
        select(self.rear_l_combo, selections[1], CONFIG["auto_selection_hints"]["rear_left_sink"], "rear left")
        select(self.rear_r_combo, selections[2], CONFIG["auto_selection_hints"]["rear_right_sink"], "rear right")
        self.on_sink_selection_changed()

    def on_sink_selection_changed(self, *args):
        front, rear_l, rear_r = self.current_selection()
        self.front_vol_scale.set_sensitive(bool(front))
        self.rear_balance_scale.set_sensitive(bool(rear_l) and bool(rear_r))

    def current_selection(self) -> Tuple[str, str, str]:
        def get_raw_name(combo: Gtk.DropDown) -> str:
            item = combo.get_selected_item()
            if not item:
                return ""
            
            display_name = item.get_string()
            if display_name == DISABLED_SINK_TEXT:
                return ""
            
            # Find the raw name from our map, otherwise assume display name is raw name
            return next((k for k, v in self.sink_name_map.items() if v == display_name), display_name)

        return get_raw_name(self.front_combo), get_raw_name(self.rear_l_combo), get_raw_name(self.rear_r_combo)

    def _set_volume_async(self, sink: str, vol: int):
        run_cmd(f"pactl set-sink-volume {shlex.quote(sink)} {vol}%")
        return GLib.SOURCE_REMOVE

    def on_front_volume_changed(self, adj: Gtk.Adjustment):
        if sink := self.current_selection()[0]: self._set_volume_async(sink, int(adj.get_value()))

    def on_rear_balance_changed(self, adj: Gtk.Adjustment):
        balance = adj.get_value() # Value is from -100 (left) to 100 (right)
        _, rear_l, rear_r = self.current_selection()
        
        # This logic implements a standard balance control that only attenuates.
        # When centered (balance=0), both volumes are 100%.
        # As the slider moves, the opposite channel's volume is reduced.
        right_vol = 100 * (1 + balance / 100) if balance < 0 else 100
        left_vol = 100 * (1 - balance / 100) if balance > 0 else 100

        # The calculated volumes are already percentages, so they can be passed directly.
        # This prevents the volume from exceeding 100%.
        if rear_l: self._set_volume_async(rear_l, int(left_vol))
        if rear_r: self._set_volume_async(rear_r, int(right_vol))

    def on_apply(self, *args):
        sinks = self.current_selection()
        comp_cfg = {k: adj.get_value() for k, adj in self.comp_adjs.items()}
        
        # Save the current compressor settings for persistence
        save_compressor_settings(comp_cfg)

        GLib.idle_add(apply_pipeline, *sinks, comp_cfg)

    def on_stop(self, *args): GLib.idle_add(stop_pipeline)

class AudioSplitterApp(Gtk.Application):
    def __init__(self): super().__init__(application_id=APP_ID)
    def do_activate(self, *args): AudioSplitterWindow(self).present()

if __name__ == "__main__":
    AudioSplitterApp().run()
