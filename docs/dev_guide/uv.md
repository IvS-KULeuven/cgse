
# Working with `uv`

`uv` is an extremely fast Python package and project manager, written in Rust. We will use `uv` as the single tool that replaces `pip`, `virtualenv`, `pyenv`, and more. The main tasks for which we will use `uv` are:

- run and install Python versions
- installing and managing a virtual environment
- build all the packages in the workspace or monorepo
- publish all the packages to PyPI
- run scripts and apps

## Installing `uv`

On macOS and Linux you can install `uv` using `curl`:

```shell
$ curl -LsSf https://astral.sh/uv/install.sh | sh
```

If you need more specific information on installing and upgrading `uv`, please refer to the [official documentation](https://docs.astral.sh/uv/getting-started/installation/).


## Installing a Python version

The CGSE is guaranteed to work with Python 3.9.x. We will gradually include higher versions of Python, but currently 
these have not been tested. So, we will for the moment stick with Python 3.9.20. Install this version as follows:

```shell
$ uv python install 3.9.20
```

!!! note "`pyenv`"

    When using `pyenv` to manage your Python versions, make sure you also have the same Python version installed 
    with `pyenv` and `uv`. Otherwise you will run into the following error. This is a known issue with `uv`.

    ```
    pyenv: version `3.9.20' is not installed (set by /Users/rik/github/cgse/libs/cgse-common/.python-version)
    ```

You can check which Python versions are installed already on your system:

=== "Command"

    ```bash
    $ uv python list --only-installed
    ```

=== "Output"

    ```
    cpython-3.12.8-macos-aarch64-none     /Users/rik/Library/Application Support/uv/python/cpython-3.12.8-macos-aarch64-none/bin/python3.12
    cpython-3.10.16-macos-aarch64-none    /Users/rik/Library/Application Support/uv/python/cpython-3.10.16-macos-aarch64-none/bin/python3.10
    cpython-3.9.21-macos-aarch64-none     /Users/rik/Library/Application Support/uv/python/cpython-3.9.21-macos-aarch64-none/bin/python3.9
    cpython-3.9.20-macos-aarch64-none     /Users/rik/Library/Application Support/uv/python/cpython-3.9.20-macos-aarch64-none/bin/python3.9
    cpython-3.9.6-macos-aarch64-none      /Library/Developer/CommandLineTools/usr/bin/python3 -> ../../Library/Frameworks/Python3.framework/Versions/3.9/bin/python3
    cpython-3.8.17-macos-aarch64-none     /Users/rik/Library/Application Support/uv/python/cpython-3.8.17-macos-aarch64-none/bin/python3.8
    ```


## Create a virtual environment

!!! info inline end "Pin a Python version"

    You can pin a python version with the command:

    ```
    $ uv python pin 3.9.20
    ```

    `uv` will search for a pinned version in the parent folders up to the root folder or your home directory.


You can create a virtual environment with `uv` for the specific Python version as follows. The '`--python`' is optional 
and `uv` will use the default (pinned) Python version when creating a `venv` without this option. When creating a 
virtual environment make sure you are in the package root, e.g. `~/github/cgse/libs/cgse-common`.

```shell
$ cd ~/github/cgse/libs/cgse-common
$ uv venv --python 3.9.20
```

Assuming you are in the package root where you created the virtual environment, you can now install its dependencies 
with `pip install` as follows:

```shell
$ uv pip install -r pyproject.toml
```

To install the current project as an editable package:

```shell
$ uv pip install -e .
```

!!! note 

    If you don't want to use the `uv` commands, you can activate the virtual environment and use the original `pip` 
    and `python` commands as you are used to.

    ```
    $ source .venv/bin/activate
    ```

!!! info

    In a workspace, maintaining a virtual environment per package might be a hassle and most of the time that is not 
    needed. A good approach is to always use the virtual environment at the workspace root. This `venv` which will be 
    automatically created if you run a command or if you use `uv sync` in the package folder. With `uv sync` you can 
    make sure the virtual environment is up-to-date and contains only those dependencies that are required for the 
    package you are in. So, each time you switch to another package and want to run a comand or a test for that 
    package, use 

    ```
    $ uv sync
    ```

## Building and publishing all packages

We have chosen for one and the same version number for all packages in the `cgse` monorepo. That means that whenever 
we make a change to one of the packages and want to release that change, all packages shall be rebuild and published.

!!! inline end warning

    When working in a workspace, keep in mind that the commands `uv run` and `uv sync` by default work on the 
    workspace root. That means that when you run the `uv run pip install <package>` command, the `.venv` at the 
    workspace root will be updated or created if it didn't exist. Similar for the `uv sync` command, there is only 
    one `uv.lock` file at the root of the workspace.  

Fortunately, with `uv`, that is done in a few commands.

When you are in the monorepo root folder, you can build all packages at once. They will be placed in the `dist` folder 
of the root package. Before building, make sure you update the version in the `pyproject.toml` of the root package 
and then bump the versions. Before building, clean up the `dist` folder, then you can do a default `uv publish` afterwards.

```shell
$ cd <monorepo root>
$ uv run bump.py
$ rm -r dist
$ uv build --all-packages
```

Publish all packages in the root dist folder to PyPI. The UV_PUBLISH_TOKEN can be defined in a (read protected) ~/.
setenv.bash file:

```shell
$ uv publish --token $UV_PUBLISH_TOKEN
```

The above command will publish all package to PyPI. If you don't want the token to be in a shell variable, you can 
omit the `--token` in the command above. You will then be asked for a username, use `__token__` as the username and 
then provide the token as a password.
