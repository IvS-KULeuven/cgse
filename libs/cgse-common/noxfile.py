import nox

python_versions = ["3.9", "3.10", "3.11", "3.12", "3.13"]


@nox.session(python=python_versions)
def uv_tests(session: nox.Session):
    """
    Run the unit and regular tests using `uv`.
    """
    print(f"{session.python = }")

    py_version = ["--python", f"{session.python}"]

    uv_run_cmd = ["uv", "run", "--active", *py_version]
    uv_sync_cmd = ["uv", "sync", "--active", *py_version]

    # session.run_install("uv", "python", "pin", f"{session.python}")

    session.run_install("uv", "venv", *py_version)

    session.run_install(
        *uv_sync_cmd,  # "--all-packages",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    session.run(*uv_run_cmd, "python", "-V")
    session.run(*uv_run_cmd, "python", "-m", "site")
    session.run(*uv_run_cmd, "pytest", "-v", *session.posargs)


@nox.session(python=python_versions, default=False)
def py_tests(session: nox.Session):
    """
    Run the unit and regular tests using plain Python.
    """
    print(f"{session.python = }")

    session.install(".")
    session.install("pytest")
    session.install("pytest-cov")
    session.install("pytest-mock")

    session.run("python", "-V")
    session.run("python", "-m", "site")
    session.run("pytest", "-v", *session.posargs)
