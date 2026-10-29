# Keithley Temperature Control

## Latest release

- PyPI: https://pypi.org/project/keithley-tempcontrol/
- GitHub releases: https://github.com/IvS-KULeuven/cgse/releases
- Latest release notes: https://github.com/IvS-KULeuven/cgse/releases/latest
- Changelog: https://github.com/IvS-KULeuven/cgse/blob/main/CHANGELOG.md

# Implemented Devices

- DAQ6510

## DAQ6510 control server

The DAQ6510 control server (`daq6510_cs`) is asynchronous and owns the connection to the device. It configures a
background scan from the `gse.DAQ6510` section of the Setup, polls the reading buffer for new scans and keeps the
latest readings in memory. Readings are stored with the Storage Manager and sent to the Metrics Hub.

```
daq6510_cs start [--setup-file SETUP.yaml] [--auto-scan]
daq6510_cs start-scan | stop-scan | get-latest | reset | status | stop
```

While a scan is running, only read-only queries, `stop-scan` and `reset` are accepted.

Without hardware, start the simulator with `daq6510_sim start` and set `HOSTNAME: localhost` for the
`Keithley DAQ6510` settings.

### To verify on hardware

The simulator and the unit tests use a model of the DAQ6510. These assumptions have not been checked against the
real device yet:

- The format of the `SEConds`, `FRACtional` and `UNIT` elements returned by `TRACe:DATA?`.
- `SYSTem:TIME` sets UTC, so the `SEConds` timestamps are UTC.
- `TRACe:ACTual:END?` counts the readings of a running scan, one by one, from index 1 after `TRACe:POINts`.
- `ABORt` followed by `TRACe:CLEar` and `INITiate` restarts the scan with the same configuration (buffer rollover).
- A sensor configuration from the Setup produces no errors in `SYSTem:ERRor?`.

## Reference Documents
 - Model DAQ6510 Data Acquisition and Multimeter System Reference Manual (DAQ6510-901-01 Rev. B / September 2019)
 - Model DAQ6510 Data Acquisition and Multimeter System User's Manual (DAQ6510-900-01 Rev. B / August 2019)
