import pytest
from unittest.mock import patch, MagicMock
import audio_splitter_gui as asg

# Sample output from `pactl list short sinks`
SAMPLE_PACT_SINKS_OUTPUT = """
22      alsa_output.pci-0000_00_1f.3.hdmi-stereo        module-alsa-card.c      s16le 2ch 44100Hz      RUNNING
23      alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3 module-alsa-card.c      s16le 2ch 44100Hz      RUNNING
24      null    module-null-sink.c      s16le 2ch 44100Hz       RUNNING
"""

# Sample output from `pactl list modules`
SAMPLE_PACT_MODULES_OUTPUT = """
Module #38
        Name: module-remap-source
        Argument: source_name=splitter_left master=null.monitor channels=1
        Usage counter: 2
        Properties:
                prop1=val1

Module #39
        Name: module-remap-source
        Argument: source_name=splitter_right master=null.monitor channels=1
        Usage counter: 1
        Properties:
                prop2=val2

Module #48
        Name: module-loopback
        Argument: source=splitter_left sink=alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3
        Usage counter: n/a
        Properties:
                prop3=val3

Module #49
        Name: module-loopback
        Argument: source=splitter_right sink=alsa_output.pci-0000_00_1f.3.hdmi-stereo
        Usage counter: n/a
        Properties:
                prop4=val4
"""


@patch('audio_splitter_gui.run_cmd')
def test_pactl_sinks_parsing(mock_run_cmd):
    """Tests if pactl_sinks correctly parses sample output."""
    mock_run_cmd.return_value = (0, SAMPLE_PACT_SINKS_OUTPUT, "")
    
    sinks = asg.pactl_sinks()
    
    assert len(sinks) == 3
    assert sinks[0] == ('22', 'alsa_output.pci-0000_00_1f.3.hdmi-stereo')
    assert sinks[1] == ('23', 'alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3')
    assert sinks[2] == ('24', 'null')


@patch('audio_splitter_gui.run_cmd')
def test_pactl_sinks_empty_output(mock_run_cmd):
    """Tests if pactl_sinks handles empty output gracefully."""
    mock_run_cmd.return_value = (0, "", "")
    sinks = asg.pactl_sinks()
    assert len(sinks) == 0


@patch('audio_splitter_gui.run_cmd')
def test_pactl_sinks_error(mock_run_cmd):
    """Tests if pactl_sinks handles a command error."""
    mock_run_cmd.return_value = (1, "", "some error")
    sinks = asg.pactl_sinks()
    assert len(sinks) == 0


@patch('audio_splitter_gui.pactl_modules')
def test_find_module_ids_single_match(mock_pactl_modules):
    """Tests finding a single module ID with one pattern."""
    mock_pactl_modules.return_value = SAMPLE_PACT_MODULES_OUTPUT
    
    ids = asg.find_module_ids(["module-loopback", "sink=alsa_output.pci-0000_03_00.1.hdmi-stereo-extra3"])
    
    assert ids == ["48"]


@patch('audio_splitter_gui.pactl_modules')
def test_find_module_ids_multiple_matches(mock_pactl_modules):
    """Tests finding multiple module IDs with a broad pattern."""
    mock_pactl_modules.return_value = SAMPLE_PACT_MODULES_OUTPUT
    
    ids = asg.find_module_ids(["module-remap-source"])
    
    assert sorted(ids) == ["38", "39"]


@patch('audio_splitter_gui.pactl_modules')
def test_find_module_ids_no_match(mock_pactl_modules):
    """Tests finding no modules when a pattern does not match."""
    mock_pactl_modules.return_value = SAMPLE_PACT_MODULES_OUTPUT
    
    ids = asg.find_module_ids(["non_existent_pattern"])
    
    assert ids == []


@patch('audio_splitter_gui.pactl_modules')
def test_find_module_ids_multiple_patterns(mock_pactl_modules):
    """Tests finding a module that matches multiple patterns."""
    mock_pactl_modules.return_value = SAMPLE_PACT_MODULES_OUTPUT
    
    ids = asg.find_module_ids(["module-loopback", "splitter_right"])
    
    assert ids == ["49"]

@patch('audio_splitter_gui.run_cmd')
def test_unload_modules_by_patterns(mock_run_cmd):
    """Tests that unload is called with the correct module ID."""
    with patch('audio_splitter_gui.find_module_ids', return_value=['48', '49']) as mock_find_ids:
        asg.unload_modules_by_patterns(["some-pattern"])
        
        mock_find_ids.assert_called_once_with(["some-pattern"])
        
        assert mock_run_cmd.call_count == 2
        mock_run_cmd.assert_any_call("pactl unload-module 48")
        mock_run_cmd.assert_any_call("pactl unload-module 49")
