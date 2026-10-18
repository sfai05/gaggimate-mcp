"""Exercise the real analyze_shot JSON path with a saved log (no device I/O)."""

import importlib
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from gaggimate_mcp.parsers.shot import parse_binary_shot
from gaggimate_mcp.transformers.shot import VALID_DETAIL_LEVELS


@pytest.mark.asyncio
@pytest.mark.parametrize('detail', VALID_DETAIL_LEVELS)
async def test_analyze_shot_serializes_saved_endpoint_evidence(detail, monkeypatch, tmp_path):
    # Import-time storage is isolated, not the real user/bag store.
    for name in ('PROFILES_DIR', 'STORAGE_PATH', 'COFFEES_DIR', 'USER_DIR'):
        monkeypatch.setenv('GAGGIMATE_' + name, str(tmp_path / name.lower()))
    server = importlib.import_module('gaggimate_mcp.server')
    data = (Path(__file__).parent / 'fixtures' / '000058.slog').read_bytes()
    shot = parse_binary_shot(data, '000058')
    fetch = AsyncMock(return_value=shot)
    monkeypatch.setattr(server.http_client, 'fetch_shot', fetch)
    monkeypatch.setattr(server.rating_storage, 'get_rating', Mock(return_value=None))
    result = json.loads(await server.analyze_shot('58', detail=detail))
    fetch.assert_awaited_once_with('000058')
    assert result['success'] is True
    assert result['incomplete'] is False
    assert result['shot']['final_weight_g'] is None
    assert result['shot']['weight_observation']['last_positive_scale_sample']['weight_g'] == 23.6
    assert result['shot']['weight_observation']['last_positive_scale_sample']['time_s'] == 43.199
    assert result['shot']['weight_observation']['zero_after_stop_observed'] is True
    assert result['shot']['termination']['final_exit_reason'] == 'DURATION'
    assert result['shot']['termination']['brew_delay_ms'] == 500
