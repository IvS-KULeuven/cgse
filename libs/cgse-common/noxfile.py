import nox


@nox.session(python=['3.9', '3.10', '3.11', '3.12'])
def tests(session: nox.Session):
    """
    Run the unit and regular tests.
    """
    print(f"{session.python = }")

    py_version = ["--python", f"{session.python}"]
    uv_run_cmd = ["uv", "run", "--active", *py_version]

    session.run_install("uv", "python", "pin", f"{session.python}")

    session.run_install("uv", "venv", *py_version)

    session.run_install(
        "uv", "sync", "--active", *py_version, "--all-packages", "--extra=test",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )

    session.run(*uv_run_cmd, "python", "-V")

    session.run(*uv_run_cmd, "pytest", "-v", *session.posargs)
