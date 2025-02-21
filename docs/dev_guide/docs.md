# Building the documentation

- Make sure you are in a virtual environment with Python 3.9+ or use the `uv` commands as
  demonstrated below.
- Run the `mkdocs serve` from the project root older
- Create new pages by adding folder and Markdown files inside `docs/*`

## Set up your environment

The `pyproject.toml` file of the `cgse` root contains additional dependencies for running the
`mkdocs` commands. When working on the documentation, make sure you have installed the 'docs'
dependency group. Currently, only `mkdocs` and `mkdocs-material` are needed. You can use the 
following command to add the documentation dependencies to your development environment.

```shell
$ cd ~/github/cgse
$ uv sync --all-packages --all-groups
```

Now you can start the _live-reload_ server of `mkdocs`. This will recreate the documentation 
whenever you make a change in the files below the `docs` folder. After starting this command, 
navigate to the `http://127.0.0.1:8000/cgse/` site in your favorite browser.

```shell
$ uv run mkdocs serve
```

Now you can update files, create new folders in `docs/*`, create new Markdown files and all changes
will be reloaded live in the browser.

When you are ready with updating, you will need to build the site and publish it on GitHub pages:

```shell
$ uv run mkdocs build
$ uv run mkdocs gh-deploy -r upstream -m "documentation update on .."
```

## Commands

- `mkdocs serve` — start the live-reloading docs server
- `mkdocs build` — build the documentation site
- `mkdocs deploy` — publish your documentation on GitHub pages
- `mkdocs -h` — print a help message for more options

## Project layout

The documentation pages follow more or less the structure of the code in terms of libs and 
projects. Below I have laid out this structure leaving out less important files and folders. 

```text
mkdocs.yml         # the mkdocs configuration file
docs
├── index.md       # the documentation homepage
├── initialize.md
├── getting_started.md
├── package_list.md
├── dev_guide/
├── user_guide/
├── libs
│   ├── cgse-common/
│   ├── cgse-coordinates/
│   ├── cgse-core/
│   ├── cgse-gui/
│   └── index.md
├── projects/
│   ├── cgse-tools.md
│   ├── symetrie-hexapod.md
│   └── index.md
├── images/
└── roadmap.md
```
