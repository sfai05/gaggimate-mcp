"""Weight/termination regression tests; synthetic files are explicitly test data."""

import json
import struct
from pathlib import Path

import pytest

from gaggimate_mcp.parsers.shot import ShotData, parse_binary_shot
from gaggimate_mcp.transformers.observations import describe_exit_reason, observe_termination, observe_weight
from gaggimate_mcp.transformers.shot import transform_shot_for_ai, VALID_DETAIL_LEVELS


def binary_shot(version=7, reason=5, transition_reason=5, weight=0):
    """Synthetic compact V+SI fixture modelling stop, BLE weight and zero tail."""
    header = bytearray(512 if version >= 5 else 128)
    struct.pack_into('<IBxHHHIIII', header, 0, 0x544F4853, version, len(header), 250, 0,
                     (1 << 0) | (1 << 9) | (1 << 12), 4, 43700, 0)
    struct.pack_into('<H', header, 108, weight)
    if version >= 5:
        struct.pack_into('<HBB25s', header, 110, 0, 0, 0, b'Preinfusion')
        struct.pack_into('<HBB25s', header, 139, 1, 1, transition_reason, b'Brew')
        header[458] = 2
        header[459] = reason
        struct.pack_into('<H', header, 460, 500)
    times = (42949, 43199, 43449, 43699) if version >= 6 else (170, 171, 172, 173)
    fmt = '<IHH' if version >= 6 else '<HHH'
    samples = b''.join(struct.pack(fmt, t, w, si) for t, w, si in
                       zip(times, (233, 236, 0, 0), (15, 29, 29, 29)))
    return bytes(header) + samples


def make_shot(samples, **kwargs):
    return ShotData(id='synthetic', version=7, fields_mask=0, sample_count=len(samples),
                    sample_interval=250, profile_id='test', profile_name='Test', timestamp=0,
                    rating=0, duration=len(samples)*250, weight=kwargs.pop('weight', None),
                    samples=samples, **kwargs)


def sample(t, value, connected=True, extended=False):
    return {'t': t, 'v': value, 'systemInfo': {
        'bluetooth_scale_connected': connected, 'extended_recording': extended}}


@pytest.mark.parametrize('version', [4, 5, 6, 7])
def test_parser_legacy_and_modern_headers(version):
    shot = parse_binary_shot(binary_shot(version), 'test')
    assert shot.weight is None
    assert shot.final_weight_raw == 0
    assert shot.final_exit_reason == (5 if version >= 5 else None)
    assert shot.brew_delay_ms == (500 if version >= 5 else None)
    if version >= 5:
        assert [p.transition_reason for p in shot.phases] == [0, 5]
    assert shot.samples[-2]['v'] == 0


@pytest.mark.parametrize('reason,name', [(0, 'UNKNOWN_OR_LEGACY'), (1, 'TARGET_VOLUMETRIC'),
    (2, 'TARGET_PRESSURE'), (3, 'TARGET_FLOW'), (4, 'TARGET_PUMPED'), (5, 'DURATION'),
    (6, 'SAFETY'), (7, 'ABORTED'), (250, 'UNKNOWN'), (None, 'UNKNOWN')])
def test_reason_codes(reason, name):
    assert describe_exit_reason(reason) == name


@pytest.mark.parametrize('detail', VALID_DETAIL_LEVELS)
def test_weight_evidence_survives_every_detail_level(detail):
    shot = parse_binary_shot(binary_shot(), 'synthetic')
    result = json.loads(json.dumps(transform_shot_for_ai(shot, detail)))
    assert result['final_weight_g'] is None
    w = result['weight_observation']
    assert w['header_final_weight_g'] == 0
    assert w['last_positive_scale_sample']['weight_g'] == 23.6
    assert w['last_positive_scale_sample']['time_s'] == 43.199
    assert w['last_positive_scale_sample']['extended_recording'] is True
    assert w['last_active_positive_scale_sample']['weight_g'] == 23.3
    assert w['zero_after_stop_observed'] is True
    assert w['settled_final_weight_verified'] is False
    assert 'WEIGHT_ZERO_AFTER_STOP_CAUSE_UNKNOWN' in w['warnings']
    t = result['termination']
    assert t['final_exit_reason'] == 'DURATION'
    assert t['brew_delay_ms'] == 500
    assert t['last_active_sample_time_s'] == 42.949
    assert t['first_extended_recording_sample_time_s'] == 43.199
    assert result['phases'][1]['transition_reason'] == 'DURATION'


def test_header_weight_preserved_never_replaced_by_peak_or_last_sample():
    shot = make_shot([sample(0, 90), sample(250, 36), sample(500, 0, extended=True)],
                     weight=37.0, final_weight_raw=370)
    result = transform_shot_for_ai(shot)
    assert result['final_weight_g'] == 37.0
    assert result['weight_observation']['last_positive_scale_sample']['weight_g'] == 36
    assert result['weight_observation']['final_weight_source'] == 'slog_header'


