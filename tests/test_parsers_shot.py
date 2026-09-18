"""Tests for .slog binary shot file parser."""

import struct
from gaggimate_mcp.parsers.shot import parse_binary_shot


class TestBinaryShotParser:
    """Test binary shot file parsing."""

    def test_parse_minimal_shot_v4(self):
        """Test parsing a minimal V4 shot file."""
        # Create minimal valid V4 shot file
        magic = 0x544F4853  # 'SHOT'
        version = 4
        reserved0 = 0
        header_size = 128
        sample_interval = 100  # milliseconds
        reserved1 = 0
        fields_mask = 0b1111  # T, TT, CT, TP (4 fields)
        sample_count = 2
        duration = 20000  # 20 seconds
        timestamp = 1640000000
        profile_id = b'test_profile\x00' + b'\x00' * 19
        profile_name = b'Test Profile\x00' + b'\x00' * 35
        weight = 360  # 36.0 grams

        # Build header
        header = struct.pack(
            '<IB B H H H I I I I 32s 48s H',
            magic, version, reserved0, header_size,
            sample_interval, reserved1,
            fields_mask, sample_count, duration, timestamp,
            profile_id, profile_name, weight
        )

        # Pad header to 128 bytes
        header = header + b'\x00' * (128 - len(header))

        # Sample data: 2 samples, 4 fields each (8 bytes per sample)
        # Sample 1: t=1000ms, tt=93.0°C, ct=92.5°C, tp=9.0 bar
        sample1 = struct.pack('<HHHH', 10, 930, 925, 90)

        # Sample 2: t=2000ms, tt=93.0°C, ct=93.0°C, tp=9.0 bar
        sample2 = struct.pack('<HHHH', 20, 930, 930, 90)

        binary_data = header + sample1 + sample2

        # Parse
        shot = parse_binary_shot(binary_data, "000001")

        # Verify
        assert shot.id == "000001"
        assert shot.version == 4
        assert shot.fields_mask == 0b1111
        assert shot.sample_count == 2
        assert shot.sample_interval == 100
        assert shot.profile_id == "test_profile"
        assert shot.profile_name == "Test Profile"
        assert shot.timestamp == 1640000000
        assert shot.duration == 20000
        assert shot.weight == 36.0
        assert shot.incomplete == False
        assert len(shot.samples) == 2
        assert len(shot.phases) == 0  # V4 has no phase data

        # Check first sample
        assert shot.samples[0]['t'] == 1000  # 10 * 100ms
        assert shot.samples[0]['tt'] == 93.0  # 930 / 10
        assert shot.samples[0]['ct'] == 92.5  # 925 / 10
        assert shot.samples[0]['tp'] == 9.0  # 90 / 10

    def test_parse_shot_invalid_magic(self):
        """Test parsing shot file with invalid magic number."""
        invalid_data = struct.pack('<I', 0xDEADBEEF) + b'\x00' * 124

        try:
            parse_binary_shot(invalid_data, "000001")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid shot magic" in str(e)

    def test_parse_shot_html_response_gives_friendly_error(self):
        """Test that HTML response (firmware 1.8.0 issue) gives a clear error."""
        html_data = b'<!DOCTYPE html><html><body>Not Found</body></html>'
        html_data = html_data + b'\x00' * (128 - len(html_data))

        try:
            parse_binary_shot(html_data, "000195")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "HTML" in str(e)
            assert "overloaded" in str(e)

    def test_parse_shot_short_html_detected_before_size_check(self):
        """Short HTML responses should get HTML error, not 'too small' error."""
        short_html = b'<html>err</html>'  # < 128 bytes
        try:
            parse_binary_shot(short_html, "000195")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "HTML" in str(e)
            assert "too small" not in str(e)

    def test_parse_shot_firmware_1_8_0_magic_bytes(self):
        """Test the specific magic bytes from the 1.8.0 error report."""
        # 0x6f64213c = "<!do" in little-endian ASCII
        data = b'<!doctype html>' + b'\x00' * 113

        try:
            parse_binary_shot(data, "000195")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "HTML" in str(e)

    def test_parse_shot_too_small(self):
        """Test parsing shot file that's too small."""
        too_small = b'\x00' * 50

        try:
            parse_binary_shot(too_small, "000001")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "too small" in str(e)

    def test_parse_shot_with_phase_transitions(self):
        """Test parsing V5 shot file with phase transitions."""
        magic = 0x544F4853
        version = 5
        reserved0 = 0
        header_size = 512
        sample_interval = 100
        reserved1 = 0
        fields_mask = 0b11  # T, TT (2 fields)
        sample_count = 3
        duration = 30000
        timestamp = 1640000000
        profile_id = b'v5_profile\x00' + b'\x00' * 21
        profile_name = b'V5 Profile\x00' + b'\x00' * 37
        weight = 400  # 40.0 grams

        # Build header up to weight (110 bytes)
        header_part1 = struct.pack(
            '<IB B H H H I I I I 32s 48s H',
            magic, version, reserved0, header_size,
            sample_interval, reserved1,
            fields_mask, sample_count, duration, timestamp,
            profile_id, profile_name, weight
        )

        # Phase transitions: 2 transitions
        # Transition 1: sample 0, phase 0, "Preinfusion"
        transition1 = struct.pack('<HB x 25s', 0, 0, b'Preinfusion\x00' + b'\x00' * 13)

        # Transition 2: sample 2, phase 1, "Extraction"
        transition2 = struct.pack('<HB x 25s', 2, 1, b'Extraction\x00' + b'\x00' * 14)

        # Pad to transition count position (458 bytes)
        padding = b'\x00' * (458 - len(header_part1) - len(transition1) - len(transition2))

        # Transition count
        transition_count = struct.pack('B', 2)

        # Pad to 512 bytes
        header = header_part1 + transition1 + transition2 + padding + transition_count
        header = header + b'\x00' * (512 - len(header))

        # Sample data: 3 samples, 2 fields each
        sample1 = struct.pack('<HH', 10, 900)  # t=1000ms, tt=90.0°C
        sample2 = struct.pack('<HH', 20, 920)  # t=2000ms, tt=92.0°C
        sample3 = struct.pack('<HH', 30, 930)  # t=3000ms, tt=93.0°C

        binary_data = header + sample1 + sample2 + sample3

        # Parse
        shot = parse_binary_shot(binary_data, "000002")

        # Verify
        assert shot.version == 5
        assert len(shot.phases) == 2
        assert shot.phases[0].sample_index == 0
        assert shot.phases[0].phase_number == 0
        assert shot.phases[0].phase_name == "Preinfusion"
        assert shot.phases[1].sample_index == 2
        assert shot.phases[1].phase_number == 1
        assert shot.phases[1].phase_name == "Extraction"

        # Check phase numbers in samples
        assert shot.samples[0].get('phase') == 0
        assert shot.samples[1].get('phase') == 0
        assert shot.samples[2].get('phase') == 1

    def test_parse_incomplete_shot(self):
        """Test parsing a shot file with incomplete samples."""
        magic = 0x544F4853
        version = 4
        reserved0 = 0
        header_size = 128
        sample_interval = 100
        reserved1 = 0
        fields_mask = 0b11  # T, TT (2 fields)
        sample_count = 10  # Claims 10 samples
        duration = 10000
        timestamp = 1640000000
        profile_id = b'incomplete\x00' + b'\x00' * 21
        profile_name = b'Incomplete\x00' + b'\x00' * 37
        weight = 0

        header = struct.pack(
            '<IB B H H H I I I I 32s 48s H',
            magic, version, reserved0, header_size,
            sample_interval, reserved1,
            fields_mask, sample_count, duration, timestamp,
            profile_id, profile_name, weight
        )
        header = header + b'\x00' * (128 - len(header))

        # Only provide 2 samples worth of data (but claims 10)
        sample1 = struct.pack('<HH', 10, 900)
        sample2 = struct.pack('<HH', 20, 920)

        binary_data = header + sample1 + sample2

        # Parse
        shot = parse_binary_shot(binary_data, "000003")

        # Should only parse the 2 samples that exist
        assert shot.sample_count == 2
        assert shot.incomplete == True
        assert len(shot.samples) == 2

    # ------------------------------------------------------------------
    # Shot log v6/v7 layout.
    # v6 widened the tick field from uint16 (sample index) to uint32
    # (elapsed ms); v7 added 'wp' (cumulative water pumped) as field bit 13.
    # Getting either wrong misaligns every subsequent field, so these tests
    # pin the record size as well as the values.
    # ------------------------------------------------------------------

    @staticmethod
    def _build_v5plus_header(version, fields_mask, sample_count,
                             sample_interval, duration):
        """Build a valid 512-byte v5+ header."""
        header = struct.pack(
            '<IBBHHHIIII',
            0x544F4853, version, 30 if version >= 7 else 26,
            512, sample_interval, 0,
            fields_mask, sample_count, duration, 1789000000,
        )
        header += struct.pack('<32s', b'v7test')
        header += struct.pack('<48s', b'V7 Profile')
        header += struct.pack('<H', 0)
        return header + b'\x00' * (512 - len(header))

    def test_parse_v7_water_pumped_and_millisecond_tick(self):
        """v7: 30-byte samples, absolute ms tick, and 'wp' decoded."""
        all_fields_mask = 0x3FFF  # bits 0..13
        samples = [
            struct.pack('<IHHHHhhhhHHHHH', 0, 925, 930, 0, 90,
                        0, 0, 0, 0, 0, 0, 0, 1, 0),
            struct.pack('<IHHHHhhhhHHHHH', 250, 925, 931, 0, 90,
                        120, 0, 110, 0, 0, 0, 100, 1, 55),
            struct.pack('<IHHHHhhhhHHHHH', 500, 925, 932, 0, 90,
                        121, 0, 118, 0, 360, 361, 101, 1, 110),
        ]
        data = (self._build_v5plus_header(7, all_fields_mask, 3, 250, 32394)
                + b''.join(samples))

        shot = parse_binary_shot(data, "000000")

        assert shot.version == 7
        assert shot.sample_count == 3
        assert shot.incomplete is False

        # All 14 fields decoded, including the v7 addition.
        assert set(shot.samples[0]) >= {
            't', 'tt', 'ct', 'tp', 'cp', 'fl', 'tf', 'pf',
            'vf', 'v', 'ev', 'pr', 'systemInfo', 'wp',
        }

        # Tick is elapsed milliseconds, not a sample index.
        assert [s['t'] for s in shot.samples] == [0, 250, 500]

        # Water pumped is 0.1 ml resolution.
        assert [s['wp'] for s in shot.samples] == [0.0, 5.5, 11.0]
        assert shot.samples[2]['tt'] == 92.5

    def test_parse_v5_tick_stays_sample_index(self):
        """v5 must keep the old 26-byte layout and derived tick."""
        v5_mask = 0x1FFF  # bits 0..12, no water pumped
        samples = [
            struct.pack('<HHHHHhhhhHHHH', i, 925, 930, 0, 90,
                        120, 0, 110, 0, 0, 0, 100, 1)
            for i in range(3)
        ]
        data = (self._build_v5plus_header(5, v5_mask, 3, 250, 750)
                + b''.join(samples))

        shot = parse_binary_shot(data, "v5test")

        assert shot.version == 5
        assert shot.sample_count == 3
        assert 'wp' not in shot.samples[0]
        # v5 stores a sample index; the parser multiplies by the interval.
        assert [s['t'] for s in shot.samples] == [0, 250, 500]

    def test_newer_layout_raises_instead_of_returning_garbage(self):
        """A file bigger than the declared layout must fail loudly.

        Silently misaligned samples are how the v6/v7 format bump went
        unnoticed, so the parser refuses rather than guessing.
        """
        import pytest

        all_fields_mask = 0x3FFF
        samples = [
            struct.pack('<IHHHHhhhhHHHHH', i * 250, 925, 930, 0, 90,
                        120, 0, 110, 0, 0, 0, 100, 1, 55)
            for i in range(3)
        ]
        data = (self._build_v5plus_header(7, all_fields_mask, 3, 250, 750)
                + b''.join(samples))

        # Re-declare the same body as a v5 file: 14 fields x 2 bytes predicts
        # a smaller file than the 30-byte records actually present.
        mislabelled = bytearray(data)
        struct.pack_into('<B', mislabelled, 4, 5)

        with pytest.raises(ValueError, match="layout mismatch"):
            parse_binary_shot(bytes(mislabelled), "mislabelled")
