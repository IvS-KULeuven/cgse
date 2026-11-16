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
| `device_id`   | no       | the instance of the device, when there are several devices of the same type           |

The `device_id` is the argument of `cgse <object> start|stop|status <device_id>`, and the control server registers it
in the service registry, e.g. `PUNA_01`. A single device, whose `cgse <object> start` takes no device identifier
(e.g. `dt8874`, `daq6510`, `tvac`), has no `device_id`: its control server registers none, and a `device_id` in the
Setup would never match it.

```yaml
gse:
    dt8874:
        device_name: Digilent DT8874
        cgse_object: dt8874        # no device_id: there is one DT8874
```

The other entries of the node are the configuration of the device, they are not searched for further devices.

The CGSE TUI and the process manager GUI show every device driver of the Setup that the configuration manager has
loaded. A device runs when a service is registered with the same `cgse_object` and, when given, the same `device_id`;
the registry service type is not used. They start and stop it with `cgse <object> start|stop [<device_id>]`. When a
service of the same `cgse_object` runs with another `device_id`, both log a warning that says what to change in the
Setup. The TUI also warns when a Setup device without `device_id` matches several running services, and when there is
no `cgse <object>` command for a device that doesn't run.

Older Setups describe a device with `device` (a proxy class), `device_name` and `device_id`. The process manager still
uses these when the node has no `cgse_object`: it looks for the service type `device_id` (in upper case) in the
registry, and passes the first of the `device_args` to the `cgse` command. Add a `cgse_object` to use the device
driver form, then `device` and `device_args` are not needed by the process manager or the TUI.
