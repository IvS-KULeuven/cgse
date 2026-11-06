# The Setup

## Device drivers in the Setup

The device drivers that are used in a project are described in the Setup, usually under `gse`. A node describes a
device driver when it has a `cgse_object`, the name of its `cgse <object>` command, the command that starts, stops
and shows the status of its control server:

```yaml
gse:
    DAQ6510:
        device_name: Keithley DAQ6510
        cgse_object: daq6510
        channels: (@101:103)
    hexapod:
        device_name: PUNA Hexapod
        cgse_object: puna
        device_id: PUNA_01
```

| Key           | Required | Meaning                                                                               |
|---------------|----------|---------------------------------------------------------------------------------------|
| `cgse_object` | yes      | the `cgse <object>` command of the device, e.g. `daq6510`, `puna`, `tvac`             |
| `device_name` | no       | the name shown for the device, by default the key of the node                         |
| `device_id`   | no       | the device identifier, when there are several devices of the same type               |

The other entries of the node are the configuration of the device, they are not searched for further devices. The
CGSE TUI shows every device driver of the Setup that the configuration manager has loaded: a running one as its
service in the registry (matched on `cgse_object` and, when given, `device_id`), one that doesn't run as a dimmed row
that can be started with `cgse <object> start [<device_id>]`.

Older Setups describe a device with `device` (a proxy class) and `device_name`; the process manager uses these. Add a
`cgse_object` to show them in the TUI.
