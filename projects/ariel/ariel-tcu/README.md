# Telescope Control Unit (TCU)

## Reference Document

- RD01: TCU User Manual (ARIEL-IEEC-PL-TN-002), v1.2
- RD02: ARIEL TCU Data Handling (ARIEL-IEEC-PL-TN-007), v1.0
- RD03: TCU code provided by Vladimiro Noce (priv. comm.)
- RD04: ARIEL Telescope Control Unit Design Description Document (ARIEL-IEEC-PL-DD-001), v1.10
- RD05: ARIEL TCU FW Architecture Design (ARIEL-IEEC-PL-DD-002), v1.5


## Boards

- Control & Thermal Sensing (CTS) -> thermal monitoring
- Power Supply Unit (PSU)
- M2MD -> drives M2M

## Modes

- OFF
- I/F SELECT
- IDLE (0x0000): internal HK active
- BASE (0x0001): internal HK + temperature measurements active
- CALIBRATION (0x0003): internal HK + temperature measurements active + M2MD
