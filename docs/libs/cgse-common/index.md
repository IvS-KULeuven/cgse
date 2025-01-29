# Common Code


This package `cgse-common` contains modules that are used by all other packages. 

| Module Name        | Description                                                                     |
|--------------------|---------------------------------------------------------------------------------|
| `egse.bits`        | convenience functions to work with bits, bytes and integers                     |
| `egse.calibration` | functions to handle conversions and apply correction                            |
| `egse.command`     | classes and functions to work with commands that operate hardware devices       |
| `egse.config`      | convenience functions to configure the system and find folders and files        |
| `egse.control`     | defines abstract classes and convenience functions for any control server       |
| `egse.decorators`  | a collection of useful decorator functions                                      |
| `egse.device`      | defines the generic interfaces to connect devices                               |
| `egse.env`         | functionality to work with and check your environment variables                 |
| `egse.exceptions`  | common Exceptions and Errors                                                    |
| `egse.hk`          | functions to retrieve and convert housekeping parameter values                  |
| `egse.metrics`     | functions to define and update metrics                                          |
| `egse.mixin`       | defines the mixin classes for dynamic commanding                                |
| `egse.monitoring`  | the monitoring application / function                                           |
| `egse.observer`    | the classic observer and observable                                             |
| `egse.obsid`       | functions to define and work with the OBSID                                     |
| `egse.persistence` | the persistence layer interface                                                 |
| `egse.plugin`      | functions to load plugins and settings from entry-points                        |
| `egse.process`     | functions and classes to work with processes and sub-processes                  |
| `egse.protocol`    | base class for communicating commands with the hardware or the control server   |
| `egse.proxy`       | base class for the Proxy objects for each device controller                     |
| `egse.reload`      | a slightly better approach to reloading modules and function                    |
| `egse.resource`    | convenience functions to use resources in your code                             |
| `egse.response`    | defines the classes to handle responses from the control servers                |
| `egse.services`    | provides the services to the control servers                                    |
| `egse.settings`    | provides functions to handle user and configuration settings                    |
| `egse.setup`       | defines the Setup, containing the complete configuration for a test             |
| `egse.state`       | classes and functions to handle state, e.g. the GlobalState                     |
| `egse.system`      | convenience functions that provide information on system specific functionality |
| `egse.version`     | functions to load specific version information                                  |
| `egse.zmq_ser`     | serialization function used in a ZeroMQ context                                 |
