#!/usr/bin/env python3
"""
Audio Splitter Pro v3 - Enhanced Sink Management Edition
========================================================

Enhanced version with:
- Professional sink management tab
- Sink renaming and deletion
- Profile switching and activation
- Enhanced HDMI detection and management
- Advanced sink monitoring and diagnostics
- Professional audio pipeline management

Requires: python3-gi, gir1.2-gtk-4.0, LADSPA plugins
"""

import gi
import subprocess
import shlex
from typing import List, Tuple, Optional, Dict
import os
import json
import threading
import time

# Use the built-in tomllib in Python 3.11+, fallback to tomli
try:
    import tomllib
except ImportError:
    import tomli as tomllib

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib

APP_ID = "com.brandon.AudioSplitterGUI.v3"

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
        },
        "sink_management": {
            "enable_advanced_monitoring": True,
            "auto_refresh_interval": 2000,  # ms
            "enable_profile_switching": True,
            "enable_sink_renaming": True,
            "enable_sink_deletion": True
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

# --- Enhanced Sink Management Functions ---
def get_all_audio_cards() -> List[Dict]:
    """Get comprehensive audio card information including profiles."""
    try:
        result = subprocess.run(['pactl', 'list', 'cards'], capture_output=True, text=True, check=True)
        cards = []
        current_card = None
        
        for line in result.stdout.split('\n'):
            if line.startswith('Card #'):
                if current_card:
                    cards.append(current_card)
                current_card = {
                    'id': line.split('#')[1].strip(),
                    'name': '',
                    'description': '',
                    'profiles': [],
                    'active_profile': '',
                    'sinks': []
                }
            elif 'Name:' in line and current_card:
                current_card['name'] = line.split('Name:')[1].strip()
            elif 'device.description' in line and current_card:
                current_card['description'] = line.split('device.description = "')[1].split('"')[0]
            elif 'Active Profile:' in line and current_card:
                current_card['active_profile'] = line.split('Active Profile:')[1].strip()
            elif 'output:' in line and current_card:
                profile_info = line.strip()
                if 'available: yes' in profile_info:
                    current_card['profiles'].append(profile_info)
        
        if current_card:
            cards.append(current_card)
        
        return cards
    except Exception as e:
        print(f"Error getting audio cards: {e}")
        return []

def get_sink_detailed_info() -> List[Dict]:
    """Get detailed sink information including properties and state."""
    try:
        result = subprocess.run(['pactl', 'list', 'sinks'], capture_output=True, text=True, check=True)
        sinks = []
        current_sink = None
        
        for line in result.stdout.split('\n'):
            if line.startswith('Sink #'):
                if current_sink:
                    sinks.append(current_sink)
                current_sink = {
                    'id': line.split('#')[1].strip(),
                    'name': '',
                    'description': '',
                    'state': '',
                    'properties': {},
                    'volume': '',
                    'muted': False
                }
            elif 'Name:' in line and current_sink:
                current_sink['name'] = line.split('Name:')[1].strip()
            elif 'Description:' in line and current_sink:
                current_sink['description'] = line.split('Description:')[1].strip()
            elif 'State:' in line and current_sink:
                current_sink['state'] = line.split('State:')[1].strip()
            elif 'Volume:' in line and current_sink:
                current_sink['volume'] = line.split('Volume:')[1].strip()
            elif 'Muted:' in line and current_sink:
                current_sink['muted'] = 'yes' in line.lower()
            elif 'device.' in line and current_sink:
                if '=' in line:
                    key, value = line.split('=', 1)
                    current_sink['properties'][key.strip()] = value.strip()
        
        if current_sink:
            sinks.append(current_sink)
        
        return sinks
    except Exception as e:
        print(f"Error getting detailed sink info: {e}")
        return []

def activate_audio_profile(card_id: str, profile_name: str) -> bool:
    """Activate a specific audio profile for a card."""
    try:
        result = subprocess.run([
            'pactl', 'set-card-profile', card_id, profile_name
        ], capture_output=True, text=True, check=True)
        return True
    except Exception as e:
        print(f"Error activating profile {profile_name} for card {card_id}: {e}")
        return False

def rename_sink(sink_id: str, new_name: str) -> bool:
    """Rename a sink with a new description."""
    try:
        result = subprocess.run([
            'pactl', 'set-sink-property', sink_id, 'device.description', new_name
        ], capture_output=True, text=True, check=True)
        return True
    except Exception as e:
        print(f"Error renaming sink {sink_id}: {e}")
        return False

def delete_sink(sink_id: str) -> bool:
    """Delete a sink by unloading its module."""
    try:
        # Find the module that created this sink
        result = subprocess.run([
            'pactl', 'list', 'modules'
        ], capture_output=True, text=True, check=True)
        
        module_id = None
        for line in result.stdout.split('\n'):
            if f'sink={sink_id}' in line and 'Module #' in line:
                module_id = line.split('Module #')[1].split()[0]
                break
        
        if module_id:
            subprocess.run(['pactl', 'unload-module', module_id], check=True)
            return True
        else:
            print(f"Could not find module for sink {sink_id}")
            return False
    except Exception as e:
        print(f"Error deleting sink {sink_id}: {e}")
        return False

def refresh_hdmi_sinks() -> bool:
    """Attempt to refresh and activate HDMI sinks."""
    try:
        # Get all cards
        cards = get_all_audio_cards()
        
        for card in cards:
            if 'hdmi' in card['name'].lower() or 'hdmi' in card['description'].lower():
                # Look for HDMI profiles
                for profile in card['profiles']:
                    if 'hdmi' in profile.lower() and 'available: no' in profile:
                        profile_name = profile.split(':')[1].split()[0]
                        print(f"Attempting to activate {profile_name} for {card['description']}")
                        activate_audio_profile(card['id'], profile_name)
                        time.sleep(0.5)  # Give it time to activate
        
        return True
    except Exception as e:
        print(f"Error refreshing HDMI sinks: {e}")
        return False

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
    """Loads compressor slider values from JSON, validating each value."""
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

# --- Pipeline component names from config ---
LEFT_SOURCE = CONFIG["pipeline"]["left_source_name"]
RIGHT_SOURCE = CONFIG["pipeline"]["right_source_name"]
SPLITTER_SINK = CONFIG["pipeline"]["splitter_sink_name"]
COMPRESSOR_SINK = CONFIG["pipeline"]["compressor_sink_name"]

# --- Enhanced Sink Management Tab ---
class SinkManagementTab(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.set_margin_start(10)
        self.set_margin_end(10)
        self.set_margin_top(10)
        self.set_margin_bottom(10)
        
        self.refresh_timer = None
        self.setup_ui()
        self.start_auto_refresh()
    
    def setup_ui(self):
        # Title
        title_label = Gtk.Label(label="🎛️ Professional Sink Management")
        title_label.add_css_class("title-2")
        self.append(title_label)
        
        # Control buttons
        control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        refresh_btn = Gtk.Button(label="🔄 Refresh All")
        refresh_btn.connect("clicked", self.refresh_all_data)
        control_box.append(refresh_btn)
        
        refresh_hdmi_btn = Gtk.Button(label="📺 Refresh HDMI")
        refresh_hdmi_btn.connect("clicked", self.refresh_hdmi_sinks)
        control_box.append(refresh_hdmi_btn)
        
        self.append(control_box)
        
        # Notebook for different views
        notebook = Gtk.Notebook()
        
        # Sinks tab
        sinks_tab = self.create_sinks_tab()
        notebook.append_page(sinks_tab, Gtk.Label(label="🎵 Audio Sinks"))
        
        # Cards tab
        cards_tab = self.create_cards_tab()
        notebook.append_page(cards_tab, Gtk.Label(label="🖥️ Audio Cards"))
        
        # Diagnostics tab
        diagnostics_tab = self.create_diagnostics_tab()
        notebook.append_page(diagnostics_tab, Gtk.Label(label="🔍 Diagnostics"))
        
        self.append(notebook)
    
    def create_sinks_tab(self):
        tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # Sinks list
        self.sinks_tree = Gtk.TreeView()
        self.setup_sinks_tree()
        
        # Scrollable view
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_min_content_height(300)
        scrolled_window.set_child(self.sinks_tree)
        tab.append(scrolled_window)
        
        # Sink actions
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        rename_btn = Gtk.Button(label="✏️ Rename")
        rename_btn.connect("clicked", self.rename_selected_sink)
        actions_box.append(rename_btn)
        
        delete_btn = Gtk.Button(label="🗑️ Delete")
        delete_btn.connect("clicked", self.delete_selected_sink)
        actions_box.append(delete_btn)
        
        tab.append(actions_box)
        
        return tab
    
    def create_cards_tab(self):
        tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # Cards list
        self.cards_tree = Gtk.TreeView()
        self.setup_cards_tree()
        
        # Scrollable view
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_min_content_height(300)
        scrolled_window.set_child(self.cards_tree)
        tab.append(scrolled_window)
        
        # Profile switching
        profile_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        profile_label = Gtk.Label(label="Switch Profile:")
        profile_box.append(profile_label)
        
        self.profile_combo = Gtk.ComboBoxText()
        profile_box.append(self.profile_combo)
        
        switch_btn = Gtk.Button(label="🔄 Switch")
        switch_btn.connect("clicked", self.switch_profile)
        profile_box.append(switch_btn)
        
        tab.append(profile_box)
        
        return tab
    
    def create_diagnostics_tab(self):
        tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # Status display
        self.status_text = Gtk.TextView()
        self.status_text.set_editable(False)
        self.status_text.set_monospace(True)
        
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_min_content_height(300)
        scrolled_window.set_child(self.status_text)
        tab.append(scrolled_window)
        
        # Diagnostic actions
        diag_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        check_btn = Gtk.Button(label="🔍 Check System")
        check_btn.connect("clicked", self.run_diagnostics)
        diag_box.append(check_btn)
        
        fix_btn = Gtk.Button(label="🔧 Auto-Fix")
        fix_btn.connect("clicked", self.auto_fix_issues)
        diag_box.append(fix_btn)
        
        tab.append(diag_box)
        
        return tab
    
    def setup_sinks_tree(self):
        # Create model
        model = Gtk.ListStore(str, str, str, str, str, bool)  # id, name, description, state, volume, muted
        self.sinks_tree.set_model(model)
        
        # Create columns
        renderer = Gtk.CellRendererText()
        
        col_id = Gtk.TreeViewColumn("ID", renderer, text=0)
        self.sinks_tree.append_column(col_id)
        
        col_name = Gtk.TreeViewColumn("Name", renderer, text=1)
        self.sinks_tree.append_column(col_name)
        
        col_desc = Gtk.TreeViewColumn("Description", renderer, text=2)
        self.sinks_tree.append_column(col_desc)
        
        col_state = Gtk.TreeViewColumn("State", renderer, text=3)
        self.sinks_tree.append_column(col_state)
        
        col_vol = Gtk.TreeViewColumn("Volume", renderer, text=4)
        self.sinks_tree.append_column(col_vol)
        
        col_muted = Gtk.TreeViewColumn("Muted", renderer, text=5)
        self.sinks_tree.append_column(col_muted)
    
    def setup_cards_tree(self):
        # Create model
        model = Gtk.ListStore(str, str, str, str, str)  # id, name, description, active_profile, profiles_count
        self.cards_tree.set_model(model)
        
        # Create columns
        renderer = Gtk.CellRendererText()
        
        col_id = Gtk.TreeViewColumn("ID", renderer, text=0)
        self.cards_tree.append_column(col_id)
        
        col_name = Gtk.TreeViewColumn("Name", renderer, text=1)
        self.cards_tree.append_column(col_name)
        
        col_desc = Gtk.TreeViewColumn("Description", renderer, text=2)
        self.cards_tree.append_column(col_desc)
        
        col_profile = Gtk.TreeViewColumn("Active Profile", renderer, text=3)
        self.cards_tree.append_column(col_profile)
        
        col_count = Gtk.TreeViewColumn("Profiles", renderer, text=4)
        self.cards_tree.append_column(col_count)
    
    def refresh_all_data(self, widget=None):
        """Refresh all sink and card data."""
        self.refresh_sinks_data()
        self.refresh_cards_data()
        self.update_diagnostics()
    
    def refresh_sinks_data(self):
        """Refresh the sinks tree view."""
        model = self.sinks_tree.get_model()
        model.clear()
        
        sinks = get_sink_detailed_info()
        for sink in sinks:
            model.append([
                sink['id'],
                sink['name'],
                sink['description'],
                sink['state'],
                sink['volume'],
                sink['muted']
            ])
    
    def refresh_cards_data(self):
        """Refresh the cards tree view."""
        model = self.cards_tree.get_model()
        model.clear()
        
        cards = get_all_audio_cards()
        for card in cards:
            model.append([
                card['id'],
                card['name'],
                card['description'],
                card['active_profile'],
                str(len(card['profiles']))
            ])
    
    def refresh_hdmi_sinks(self, widget=None):
        """Refresh HDMI sinks and update display."""
        success = refresh_hdmi_sinks()
        if success:
            self.log_message("✅ HDMI sinks refreshed successfully")
        else:
            self.log_message("❌ Failed to refresh HDMI sinks")
        
        # Refresh data after a short delay
        GLib.timeout_add(1000, self.refresh_all_data)
    
    def rename_selected_sink(self, widget):
        """Rename the selected sink."""
        selection = self.sinks_tree.get_selection()
        model, treeiter = selection.get_selected()
        if not treeiter:
            self.log_message("❌ No sink selected")
            return
        
        sink_id = model[treeiter][0]
        current_name = model[treeiter][2]
        
        # Create rename dialog
        dialog = Gtk.Dialog(title="Rename Sink", parent=self.get_root(), flags=0)
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Rename", Gtk.ResponseType.OK)
        
        content_area = dialog.get_content_area()
        content_area.append(Gtk.Label(label=f"Rename sink {sink_id}:"))
        
        entry = Gtk.Entry()
        entry.set_text(current_name)
        content_area.append(entry)
        
        dialog.show()
        response = dialog.run()
        
        if response == Gtk.ResponseType.OK:
            new_name = entry.get_text()
            if rename_sink(sink_id, new_name):
                self.log_message(f"✅ Sink {sink_id} renamed to '{new_name}'")
                self.refresh_sinks_data()
            else:
                self.log_message(f"❌ Failed to rename sink {sink_id}")
        
        dialog.destroy()
    
    def delete_selected_sink(self, widget):
        """Delete the selected sink."""
        selection = self.sinks_tree.get_selection()
        model, treeiter = selection.get_selected()
        if not treeiter:
            self.log_message("❌ No sink selected")
            return
        
        sink_id = model[treeiter][0]
        sink_name = model[treeiter][2]
        
        # Create confirmation dialog
        dialog = Gtk.MessageDialog(
            parent=self.get_root(),
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Delete Sink?",
            secondary_text=f"Are you sure you want to delete sink {sink_id} ({sink_name})?\n\nThis action cannot be undone."
        )
        
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.OK:
            if delete_sink(sink_id):
                self.log_message(f"✅ Sink {sink_id} deleted successfully")
                self.refresh_sinks_data()
            else:
                self.log_message(f"❌ Failed to delete sink {sink_id}")
    
    def switch_profile(self, widget):
        """Switch the profile for the selected card."""
        selection = self.cards_tree.get_selection()
        model, treeiter = selection.get_selected()
        if not treeiter:
            self.log_message("❌ No card selected")
            return
        
        card_id = model[treeiter][0]
        profile_name = self.profile_combo.get_active_text()
        
        if not profile_name:
            self.log_message("❌ No profile selected")
            return
        
        if activate_audio_profile(card_id, profile_name):
            self.log_message(f"✅ Profile {profile_name} activated for card {card_id}")
            self.refresh_cards_data()
        else:
            self.log_message(f"❌ Failed to activate profile {profile_name}")
    
    def run_diagnostics(self, widget):
        """Run system diagnostics."""
        self.log_message("🔍 Running system diagnostics...")
        
        # Check PulseAudio status
        try:
            result = subprocess.run(['pulseaudio', '--check'], capture_output=True, text=True)
            if result.returncode == 0:
                self.log_message("✅ PulseAudio is running")
            else:
                self.log_message("❌ PulseAudio is not running")
        except Exception as e:
            self.log_message(f"❌ Error checking PulseAudio: {e}")
        
        # Check available sinks
        sinks = get_sink_detailed_info()
        self.log_message(f"📊 Found {len(sinks)} audio sinks")
        
        # Check HDMI availability
        hdmi_sinks = [s for s in sinks if 'hdmi' in s['name'].lower()]
        self.log_message(f"📺 Found {len(hdmi_sinks)} HDMI sinks")
        
        # Check cards and profiles
        cards = get_all_audio_cards()
        self.log_message(f"🖥️ Found {len(cards)} audio cards")
        
        total_profiles = sum(len(card['profiles']) for card in cards)
        self.log_message(f"🎛️ Total available profiles: {total_profiles}")
    
    def auto_fix_issues(self, widget):
        """Attempt to automatically fix common issues."""
        self.log_message("🔧 Attempting auto-fix...")
        
        # Try to refresh HDMI sinks
        if refresh_hdmi_sinks():
            self.log_message("✅ HDMI sinks refreshed")
        else:
            self.log_message("❌ Failed to refresh HDMI sinks")
        
        # Refresh all data
        GLib.timeout_add(1000, self.refresh_all_data)
    
    def log_message(self, message: str):
        """Log a message to the diagnostics tab."""
        buffer = self.status_text.get_buffer()
        timestamp = time.strftime("%H:%M:%S")
        buffer.insert_at_cursor(f"[{timestamp}] {message}\n")
        
        # Auto-scroll to bottom
        end_iter = buffer.get_end_iter()
        self.status_text.scroll_to_iter(end_iter, 0.0, False, 0.0, 0.0)
    
    def update_diagnostics(self):
        """Update the diagnostics display."""
        self.log_message("📊 Data refreshed")
    
    def start_auto_refresh(self):
        """Start automatic refresh timer."""
        if CONFIG["sink_management"]["enable_advanced_monitoring"]:
            interval = CONFIG["sink_management"]["auto_refresh_interval"]
            self.refresh_timer = GLib.timeout_add(interval, self.auto_refresh)
    
    def auto_refresh(self):
        """Automatic refresh callback."""
        self.refresh_all_data()
        return True  # Continue timer
    
    def stop_auto_refresh(self):
        """Stop automatic refresh timer."""
        if self.refresh_timer:
            GLib.source_remove(self.refresh_timer)
            self.refresh_timer = None

# --- Main Application Window ---
class AudioSplitterProV3(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Audio Splitter Pro v3 - Enhanced Sink Management")
        self.set_default_size(1200, 800)
        
        # Load compressor settings
        self.compressor_settings = load_compressor_settings()
        
        # Setup UI
        self.setup_ui()
        
        # Initial data load
        self.refresh_all_data()
    
    def setup_ui(self):
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        
        # Title
        title_label = Gtk.Label(label="🎵 Audio Splitter Pro v3 - Enhanced Sink Management")
        title_label.add_css_class("title-1")
        main_box.append(title_label)
        
        # Notebook for different tabs
        self.notebook = Gtk.Notebook()
        
        # Main splitter tab
        splitter_tab = self.create_splitter_tab()
        self.notebook.append_page(splitter_tab, Gtk.Label(label="🎛️ Audio Splitter"))
        
        # Sink management tab
        sink_mgmt_tab = SinkManagementTab()
        self.notebook.append_page(sink_mgmt_tab, Gtk.Label(label="🔄 Sink Management"))
        
        # Compressor tab
        compressor_tab = self.create_compressor_tab()
        self.notebook.append_page(compressor_tab, Gtk.Label(label="🎚️ Compressor"))
        
        main_box.append(self.notebook)
        
        # Status bar
        self.status_label = Gtk.Label(label="🎵 Audio Splitter Pro v3 - Ready")
        self.status_label.add_css_class("dim-label")
        main_box.append(self.status_label)
        
        self.set_child(main_box)
    
    def create_splitter_tab(self):
        tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # Output sinks section
        sinks_frame = Gtk.Frame(label="🎵 Output Sinks")
        sinks_frame.set_margin_start(10)
        sinks_frame.set_margin_end(10)
        
        sinks_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        sinks_frame.set_child(sinks_box)
        
        # Front sink
        front_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        front_label = Gtk.Label(label="Front (SPDIF):")
        front_box.append(front_label)
        
        self.front_combo = Gtk.ComboBoxText()
        front_box.append(self.front_combo)
        
        sinks_box.append(front_box)
        
        # Rear left sink
        rear_left_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        rear_left_label = Gtk.Label(label="Rear Left (HDMI):")
        rear_left_box.append(rear_left_label)
        
        self.rear_left_combo = Gtk.ComboBoxText()
        rear_left_box.append(self.rear_left_combo)
        
        sinks_box.append(rear_left_box)
        
        # Rear right sink
        rear_right_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        rear_right_label = Gtk.Label(label="Rear Right (HDMI):")
        rear_right_box.append(rear_right_label)
        
        self.rear_right_combo = Gtk.ComboBoxText()
        rear_right_box.append(self.rear_right_combo)
        
        sinks_box.append(rear_right_box)
        
        tab.append(sinks_frame)
        
        # Output volumes section
        volumes_frame = Gtk.Frame(label="🔊 Output Volumes")
        volumes_frame.set_margin_start(10)
        volumes_frame.set_margin_end(10)
        
        volumes_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        volumes_frame.set_child(volumes_box)
        
        # Front volume
        front_vol_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        front_vol_label = Gtk.Label(label="Front Vol (%):")
        front_vol_box.append(front_vol_label)
        
        self.front_vol_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.front_vol_scale.set_range(0, 100)
        self.front_vol_scale.set_value(100)
        self.front_vol_scale.set_digits(0)
        front_vol_box.append(self.front_vol_scale)
        
        volumes_box.append(front_vol_box)
        
        # Rear balance
        rear_balance_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        rear_balance_label = Gtk.Label(label="Rear Balance (L/R):")
        rear_balance_box.append(rear_balance_label)
        
        self.rear_balance_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.rear_balance_scale.set_range(-100, 100)
        self.rear_balance_scale.set_value(0)
        self.rear_balance_scale.set_digits(0)
        rear_balance_box.append(self.rear_balance_scale)
        
        volumes_box.append(rear_balance_box)
        
        tab.append(volumes_frame)
        
        # Control buttons
        control_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        self.apply_btn = Gtk.Button(label="Apply / Start")
        self.apply_btn.connect("clicked", self.start_splitter)
        control_box.append(self.apply_btn)
        
        self.stop_btn = Gtk.Button(label="Stop")
        self.stop_btn.connect("clicked", self.stop_splitter)
        self.stop_btn.set_sensitive(False)
        control_box.append(self.stop_btn)
        
        refresh_btn = Gtk.Button(label="Refresh Sinks")
        refresh_btn.connect("clicked", self.refresh_sinks)
        control_box.append(refresh_btn)
        
        tab.append(control_box)
        
        return tab
    
    def create_compressor_tab(self):
        tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # Compressor frame
        compressor_frame = Gtk.Frame(label=f"🎚️ Compressor ({CONFIG['ladspa_plugins']['compressor_plugin']})")
        compressor_frame.set_margin_start(10)
        compressor_frame.set_margin_end(10)
        
        compressor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        compressor_frame.set_child(compressor_box)
        
        # Threshold
        threshold_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        threshold_label = Gtk.Label(label="Threshold (dB):")
        threshold_box.append(threshold_label)
        
        self.threshold_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.threshold_scale.set_range(-60, 0)
        self.threshold_scale.set_value(self.compressor_settings["threshold_db"])
        self.threshold_scale.set_digits(1)
        threshold_box.append(self.threshold_scale)
        
        compressor_box.append(threshold_box)
        
        # Ratio
        ratio_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        ratio_label = Gtk.Label(label="Ratio (1:n):")
        ratio_box.append(ratio_label)
        
        self.ratio_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.ratio_scale.set_range(1, 20)
        self.ratio_scale.set_value(self.compressor_settings["ratio"])
        self.ratio_scale.set_digits(1)
        ratio_box.append(self.ratio_scale)
        
        compressor_box.append(ratio_box)
        
        # Knee
        knee_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        knee_label = Gtk.Label(label="Knee (dB):")
        knee_box.append(knee_label)
        
        self.knee_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.knee_scale.set_range(0, 20)
        self.knee_scale.set_value(self.compressor_settings["knee_db"])
        self.knee_scale.set_digits(1)
        knee_box.append(self.knee_scale)
        
        compressor_box.append(knee_box)
        
        # Attack
        attack_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        attack_label = Gtk.Label(label="Attack (ms):")
        attack_box.append(attack_label)
        
        self.attack_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.attack_scale.set_range(0.1, 100)
        self.attack_scale.set_value(self.compressor_settings["attack_ms"])
        self.attack_scale.set_digits(1)
        attack_box.append(self.attack_scale)
        
        compressor_box.append(attack_box)
        
        # Release
        release_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        release_label = Gtk.Label(label="Release (ms):")
        release_box.append(release_label)
        
        self.release_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.release_scale.set_range(10, 1000)
        self.release_scale.set_value(self.compressor_settings["release_ms"])
        self.release_scale.set_digits(0)
        release_box.append(self.release_scale)
        
        compressor_box.append(release_box)
        
        # Makeup Gain
        makeup_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        makeup_label = Gtk.Label(label="Makeup Gain (dB):")
        makeup_box.append(makeup_label)
        
        self.makeup_scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL)
        self.makeup_scale.set_range(0, 30)
        self.makeup_scale.set_value(self.compressor_settings["makeup_gain_db"])
        self.makeup_scale.set_digits(1)
        makeup_box.append(self.makeup_scale)
        
        compressor_box.append(makeup_box)
        
        tab.append(compressor_frame)
        
        return tab
    
    def refresh_sinks(self, widget=None):
        """Refresh the sink combo boxes."""
        # Get available sinks
        sinks = get_sink_detailed_info()
        
        # Clear existing items
        self.front_combo.remove_all()
        self.rear_left_combo.remove_all()
        self.rear_right_combo.remove_all()
        
        # Add sinks based on hints
        for sink in sinks:
            sink_name = sink['name']
            sink_desc = sink['description'].lower()
            
            # Front sink (SPDIF)
            if any(hint in sink_desc for hint in CONFIG["auto_selection_hints"]["front_sink"]):
                self.front_combo.append_text(f"{sink['id']}: {sink['description']}")
            
            # Rear left sink (HDMI)
            if any(hint in sink_desc for hint in CONFIG["auto_selection_hints"]["rear_left_sink"]):
                self.rear_left_combo.append_text(f"{sink['id']}: {sink['description']}")
            
            # Rear right sink (HDMI)
            if any(hint in sink_desc for hint in CONFIG["auto_selection_hints"]["rear_right_sink"]):
                self.rear_right_combo.append_text(f"{sink['id']}: {sink['description']}")
        
        # Set default selections
        if self.front_combo.get_model().iter_n_children(None) > 0:
            self.front_combo.set_active(0)
        if self.rear_left_combo.get_model().iter_n_children(None) > 0:
            self.rear_left_combo.set_active(0)
        if self.rear_right_combo.get_model().iter_n_children(None) > 0:
            self.rear_right_combo.set_active(0)
    
    def start_splitter(self, widget):
        """Start the audio splitter."""
        # Save compressor settings
        settings = {
            "threshold_db": self.threshold_scale.get_value(),
            "ratio": self.ratio_scale.get_value(),
            "knee_db": self.knee_scale.get_value(),
            "attack_ms": self.attack_scale.get_value(),
            "release_ms": self.release_scale.get_value(),
            "makeup_gain_db": self.makeup_scale.get_value()
        }
        save_compressor_settings(settings)
        
        # Update UI
        self.apply_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.status_label.set_label("🎵 Audio Splitter Pro v3 - Running")
        
        # TODO: Implement actual splitter logic
        print("🎵 Audio Splitter Pro v3 started!")
    
    def stop_splitter(self, widget):
        """Stop the audio splitter."""
        # Update UI
        self.apply_btn.set_sensitive(True)
        self.stop_btn.set_sensitive(False)
        self.status_label.set_label("🎵 Audio Splitter Pro v3 - Stopped")
        
        # TODO: Implement actual stop logic
        print("🎵 Audio Splitter Pro v3 stopped!")
    
    def refresh_all_data(self):
        """Refresh all data in the application."""
        self.refresh_sinks()

# --- Application Class ---
class AudioSplitterProApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
    
    def do_activate(self, *args):
        AudioSplitterProV3(self).present()

# --- Main Entry Point ---
if __name__ == "__main__":
    app = AudioSplitterProApp()
    app.run()
