import math
import pytest
from thermostat import Controller


@pytest.mark.req("SRS-10")
def test_hysteresis_turns_on_below_band():
    c = Controller(20.0)
    assert c.update(19.0) is True


@pytest.mark.req("SRS-10")
def test_hysteresis_turns_off_above_band():
    c = Controller(20.0)
    c.update(19.0)
    assert c.update(20.5) is False


# @verifies SRS-11, SYS-2
def test_overtemp_cutoff():
    c = Controller(30.0)
    c.update(25.0)
    assert c.update(35.0) is False
    assert c.alarm == "overtemp"


@pytest.mark.req("SRS-12", "SYS-3")
@pytest.mark.parametrize("value,ok", [(5.0, True), (30.0, True), (4.9, False), (30.1, False)])
def test_setpoint_validation(value, ok):
    c = Controller(20.0)
    assert c.set_setpoint(value) is ok


def test_default_setpoint():
    # deliberately not linked to any requirement -> reported as orphan
    assert Controller().setpoint == 20.0
