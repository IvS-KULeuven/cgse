# Testing the Software

We use the `pytest` package to unit test our modules and packages. The `pyproject.toml` files are configured for 
each package to perform the testing. This section will guide you through the steps to run the tests and also explain 
how we configured the tests and some guidelines we used.

## Running the unit test for each package separately

If you are working on a particular package and want to run its unit test, make sure you are in the root folder of 
that package, e.g. for the `cgse-common` package, do the following:

```shell
$ cd ~/github/cgse/libs/cgse-common/
$ uv sync
$ uv run pytest -v
================================================================ test session starts =================================================================
platform darwin -- Python 3.9.20, pytest-8.3.4, pluggy-1.5.0 -- /Users/rik/github/cgse/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /Users/rik/github/cgse/libs/cgse-common
configfile: pyproject.toml
plugins: cov-6.0.0, mock-3.14.0
collected 161 items

test_bits.py::test_clear_bit PASSED                                                                                                            [  0%]
test_bits.py::test_set_bit PASSED                                                                                                              [  1%]
test_bits.py::test_toggle_bit PASSED                                                                                                           [  1%]
test_bits.py::test_beautify_binary PASSED                                                                                                      [  2%]
test_bits.py::test_set_bits PASSED                                                                                                             [  3%]
test_bits.py::test_alternative_set_bits PASSED                                                                                                 [  3%]
test_bits.py::test_clear_bits PASSED                                                                                                           [  4%]
test_bits.py::test_crc_calc PASSED                                                                                                             [  4%]
test_bits.py::test_humanize_bytes PASSED                                                                                                       [  5%]
test_bits.py::test_s16 PASSED                                                                                                                  [  6%]
test_bits.py::test_s32 PASSED                                                                                                                  [  6%]
test_command.py::test_dry_run PASSED                                                                                                           [  7%]
test_command.py::test_command_class PASSED                                                                                                     [  8%]
test_command.py::test_return_code_of_execute PASSED                                                                                            [  8%]
...
```

## Running the unit tests of all packages

Before releasing the software, we should run all the unit tests of all the packages in the monorepo and have green 
light 🟢. Running these unit tests is as simple as for the individual packages. You will need to be in the root folder 
of the monorepo and sync your virtual environment for all the packages in the workspace.

```shell
$ cd ~/gitbug/cgse
$ uv sync --all-packages
$ uv run pytest -v
```
