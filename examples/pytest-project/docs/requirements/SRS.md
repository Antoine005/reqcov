# Software requirements — Thermostat controller

## SRS-10 — Hysteresis control
The controller shall turn the heater on when temperature < setpoint − 0.25 °C and off when temperature > setpoint + 0.25 °C.
Parent: SYS-1
Verification: test

## SRS-11 — Over-temperature cut-off
The controller shall force the heater off and raise an alarm when temperature ≥ 35.0 °C, regardless of setpoint.
Parent: SYS-2
Verification: test
Tags: safety

## SRS-12 — Setpoint validation
The controller shall reject setpoints outside [5.0, 30.0] °C and keep the previous value.
Parent: SYS-3
Verification: test

## SRS-13 — Sensor fault handling
If the sensor returns NaN, the controller shall turn the heater off and raise a sensor alarm.
Parent: SYS-2
Verification: test

## SRS-14 — Logging format
Every state change shall be logged as `timestamp;temp;setpoint;heater`.
Verification: inspection
