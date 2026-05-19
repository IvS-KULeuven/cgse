"""Unit tests for ThermalVac module initialisation."""

from egse.ivs.thermalvac import tvac_state_to_string


class TestTvacStateToString:
    """Tests for tvac_state_to_string function."""

    def test_unknown_state_zero(self):
        """Test state 0 returns Unknown."""
        assert tvac_state_to_string(0) == "Unknown"

    def test_idle_state_one(self):
        """Test state 1 returns Idle."""
        assert tvac_state_to_string(1) == "Idle"

    def test_pumping_fore_vacuum_state_two(self):
        """Test state 2 returns Pumping fore vacuum."""
        assert tvac_state_to_string(2) == "Pumping fore vacuum"

    def test_waiting_for_pressure_stabilization_state_three(self):
        """Test state 3 returns Waiting for pressure to stabilize."""
        assert tvac_state_to_string(3) == "Waiting for pressure to stabilize"

    def test_pumping_at_high_vacuum_state_four(self):
        """Test state 4 returns Pumping at high vacuum."""
        assert tvac_state_to_string(4) == "Pumping at high vacuum"

    def test_starting_turbo_pump_state_five(self):
        """Test state 5 returns Starting turbo pump."""
        assert tvac_state_to_string(5) == "Starting turbo pump"

    def test_stopping_pumps_state_six(self):
        """Test state 6 returns Stopping pumps."""
        assert tvac_state_to_string(6) == "Stopping pumps"

    def test_turbo_pump_decelerating_state_seven(self):
        """Test state 7 returns Turbo pump decelerating."""
        assert tvac_state_to_string(7) == "Turbo pump decelerating"

    def test_cooling_state_eight(self):
        """Test state 8 returns Cooling."""
        assert tvac_state_to_string(8) == "Cooling"

    def test_heating_state_nine(self):
        """Test state 9 returns Heating."""
        assert tvac_state_to_string(9) == "Heating"

    def test_pressure_rising_state_ten(self):
        """Test state 10 returns Pressure rising (too high for turbo)."""
        assert tvac_state_to_string(10) == "Pressure rising (too high for turbo)"

    def test_negative_state_returns_invalid(self):
        """Test negative state returns Invalid state."""
        assert tvac_state_to_string(-1) == "Invalid state"

    def test_state_beyond_maximum_returns_invalid(self):
        """Test state beyond maximum returns Invalid state."""
        assert tvac_state_to_string(11) == "Invalid state"

    def test_large_positive_state_returns_invalid(self):
        """Test large positive state returns Invalid state."""
        assert tvac_state_to_string(999) == "Invalid state"

    def test_state_with_all_valid_values(self):
        """Test all valid states map to correct descriptions."""
        expected_states = {
            0: "Unknown",
            1: "Idle",
            2: "Pumping fore vacuum",
            3: "Waiting for pressure to stabilize",
            4: "Pumping at high vacuum",
            5: "Starting turbo pump",
            6: "Stopping pumps",
            7: "Turbo pump decelerating",
            8: "Cooling",
            9: "Heating",
            10: "Pressure rising (too high for turbo)",
        }

        for state, expected_description in expected_states.items():
            assert tvac_state_to_string(state) == expected_description


class TestModuleInitialization:
    """Tests for module-level settings initialization."""

    def test_tvac_state_to_string_returns_string(self):
        """Test tvac_state_to_string always returns a string."""
        for state in range(-5, 15):
            result = tvac_state_to_string(state)
            assert isinstance(result, str)
