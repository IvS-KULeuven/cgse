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
Python 3.9, 3.10, and 3.11.

The following command will run the unit tests and save the stdout and stderr in the file `nox.
out.txt`.

```text
$ nox > nox.out.txt 2>&1
```
