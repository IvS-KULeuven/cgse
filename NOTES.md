# The monorepo structure

Currently, the structure starts with two folders in the root, i.e. `libs` and `projects`. Where _libs_ contains library type packages like common modules, small generic gui functions, reference frames, ... and _projects_ contain packages that build upon these libraries. 

There is one package that I think doesn't fit into this picture, that is `cgse-core`. This is not a library, but a – collection of – service(s). So, we might want to add a third top-level folder `services` but I also fear that this again more complicates the monorepo.

# Package Structure

We try to keep the package structure as standard as possible and consistent over the whole monorepo. The structure currently is as follows (example from case-common):

```
├── README.md
├── dist
│   ├── cgse_common-2023.1.4-py3-none-any.whl
│   └── cgse_common-2023.1.4.tar.gz
├── pyproject.toml
├── src/
│   └── egse/  # namespace
│       ├── modules (*.py)
│       └── <sub-packages>/
└── tests/
    ├── data
    └── pytest modules (test_*.py)
```


# Package versions

Should all packages in the monorepo have the same version?

# Use of Poetry

I have now Poetry configurations for all `libs` in this monorepo. So, how do we use Poetry in this project?

First thing to understand,  if you are installing the different packages in this repo from PyPI there is no need to use Poetry. The package will be installed in your current virtual environment.

The following command starts a new sub-shell and activates the virtual environment: 
```
$ poetry shell
```

If you do not want to start a new shell, but just want to execute a command in the virtual environment, use the `poetry run` command, e.g.
```
$ poetry run pytest tests/test_bits.py
```
Or
```
$ poetry run python -m egse.monitoring localhost 6001
```

# Build and Publish

Building a source distribution and a wheel for your project is as easy as running the following command:
```
$ poetry build
Building cgse-common (2023.1.5)
  - Building sdist
  - Built cgse_common-2023.1.5.tar.gz
  - Building wheel
  - Built cgse_common-2023.1.5-py3-none-any.whl
```
Make sure you have updated/bumped the version number in the `pyproject.toml`. Publishing your package on PyPI needs some more preparation, since you need to prepare a token that allows you to upload your project to PyPI. Publishing itself is a peace of cake when the credentials have been configured correctly. Poetry will also automatically take the latest version to publish.
```
$ poetry publish
Publishing cgse-common (2023.1.5) to PyPI
 - Uploading cgse_common-2023.1.5-py3-none-any.whl 100%
 - Uploading cgse_common-2023.1.5.tar.gz 100%
```



# Questions

What is the meaning of the common egse root folder in this monorepo and when the packages are installed through PyPI?

* do we still need `get_common_egse_root()`
* what is the Projects root directory?
