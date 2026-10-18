"""Tests for profile Pydantic models."""

import pytest
from pydantic import ValidationError
from gaggimate_mcp.models.profile import (
    PumpSettings,
    TransitionSettings,
    TargetCondition,
    PhaseData,
    ProfileData,
    Profile,
)


class TestPumpSettings:
    """Test PumpSettings model."""

    def test_pump_settings_pressure(self):
        """Test pump settings with pressure target."""
        pump = PumpSettings(
            target="pressure",
            pressure=9.0,
            flow=0.0
        )
        assert pump.target == "pressure"
        assert pump.pressure == 9.0
        assert pump.flow == 0.0

    def test_pump_settings_flow(self):
        """Test pump settings with flow target."""
        pump = PumpSettings(
            target="flow",
            pressure=0.0,
            flow=2.5
        )
        assert pump.target == "flow"
        assert pump.flow == 2.5

    def test_pump_pressure_max_limit(self):
        """Test pressure is clamped to max 12 bar."""
        with pytest.raises(ValidationError):
            PumpSettings(target="pressure", pressure=15.0, flow=0.0)

    def test_pump_pressure_min_limit(self):
        """Test pressure cannot be negative."""
        with pytest.raises(ValidationError):
            PumpSettings(target="pressure", pressure=-1.0, flow=0.0)

    def test_pump_invalid_target(self):
        """Test invalid target type raises error."""
        with pytest.raises(ValidationError):
            PumpSettings(target="invalid", pressure=9.0, flow=0.0)


class TestTransitionSettings:
    """Test TransitionSettings model."""

    def test_transition_linear(self):
        """Test linear transition."""
        transition = TransitionSettings(
            type="linear",
            duration=2.0
        )
        assert transition.type == "linear"
        assert transition.duration == 2.0

    def test_transition_ease_out(self):
        """Test ease-out transition."""
        transition = TransitionSettings(type="ease-out", duration=3.0)
        assert transition.type == "ease-out"

    def test_transition_instant(self):
        """Test instant transition."""
        transition = TransitionSettings(type="instant", duration=0.0)
        assert transition.type == "instant"

    def test_transition_invalid_type(self):
        """Test invalid transition type raises error."""
        with pytest.raises(ValidationError):
            TransitionSettings(type="invalid", duration=2.0)

    def test_transition_negative_duration(self):
        """Test negative duration raises error."""
        with pytest.raises(ValidationError):
            TransitionSettings(type="linear", duration=-1.0)


class TestTargetCondition:
    """Test TargetCondition model."""

    def test_target_condition_pressure(self):
        """Test pressure target condition."""
        target = TargetCondition(
            type="pressure",
            operator="gte",
            value=9.0
        )
        assert target.type == "pressure"
        assert target.operator == "gte"
        assert target.value == 9.0

    def test_target_condition_volumetric(self):
        """Test volumetric target condition."""
        target = TargetCondition(
            type="volumetric",
            operator="gte",
            value=36.0
        )
        assert target.type == "volumetric"

    def test_target_condition_flow(self):
        """Test flow target condition."""
        target = TargetCondition(
            type="flow",
            operator="lte",
            value=1.5
        )
        assert target.type == "flow"
        assert target.operator == "lte"

    def test_target_invalid_type(self):
        """Test invalid target type raises error."""
        with pytest.raises(ValidationError):
            TargetCondition(type="invalid", operator="gte", value=10.0)

    def test_target_invalid_operator(self):
        """Test invalid operator raises error."""
        with pytest.raises(ValidationError):
            TargetCondition(type="pressure", operator="invalid", value=10.0)


class TestPhaseData:
    """Test PhaseData model."""

    def test_phase_preinfusion(self):
        """Test preinfusion phase."""
        phase = PhaseData(
            name="Preinfusion",
            phase="preinfusion",
            duration=8.0,
            pump=PumpSettings(target="pressure", pressure=2.0, flow=0.0),
            transition=TransitionSettings(type="linear", duration=2.0)
        )
        assert phase.name == "Preinfusion"
        assert phase.phase == "preinfusion"
        assert phase.duration == 8.0
        assert phase.pump.pressure == 2.0

    def test_phase_brew(self):
        """Test brew phase."""
        phase = PhaseData(
            name="Extraction",
            phase="brew",
            duration=30.0,
            pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
        )
        assert phase.phase == "brew"

    def test_phase_with_temperature(self):
        """Test phase with specific temperature."""
        phase = PhaseData(
            name="Extraction",
            phase="brew",
            duration=25.0,
            temperature=93.0,
            pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
        )
        assert phase.temperature == 93.0

    def test_phase_with_targets(self):
        """Test phase with stop conditions."""
        phase = PhaseData(
            name="Extraction",
            phase="brew",
            duration=60.0,
            pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0),
            targets=[
                TargetCondition(type="volumetric", operator="gte", value=36.0)
            ]
        )
        assert len(phase.targets) == 1
        assert phase.targets[0].type == "volumetric"

    def test_phase_invalid_type(self):
        """Test invalid phase type raises error."""
        with pytest.raises(ValidationError):
            PhaseData(
                name="Invalid",
                phase="invalid",
                duration=10.0,
                pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
            )

    def test_phase_zero_duration(self):
        """Test zero duration raises error."""
        with pytest.raises(ValidationError):
            PhaseData(
                name="Test",
                phase="brew",
                duration=0.0,
                pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
            )


