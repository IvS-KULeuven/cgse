
# Installation Guide for Developers

# GitHub

Before starting, make sure you have a _fork_ of the `cgse` repository. Through this fork (which 
resides on the GitHub  server) you will create pull requests. Install a clone of your fork on 
your local machine or laptop.

![img.png](../images/github-fork-clone.png#only-light)
![img.png](../images/github-fork-clone-dark.png#only-dark)


So, when you have created a fork in your GitHub account, clone the repository on your local 
machine.  For the purpose of this guide we will clone the repo in the `~/github/cgse` folder. 
The following commands will create the required folders and clone the repo.

```shell
$ mkdir -p ~/github
$ cd ~/github
$ git clone git@github.com:IvS-KULeuven/cgse.git
$ cd ~/github/cgse
```

Now you will have to create a virtual environment and populated it with all the dependencies. 

!!! note

    The following three commands will get you going quickly:
    ```
    $ uv venv --python 3.9.20
    $ uv sync --all-packages
    $ uv run cgse
    
    Usage: cgse [OPTIONS] COMMAND [ARGS]...

    The main cgse command to inspect, configure, monitor the core services and device control 
    servers.
    
    ╭─ Options ──────────────────────────────────────────────────────────────────────────────────────────────────────╮
    │ --install-completion          Install completion for the current shell.                                        │
    │ --show-completion             Show completion for the current shell, to copy it or customize the installation. │
    │ --help                        Show this message and exit.                                                      │
    ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
    ╭─ Commands ─────────────────────────────────────────────────────────────────────────────────────────────────────╮
    │ version   Prints the version of the cgse-core and other registered packages.                                   │
    │ top       A top-like interface for core services and device control servers.                                   │
    │ clock     Showcase for running an in-line Textual App.                                                         │
    │ init      Initialize your project.                                                                             │
    │ show      Show information about settings, environment, setup, ...                                             │
    │ check     Check installation, settings, required files, etc.                                                   │
    │ dev-x     device-x is an imaginary device that serves as an example                                            │
    │ core      handle core services: start, stop, status                                                            │
    │ puna      PUNA Positioning Hexapod, Symétrie                                                                   │
    │ daq6510   DAQ6510 Data Acquisition Unit, Keithley, temperature monitoring                                      │
    ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯

    ```
