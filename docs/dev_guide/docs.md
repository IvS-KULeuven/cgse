
# Building the documentation

- Make sure you are in a virtual environment with Python 3.10+
- Run the `mkdocs serve` from the project root older
- Create new pages by adding folder and Markdown files inside `docs/*`

## Set up your environment

I created a virtual environment using `pyenv` and when I'm working on the documentation, I start up a shell with 
this environment. Currently, only `mkdocs` and `mkdocs-material` are needed. Of course, you need to install these 
only once.

```shell
$ pyenv virtualenv 3.10 cgse-doc-3.10
$ pyenv shell cgse-doc-3.10
$ pip install --upgrade pip setuptools wheel
$ pip install mkdocs
$ pip install mkdocs-material
```

From this shell, navigate to the project root folder and start the _live-reload_ server of `mkdocs`.

```shell
$ cd ~/github/cgse
$ mkdocs serve
```

Now you can update files, create new folders in `docs/*`, create new Markdown files and all changes will be reloaded 
live in the browser.

When you are ready with updating, you will need to build the site and publish it on GitHub pages:

```shell
$ mkdocs build
$ mkdocs gh-deploy -r upstream -m "documentation update on .."
```

## Commands

- `mkdocs serve` — start the live-reloading docs server
- `mkdocs build` — build the documentation site
- `mkdocs deploy` — publish your documentation on GitHub pages
- `mkdocs -h` — print a help message for more options

## Project layout

```text
mkdocs.yml     # the mkdocs configuration file
docs/
    index.md   # the documentation homepage
    ...        # other markdown pages, image, folders, ...
```
