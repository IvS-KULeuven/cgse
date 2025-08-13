import nox

python_versions = ["3.10", "3.11", "3.12", "3.13"]


# Define monorepo-wide sessions


@nox.session
def ruff(session):
    """Ruff the entire codebase."""
    session.install("ruff")
    session.run("ruff", "check", "--no-fix", "libs/cgse-common/src")
    session.run("ruff", "check", "--no-fix", "libs/cgse-core/src")
