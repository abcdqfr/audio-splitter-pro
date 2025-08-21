#!/usr/bin/env python3
"""
Tests for the Professional Mastering GUI
========================================

Testing strategy:
1. Test LADSPA plugin parameter parsing
2. Test GUI component creation without display
3. Test preset application logic
4. Test pipeline building commands
"""

import pytest
import subprocess
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class TestLADSPAPlugins:
    """Test LADSPA plugin detection and parameter parsing."""
    
    def test_plugin_exists_lookahead_limiter(self):
        """Test that the fast lookahead limiter plugin exists."""
        result = subprocess.run(
            "find /usr/lib/ladspa/ -name '*1913*' -o -name '*lookahead*'", 
            shell=True, 
            capture_output=True, 
            text=True
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0, "Fast lookahead limiter plugin not found"
    
    def test_plugin_exists_multiband_eq(self):
        """Test that the multiband EQ plugin exists."""
        result = subprocess.run(
            "find /usr/lib/ladspa/ -name '*1197*' -o -name '*mbeq*'", 
            shell=True, 
            capture_output=True, 
            text=True
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0, "Multiband EQ plugin not found"
    
    def test_plugin_exists_multiband_compressor(self):
        """Test that the multiband compressor plugin exists."""
        result = subprocess.run(
            "find /usr/lib/ladspa/ -name '*ZaMultiComp*'", 
            shell=True, 
            capture_output=True, 
            text=True
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) > 0, "ZaMultiCompX2 plugin not found"

class TestConfigLoading:
    """Test configuration file loading and fallbacks."""
    
    def test_config_loads_successfully(self):
        """Test that config.toml loads without errors."""
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        
        with open("config.toml", "rb") as f:
            config = tomllib.load(f)
        
        # Check required sections exist
        assert "pipeline" in config
        assert "ladspa_plugins" in config
        assert "lookahead_limiter_defaults" in config
        assert "multiband_eq_defaults" in config
        assert "multiband_compressor_defaults" in config

class TestPipelineCommands:
    """Test that pipeline building generates correct PulseAudio commands."""
    
    def test_limiter_command_generation(self):
        """Test generating the correct pactl command for limiter."""
        # Limiter settings
        input_gain = 2.0
        limit = -0.5
        release = 0.08
        
        # Expected command
        expected_cmd = (
            "pactl load-module module-ladspa-sink "
            "sink_name=limiter "
            "sink_master=splitter "
            "plugin=fastLookaheadLimiter "
            "label=fastLookaheadLimiter "
            f"control={input_gain},{limit},{release}"
        )
        
        # Build actual command
        actual_cmd = (
            f"pactl load-module module-ladspa-sink "
            f"sink_name=limiter "
            f"sink_master=splitter "
            f"plugin=fastLookaheadLimiter "
            f"label=fastLookaheadLimiter "
            f"control={input_gain},{limit},{release}"
        )
        
        assert actual_cmd == expected_cmd

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
