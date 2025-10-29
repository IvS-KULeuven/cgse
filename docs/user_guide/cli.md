
# CLI Commands CGSE

The CGSE comes with a suite of CLI commands to start and stop services, get 
status reports and check the installation. It's actually a suite of `cgse` 
sub-commands that is extendable by external packages. This section will 
describe the commands that are available from the `cgse` packages.

## The `cgse` command

When you run the `cgse` command without arguments, you will see something 
like this.
![cli-cgse.png](../images/cli-cgse.png)
The _Options_ sections shows the global options to the CGSE command and allows you to activate auto-completion for all 
sub-commands.

The _Commands_ section lists the `cgse` commands that are not linked to a core service or a control server. 

The _Core Command_ section lists the sub-command for each of the core services, use `core` when you want to 
start/stop all core services in one go. The core services are:

- **reg** the service registry for all core services and control servers
- **not** the notification server that collects and published all events
- **log** the log server that collects and stores all log messages
- **cm** the configuration manager
- **sm** the storage manager
- **pm** the process manager

The _Device Command_ section lists the sub-commands for all device packages that have been installed and have a 
plugin for the `cgse` command. In the `cgse` package, the following devices are available:

- **DAQ6510** the Keithley Data Acquisition and Logging Multimeter
- **LakeShore336** the LakeShore Temperature Controller
- **puna**, **joran**, **zonda** the Symétrie positioning Hexapods

The _Example_ section lists devices that are purely there as examples on how to develop device drives and their 
plugins and how to use them in the framework.
