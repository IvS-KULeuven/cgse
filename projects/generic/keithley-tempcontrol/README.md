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
daq6510_cs start-scan | stop-scan | get-latest | reset | clear-errors | status | stop
```

While a scan is running, only read-only queries, `stop-scan`, `reset` and `clear-errors` are accepted.

The `scan` section of the status separates the present condition from the record of past errors:

- `health` is `ok`, `degraded` while errors repeat, or `failed` when the scan ended because of an error. It clears by
  itself when the problem is gone (`failed` clears when a new scan is started). `consecutive_errors` counts the errors
  since the last successful poll.
- `last_error`, `last_error_at` and `error_count` keep the last error and the number of errors, also when the problem
  is gone. They are cleared with `clear-errors` or when a new scan is started.

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
- Between two scans, `ROUTe:SCAN:STATe?` reports `RUNNING` or `WAITING`. After a reconnect, the control server
  restarts the scan for any other state (e.g. `IDLE` after a power cycle).

## Reference Documents
 - Model DAQ6510 Data Acquisition and Multimeter System Reference Manual (DAQ6510-901-01 Rev. B / September 2019)
 - Model DAQ6510 Data Acquisition and Multimeter System User's Manual (DAQ6510-900-01 Rev. B / August 2019)
