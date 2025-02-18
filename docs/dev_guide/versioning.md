# Semantic Versioning

We use semantic versioning, aka [semver](https://semver.org), for our releases and patches. Please
follow the rules that are described on their site.

!!! note "TL;DR"

    The version number has the format `MAJOR.MINOR.PATH`, we increment the
    
    - MAJOR version when we make incompatible changes
    - MINOR version when we add or change functionality in a backward compatible manner
    - PATCH version when we make backward compatible bug fixes
    
    The rules above apply when MAJOR >= 1, which are considered _stable_ releases.

As long as MAJOR == 0, we are in initial development and anything may change. The MINOR number will
be increased for adding or removing functionality and the PATCH number will be increased for all
kinds of fixes.

You might occasionally see pre-release and build metadata added to the version number. We will use
the following metadata:

- `-dev.X` — a development release where X >= 1. This will be used for releases where we need to
  test PyPI installations and/or GitHub actions. A development release can be added to any PATCH 
  number. An example development release: `2.3.1-dev.1`.
- `-rc.X` — a release candidate where X >= 1. This is a pre-release and contains all the intended
  features. The release is believed to be stable enough for public testing, but isn't yet considered
  the final production version. There might be more than one release candidate. Release 
  candidates are usually used for releases where PATCH == 0. For example, when we
  have a third release candidate `1.2.0-rc.3` the actual released version will then be `1.2.0`.

## Why not CalVer?

We do not use Calendar Versioning for the following reason:

- Calendar versioning is preferred for projects that have a release schedule that is based on dates,
  like every week or every three months.
- Semantic versioning is preferred when no date related release schedule is foreseen, also major
  version 0 means that API is not yet fixed and everything can change. Our project is in that state
  right now.
