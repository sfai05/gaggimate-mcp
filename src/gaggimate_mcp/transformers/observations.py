"""Full-resolution weight and stop evidence, independent of curve decimation.

Observations are not inferred settled yields. Do not substitute max(v), modelled
flow or a transient BLE sample for the firmware's final-weight header.
"""

import math
from typing import Optional

from gaggimate_mcp.parsers.shot import ShotData, WEIGHT_SCALE


_EXIT_REASONS = {
    0: "UNKNOWN_OR_LEGACY",
    1: "TARGET_VOLUMETRIC",
    2: "TARGET_PRESSURE",
    3: "TARGET_FLOW",
    4: "TARGET_PUMPED",
    5: "DURATION",
    6: "SAFETY",
    7: "ABORTED",
}


def describe_exit_reason(code: Optional[int]) -> str:
    """Keep unknown future codes explicit; never infer a successful cutoff."""
    return _EXIT_REASONS.get(code, "UNKNOWN") if code is not None else "UNKNOWN"


def _sample_time(shot: ShotData, index: int) -> float:
    return round(shot.samples[index].get('t', index * shot.sample_interval) / 1000, 3)


def observe_termination(shot: ShotData) -> dict:
    """Bracket stop using explicit post-stop flags, not pressure/flow guesses.

    The first extended sample is after stop, not an exact pump-off timestamp.
    Legacy zero reason/delay bytes cannot distinguish unknown from unset.
    """
    first_extended = next((i for i, s in enumerate(shot.samples)
                           if s.get('systemInfo', {}).get('extended_recording') is True), None)
    last_active = None
    if first_extended is not None:
        last_active = next((i for i in range(first_extended - 1, -1, -1)
                            if shot.samples[i].get('systemInfo', {}).get('extended_recording') is False), None)
    return {
        'final_exit_reason_code': shot.final_exit_reason,
        'final_exit_reason': describe_exit_reason(shot.final_exit_reason),
        'reason_source': 'slog_header' if shot.final_exit_reason is not None else 'unavailable',
        'brew_delay_ms': shot.brew_delay_ms if shot.brew_delay_ms else None,
        'recording_duration_s': round(shot.duration / 1000, 3),
        'last_active_sample_time_s': _sample_time(shot, last_active) if last_active is not None else None,
        'first_extended_recording_sample_time_s': _sample_time(shot, first_extended) if first_extended is not None else None,
        'stop_time_source': 'extended_recording_flag_bracket' if last_active is not None else 'unavailable',
        'note': 'Active and extended sample times bracket stop at sampling resolution; recording duration is not brew duration.',
    }


def observe_weight(shot: ShotData) -> dict:
    """Expose literal BLE observations with provenance, not a yield fallback.

    Require the per-sample BLE flag: v can otherwise be model-derived volume.
    A connected flag alone cannot establish scale freshness or settled weight.
    Single samples (including spikes) remain observations, never final yields.
    """
    scale_samples = []
    unconfirmed_positive = False
    for i, s in enumerate(shot.samples):
        value = s.get('v')
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            continue
        if s.get('systemInfo', {}).get('bluetooth_scale_connected') is True:
            scale_samples.append((i, float(value)))
        elif value > 0:
            unconfirmed_positive = True
    positive = [(i, value) for i, value in scale_samples if value > 0]
    last = positive[-1] if positive else None
    last_active = next(((i, value) for i, value in reversed(positive)
                        if shot.samples[i].get('systemInfo', {}).get('extended_recording') is False), None)
    # A later positive tail-drip reading must not erase an earlier zero event.
    # Preserve the pre-zero observation separately: a rebound after reset may
    # represent only the tail drips, not the whole beverage.
    before_zero = None
    first_zero_index = None
    preceding_positive = None
    for i, value in scale_samples:
        if value > 0:
            preceding_positive = (i, value)
        elif (value == 0 and preceding_positive is not None and
              shot.samples[i].get('systemInfo', {}).get('extended_recording') is True):
            before_zero = preceding_positive
            first_zero_index = i
            break
    zero_after_stop = first_zero_index is not None
    warnings = []
    if shot.weight is None:
        warnings.append('FINAL_WEIGHT_HEADER_MISSING')
    if last:
        warnings.append('SCALE_SAMPLES_ARE_OBSERVATIONS_NOT_SETTLED_YIELD')
    if zero_after_stop:
        warnings.append('WEIGHT_ZERO_AFTER_STOP_CAUSE_UNKNOWN')
    if unconfirmed_positive:
        warnings.append('POSITIVE_V_WITHOUT_BLE_CONFIRMATION_NOT_USED_AS_GRAMS')
    if shot.incomplete:
        warnings.append('INCOMPLETE_SHOT_LOG')

    def observation(item):
        if item is None:
            return None
        index, value = item
        return {
            'weight_g': value,
            'time_s': _sample_time(shot, index),
            'sample_index': index,
            'extended_recording': shot.samples[index].get('systemInfo', {}).get('extended_recording'),
            'source': 'full_resolution_v_with_ble_connected_flag',
            'quality': 'raw_observation_not_validated_settled_yield',
        }

    return {
        'header_final_weight_g': shot.final_weight_raw / WEIGHT_SCALE if shot.final_weight_raw is not None else shot.weight,
        'final_weight_source': 'slog_header' if shot.weight is not None else 'unavailable',
        'ble_weight_sample_count': len(scale_samples),
        'positive_ble_weight_sample_count': len(positive),
        'last_positive_scale_sample': observation(last),
        'last_active_positive_scale_sample': observation(last_active),
        'last_positive_scale_sample_before_post_stop_zero': observation(before_zero),
        'first_post_stop_zero_time_s': _sample_time(shot, first_zero_index) if first_zero_index is not None else None,
        'zero_after_stop_observed': zero_after_stop,
        'settled_final_weight_verified': False,
        'warnings': warnings,
    }
