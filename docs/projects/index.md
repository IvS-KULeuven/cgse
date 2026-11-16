# Projects

The projects are those packages that add functionality to the CGSE framework.

The projects live under the folder `projects`, and they are organised in _generic_ and _specific_ projects. Generic
projects do not have an implementation that is specific for one particular project, while, obviously, specific
projects have.

For a device driver, the `cgse` column is the `cgse <object>` command of its control server, which is also the
`cgse_object` of the device in the Setup, see [The Setup](../libs/cgse-common/setup.md).

## Generic packages

In `projects/generic`:

| Package                                   | Description                                                              | `cgse`                   |
|-------------------------------------------|--------------------------------------------------------------------------|--------------------------|
| [`cgse-tools`](cgse-tools.md)             | Tools for the CGSE                                                       |                          |
| [`cgse-tui`](cgse-tui.md)                 | Terminal user interface with the status of the core services and devices |                          |
| `aim-tti-awg`                             | Aim-TTi TGF4000 Arbitrary Wave Generator                                 | `tgf4000`                |
| `digilent`                                | Digilent MEASURpoint DT8874, temperature and voltage monitoring          | `dt8874`                 |
| `keithley-tempcontrol`                    | Keithley DAQ6510 data acquisition, temperature monitoring                | `daq6510`                |
| `kikusui-power-supply`                    | KIKUSUI PMX-A power supplies                                             | `pmx_a`                  |
| `lakeshore-tempcontrol`                   | LakeShore 336 temperature controller (prototype)                         | `lakeshore336`           |
| `rs-pro-power-supply`                     | RS PRO RS-D3305P power supply                                            | `rsd3305p`               |
| [`symetrie-hexapod`](symetrie-hexapod.md) | Symétrie hexapods PUNA, ZONDA and JORAN                                  | `puna`, `zonda`, `joran` |

## Project specific packages

PLATO, in `projects/plato`:

| Package      | Description                                    |
|--------------|------------------------------------------------|
| `plato-fits` | FITS persistence layer for the Storage Manager |
| `plato-hdf5` | HDF5 persistence layer for the Storage Manager |
| `plato-spw`  | SpaceWire implementation for the CGSE          |

ARIEL, in `projects/ariel`:

| Package          | Description                                             | `cgse`        |
|------------------|---------------------------------------------------------|---------------|
| `ariel-facility` | Housekeeping from the MySQL facility database for Ariel | `facility_hk` |
| `ariel-tcu`      | Telescope Control Unit (TCU) for Ariel                  | `tcu`         |

IvS (KU Leuven), in `projects/ivs`:

| Package | Description                                    | `cgse` |
|---------|------------------------------------------------|--------|
| `tvac`  | ThermalVac thermal vacuum chamber, over OPC UA | `tvac` |

The folder name is used above. Some packages are installed under another name: `aim_tti_awg`, `kikusui_power_supply`,
`rs_pro_power_supply` and `ivs_tvac`.