class TestProfileData:
    """Test ProfileData model."""

    def test_profile_data_minimal(self):
        """Test profile data with minimal fields."""
        profile = ProfileData(
            name="Test Profile",
            description="Test description",
            temperature=93.0,
            phases=[
                PhaseData(
                    name="Extraction",
                    phase="brew",
                    duration=25.0,
                    pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                )
            ]
        )
        assert profile.name == "Test Profile"
        assert profile.temperature == 93.0
        assert len(profile.phases) == 1

    def test_profile_temperature_validation_max(self):
        """Test temperature max limit (96°C)."""
        with pytest.raises(ValidationError):
            ProfileData(
                name="Test",
                description="Test",
                temperature=100.0,
                phases=[
                    PhaseData(
                        name="Extraction",
                        phase="brew",
                        duration=25.0,
                        pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                    )
                ]
            )

    def test_profile_temperature_validation_min(self):
        """Test temperature min limit (60°C)."""
        with pytest.raises(ValidationError):
            ProfileData(
                name="Test",
                description="Test",
                temperature=50.0,
                phases=[
                    PhaseData(
                        name="Extraction",
                        phase="brew",
                        duration=25.0,
                        pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                    )
                ]
            )

    def test_profile_multiple_phases(self):
        """Test profile with multiple phases."""
        profile = ProfileData(
            name="Complex Profile",
            description="Multi-phase extraction",
            temperature=92.0,
            phases=[
                PhaseData(
                    name="Preinfusion",
                    phase="preinfusion",
                    duration=8.0,
                    pump=PumpSettings(target="pressure", pressure=2.0, flow=0.0)
                ),
                PhaseData(
                    name="Ramp",
                    phase="brew",
                    duration=5.0,
                    pump=PumpSettings(target="pressure", pressure=6.0, flow=0.0)
                ),
                PhaseData(
                    name="Extraction",
                    phase="brew",
                    duration=20.0,
                    pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                )
            ]
        )
        assert len(profile.phases) == 3

    def test_profile_no_phases(self):
        """Test profile must have at least one phase."""
        with pytest.raises(ValidationError):
            ProfileData(
                name="Test",
                description="Test",
                temperature=93.0,
                phases=[]
            )

    def test_profile_too_many_phases(self):
        """Test profile cannot have more than 10 phases."""
        phases = [
            PhaseData(
                name=f"Phase {i}",
                phase="brew",
                duration=5.0,
                pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
            )
            for i in range(11)
        ]
        with pytest.raises(ValidationError):
            ProfileData(
                name="Test",
                description="Test",
                temperature=93.0,
                phases=phases
            )


class TestProfile:
    """Test complete Profile model."""

    def test_profile_without_id(self, monkeypatch):
        """Test profile creation with an explicitly enabled legacy marker."""
        monkeypatch.setenv('GAGGIMATE_AI_PROFILE_SUFFIX', ' [AI]')
        profile = Profile(
            label="Test Profile [AI]",
            type="pro",
            description="Test profile",
            temperature=93.0,
            phases=[
                PhaseData(
                    name="Extraction",
                    phase="brew",
                    duration=25.0,
                    pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                )
            ]
        )
        assert profile.id is None
        assert profile.label == "Test Profile [AI]"
        assert profile.agent_created is True  # Auto-detected from label

    def test_profile_with_id(self):
        """Test profile with ID (existing profile)."""
        profile = Profile(
            id="profile-123",
            label="Existing [AI]",
            type="pro",
            description="Test",
            temperature=93.0,
            phases=[
                PhaseData(
                    name="Extraction",
                    phase="brew",
                    duration=25.0,
                    pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                )
            ]
        )
        assert profile.id == "profile-123"

    def test_profile_agent_created_detection(self, monkeypatch):
        """Test detection when a nonempty suffix is explicitly configured."""
        monkeypatch.setenv('GAGGIMATE_AI_PROFILE_SUFFIX', ' [AI]')
        agent_profile = Profile(
            label="TestBean [AI]",
            type="pro",
            description="Test",
            temperature=93.0,
            phases=[
                PhaseData(
                    name="Extraction",
                    phase="brew",
                    duration=25.0,
                    pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                )
            ]
        )
        assert agent_profile.agent_created is True

        user_profile = Profile(
            label="My Profile",
            type="pro",
            description="Test",
            temperature=93.0,
            phases=[
                PhaseData(
                    name="Extraction",
                    phase="brew",
                    duration=25.0,
                    pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                )
            ]
        )
        assert user_profile.agent_created is False

    def test_profile_json_serialization(self):
        """Test profile can be serialized to JSON."""
        profile = Profile(
            label="Test [AI]",
            type="pro",
            description="Test",
            temperature=93.0,
            phases=[
                PhaseData(
                    name="Extraction",
                    phase="brew",
                    duration=25.0,
                    pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                )
            ]
        )
        json_data = profile.model_dump()
        assert json_data["label"] == "Test [AI]"
        assert json_data["temperature"] == 93.0
        assert len(json_data["phases"]) == 1

    def test_profile_defaults(self):
        """Test profile default values."""
        profile = Profile(
            label="Test",
            type="pro",
            description="Test",
            temperature=93.0,
            phases=[
                PhaseData(
                    name="Extraction",
                    phase="brew",
                    duration=25.0,
                    pump=PumpSettings(target="pressure", pressure=9.0, flow=0.0)
                )
            ]
        )
        assert profile.favorite is False
        assert profile.selected is False
        assert profile.utility is False
