"""Tiny thermostat controller used as a reqcov example."""
import math

MAX_TEMP = 35.0
SETPOINT_MIN, SETPOINT_MAX = 5.0, 30.0
HYST = 0.25


class Controller:
    def __init__(self, setpoint=20.0):
        self.setpoint = setpoint
        self.heater = False
        self.alarm = None

    # @implements SRS-12
    def set_setpoint(self, value):
        if SETPOINT_MIN <= value <= SETPOINT_MAX:
            self.setpoint = value
            return True
        return False

    # @implements SRS-10, SRS-11, SRS-13
    def update(self, temp):
        if temp is None or (isinstance(temp, float) and math.isnan(temp)):
            self.heater, self.alarm = False, "sensor"
            return self.heater
        if temp >= MAX_TEMP:
            self.heater, self.alarm = False, "overtemp"
            return self.heater
        self.alarm = None
        if temp < self.setpoint - HYST:
            self.heater = True
        elif temp > self.setpoint + HYST:
            self.heater = False
        return self.heater