@pytest.mark.parametrize('samples', [[], [sample(0, 0)], [{'t': 0, 'v': 23.6}],
    [sample(0, 23.6, connected=False)], [sample(0, float('nan'))],
    [sample(0, float('inf'))], [sample(0, -1)], [sample(0, True)]])
def test_no_false_scale_yield(samples):
    w = observe_weight(make_shot(samples))
    assert w['last_positive_scale_sample'] is None
    assert w['settled_final_weight_verified'] is False
    assert w['final_weight_source'] == 'unavailable'


def test_raw_spike_is_not_promoted_to_final_yield():
    result = transform_shot_for_ai(make_shot([sample(0, 23), sample(250, 6000)]))
    assert result['final_weight_g'] is None
    assert result['weight_observation']['settled_final_weight_verified'] is False
    assert result['weight_observation']['last_positive_scale_sample']['quality'] == 'raw_observation_not_validated_settled_yield'


def test_disconnect_does_not_turn_modelled_v_into_grams():
    w = observe_weight(make_shot([sample(0, 20), sample(250, 38, connected=False)]))
    assert w['last_positive_scale_sample']['weight_g'] == 20
    assert 'POSITIVE_V_WITHOUT_BLE_CONFIRMATION_NOT_USED_AS_GRAMS' in w['warnings']


def test_zero_followed_by_tail_drip_rebound_preserves_reset_evidence():
    shot = make_shot([sample(0, 23.3), sample(250, 23.6, extended=True),
                      sample(500, 0, extended=True), sample(750, 0.2, extended=True)])
    w = observe_weight(shot)
    assert w['zero_after_stop_observed'] is True
    assert w['first_post_stop_zero_time_s'] == 0.5
    assert w['last_positive_scale_sample']['weight_g'] == 0.2
    assert w['last_positive_scale_sample_before_post_stop_zero']['weight_g'] == 23.6
    assert w['settled_final_weight_verified'] is False
    assert 'WEIGHT_ZERO_AFTER_STOP_CAUSE_UNKNOWN' in w['warnings']


def test_unknown_reason_preserves_numeric_value_and_legacy_delay_is_unknown():
    data = bytearray(binary_shot(reason=250, transition_reason=251))
    struct.pack_into('<H', data, 460, 0)
    result = transform_shot_for_ai(parse_binary_shot(bytes(data), 'test'))
    assert result['termination']['final_exit_reason_code'] == 250
    assert result['termination']['final_exit_reason'] == 'UNKNOWN'
    assert result['termination']['brew_delay_ms'] is None
    assert result['phases'][1]['transition_reason_code'] == 251
    assert result['phases'][1]['transition_reason'] == 'UNKNOWN'


def test_no_extended_flag_does_not_invent_stop_time():
    shot = make_shot([{'t': 100, 'tp': 0, 'pf': 0}])
    t = observe_termination(shot)
    assert t['first_extended_recording_sample_time_s'] is None
    assert t['last_active_sample_time_s'] is None
    assert t['stop_time_source'] == 'unavailable'


def test_extended_only_log_cannot_bracket_stop():
    t = observe_termination(make_shot([sample(0, 2, extended=True)]))
    assert t['last_active_sample_time_s'] is None
    assert t['first_extended_recording_sample_time_s'] == 0
    assert t['stop_time_source'] == 'unavailable'


def test_incomplete_log_is_flagged():
    data = binary_shot()[:-1]
    shot = parse_binary_shot(data, 'test')
    assert shot.incomplete
    assert 'INCOMPLETE_SHOT_LOG' in observe_weight(shot)['warnings']


@pytest.mark.parametrize('detail', VALID_DETAIL_LEVELS)
def test_saved_real_shot_58(detail):
    data = (Path(__file__).parent / 'fixtures' / '000058.slog').read_bytes()
    shot = parse_binary_shot(data, '000058')
    result = json.loads(json.dumps(transform_shot_for_ai(shot, detail)))
    assert shot.version == 7
    assert not shot.incomplete
    assert result['final_weight_g'] is None
    assert result['weight_observation']['header_final_weight_g'] == 0
    assert result['weight_observation']['last_positive_scale_sample']['weight_g'] == 23.6
    assert result['weight_observation']['last_positive_scale_sample']['time_s'] == 43.199
    assert result['weight_observation']['last_active_positive_scale_sample']['weight_g'] == 23.3
    assert result['weight_observation']['zero_after_stop_observed']
    assert result['termination']['final_exit_reason'] == 'DURATION'
    assert result['termination']['recording_duration_s'] == 44.699
    assert result['termination']['last_active_sample_time_s'] == 42.949
    assert result['termination']['first_extended_recording_sample_time_s'] == 43.199
    assert result['termination']['brew_delay_ms'] == 500
    assert [p['transition_reason_code'] for p in result['phases']] == [0, 5, 5]
