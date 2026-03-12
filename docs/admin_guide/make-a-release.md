## Making a release

The first thing to do is to properly format your code changes, run:

```bash
uvx ruff format
```

You should be on the branch with the developments that you want to push and merge the pull request on GitHub before making the release.

- commit all changes with a proper message
- push changes to `origin`
- create a pull request (possibly needs a review)
- merge the pull request

When all pull requests that should go into the release are merged, checkout main again and pull all the latest changes:

```bash
git checkout main
git pull upstream main
```

Now, create the release branch: e.g. `release/v0.17.3`

- `git checkout -b release/v0.17.3`
- add all notable changes to the CHANGELOG file
  - fix the links in the headers if needed
  - add links to the different pull requests
  - commit the CHANGELOG file
- bump the version number: `uv run bump.py [patch|minor|major]`
- commit all `pyproject.toml` files after the version bump
- push the changes to `origin`
- create (and merge) a pull request, use the CHANGELOG as description

In order to prevent publishing all remaining uncommitted changes and untracked files too, stash all changes and untracked files:

```bash
git stash push -u -m "All development work"
```

## Publish the new release

(also check the docs: [Building and publishing packages](https://ivs-kuleuven.github.io/cgse/dev_guide/uv/#building-and-publishing-all-packages))

Now, build and publish the packages:

- remove the old distributions: `rm -r dist`
- build the packages: `uv build --all-packages`
- publish the packages to PyPI: `uv publish --token $UV_PUBLISH_TOKEN`

Put back the changes and untracked files:

```bash
git checkout main
git pull upstream main
git stash pop
```

## Tag the new release

- create a tag for the commit of the bump: `git tag <version number> <commit hash>`, e.g. `git tag v0.16.0 559bbfc`
    - you can find the commit hash with: `git log --oneline`
- push the tag to upstream: `git push upstream <tag name>`, e.g. `git push upstream v0.16.0`


## Building and publishing the documentation

- see [Building the documentation](https://ivs-kuleuven.github.io/cgse/dev_guide/docs/#building-the-documentation)
