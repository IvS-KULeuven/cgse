# Testing with `nox`

Ultimately, we want our software to work on as many Python environments as possible. So, we 
adopted [`nox`](https://nox.thea.codes/en/stable/) to run the unit tests under different Python 
versions.

If you don't have `nox` installed on your system, you can install it globally as a uv tool:

```shell
$ uv tool install nox
```

After this you can run `nox` from the package root. We have provided a `noxfile.py` for the 
`cgse-common`package. The `cgse-common` package currently runs all unit tests without errors for 
Python 3.9, 3.10, 3.11, 3.12, and 3.13.

The following command will run the default sessions (`uv_tests`). You can 
optionally save the output of stdout and stderr (whiich can be substantial) 

```text
$ nox
```
or
```text
$ nox > nox.out.txt 2>&1
```
You can restrict your tests with commandline parameters. The following 
example will only execute the default sessions in a Pytho 3.11 environment 
and will only run the test that matches `test_async_control`.

```text
$ nox --python 3.11 -- -k test_async_control
```
