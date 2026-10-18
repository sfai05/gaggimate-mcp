"""Ownership guards: empty/blank naming markers must fail closed.

All delete operations below are mocked. These tests never contact the machine.
"""

import importlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gaggimate_mcp.config import GaggimateConfig
from gaggimate_mcp.models.profile import Profile, PhaseData, PumpSettings


@pytest.mark.parametrize('suffix,label,expected', [
    ('', 'Sweet Nutty', False),
    ('', 'Old Profile [AI]', False),
    (' ', 'A profile ', False),
    ('\t', 'A profile\t', False),
    (' [AI]', 'Test [AI]', True),
    (' [AI]', 'Sweet Nutty', False),
    (' [AI]', 'Test [AI] copy', False),
    (' - Bot', 'Test - Bot', True),
    (' - Bot', 'Test [AI]', False),
])
def test_marker_matching_and_profile_metadata(suffix, label, expected, monkeypatch):
    monkeypatch.setenv('GAGGIMATE_AI_PROFILE_SUFFIX', suffix)
    config = GaggimateConfig(_env_file=None)
    assert config.is_agent_profile_label(label) is expected
    profile = Profile(label=label, description='test', temperature=93,
                      agent_created=True,  # caller cannot override failed inference
                      phases=[PhaseData(name='Brew', phase='brew', duration=25,
                                        pump=PumpSettings(target='pressure', pressure=9, flow=0))])
    assert profile.agent_created is expected
    assert profile.label == label  # never reintroduce markers or rename profiles


def isolated_server(monkeypatch, tmp_path, suffix):
    for key in ('PROFILES_DIR', 'STORAGE_PATH', 'COFFEES_DIR', 'USER_DIR'):
        monkeypatch.setenv('GAGGIMATE_' + key, str(tmp_path / key.lower()))
    server = importlib.import_module('gaggimate_mcp.server')
    config = GaggimateConfig(_env_file=None, ai_profile_suffix=suffix)
    monkeypatch.setattr(server, 'config', config)
    ws = SimpleNamespace(load_profile=AsyncMock(), delete_profile=AsyncMock())
    monkeypatch.setattr(server, 'ws_client', ws)
    return server, ws


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix', ['', ' ', '\t'])
async def test_disabled_marker_blocks_even_confirmed_delete(suffix, monkeypatch, tmp_path):
    server, ws = isolated_server(monkeypatch, tmp_path, suffix)
    ws.load_profile.return_value = {'id':'protected', 'label':'Sweet Nutty'}
    result = json.loads(await server.manage_profile('delete', profile_id='protected', confirm_delete=True))
    assert result['success'] is False
    assert 'suffix is disabled' in result['error']
    ws.load_profile.assert_not_awaited()
    ws.delete_profile.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('label,allowed', [('Sweet Nutty', False), ('Test [AI]', True), ('Test [AI] copy', False)])
async def test_enabled_marker_only_allows_matching_label(label, allowed, monkeypatch, tmp_path):
    server, ws = isolated_server(monkeypatch, tmp_path, ' [AI]')
    ws.load_profile.return_value = {'id':'test-profile', 'label':label}
    result = json.loads(await server.manage_profile('delete', profile_id='test-profile', confirm_delete=True))
    assert result['success'] is allowed
    if allowed:
        ws.delete_profile.assert_awaited_once_with('test-profile')
    else:
        ws.delete_profile.assert_not_awaited()


@pytest.mark.asyncio
async def test_enabled_marker_still_requires_explicit_confirmation(monkeypatch, tmp_path):
    server, ws = isolated_server(monkeypatch, tmp_path, ' [AI]')
    result = json.loads(await server.manage_profile('delete', profile_id='test-profile', confirm_delete=False))
    assert result['success'] is False
    assert 'confirm_delete=True' in result['error']
    ws.load_profile.assert_not_awaited()
    ws.delete_profile.assert_not_awaited()


@pytest.mark.parametrize('temperature,expected', [(50,60), (55,60), (60,60), (93,93), (96,96), (97,96), (100,96)])
def test_explicit_temperature_limits_still_respected(temperature, expected):
    # Updating stale default tests must not weaken custom safety bounds.
    config = GaggimateConfig(_env_file=None, min_temperature=60, max_temperature=96)
    assert config.validate_temperature(temperature) == expected
