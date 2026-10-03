"""The check: `nox` runs lint, typecheck, tests and package on every supported
Python. `nox -s live` runs the suites against the realtime service in .env.

The pinned useceleris-client comes from PyPI. To work against an unreleased
client, set CELERIS_CLIENT_SOURCE to its checkout, such as ../sdk-py-client."""

import os
import shutil
import zipfile
from email.parser import Parser
from pathlib import Path

import nox
from packaging.requirements import Requirement

nox.options.default_venv_backend = "uv"
nox.options.reuse_venv = "yes"
nox.options.sessions = ["lint", "typecheck", "tests", "package"]

PYTHONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]

ROOT = Path(__file__).parent

PACKAGE = "useceleris_server"

CLIENT_SOURCE = os.environ.get("CELERIS_CLIENT_SOURCE")

DEVELOPMENT = nox.project.dependency_groups(
    nox.project.load_toml("pyproject.toml"), "dev"
)

RUNTIME_DEPENDENCIES = {"pydantic", "typing-extensions", "useceleris-client"}


def requirement(name: str) -> str:
    """The pinned development requirement for one tool."""
    return next(entry for entry in DEVELOPMENT if entry.split("==")[0] == name)


def install_development(session: nox.Session) -> None:
    if CLIENT_SOURCE:
        session.install("-e", CLIENT_SOURCE)

    session.install("-e", ".", *DEVELOPMENT)


@nox.session(python="3.14")
def lint(session: nox.Session) -> None:
    session.install(requirement("ruff"))
    session.run("ruff", "check", ".")
    session.run("ruff", "format", "--check", ".")


@nox.session(python="3.14")
def typecheck(session: nox.Session) -> None:
    install_development(session)
    session.run("mypy")


@nox.session(python=PYTHONS)
def tests(session: nox.Session) -> None:
    install_development(session)
    session.run("pytest", *session.posargs)


@nox.session(python=PYTHONS)
def live(session: nox.Session) -> None:
    install_development(session)
    session.run("pytest", "-m", "live", "tests/live", *session.posargs)


@nox.session(python=PYTHONS)
def package(session: nox.Session) -> None:
    """Builds the sdist and wheel, checks what they contain, installs the wheel
    and uses it as a consumer would."""
    session.install(requirement("mypy"))
    work = Path(session.create_tmp())
    distribution = work / "dist"
    shutil.rmtree(distribution, ignore_errors=True)
    session.run("uv", "build", "--out-dir", str(distribution), str(ROOT), external=True)
    (wheel,) = distribution.glob("*.whl")
    check_wheel(wheel)

    # The client from its checkout when one is set, installed in the same
    # command so it satisfies the pin; otherwise the pinned release is
    # installed from PyPI.
    wheels = [str(wheel)]

    if CLIENT_SOURCE:
        clients = work / "client"
        shutil.rmtree(clients, ignore_errors=True)
        session.run(
            "uv",
            "build",
            "--wheel",
            "--out-dir",
            str(clients),
            CLIENT_SOURCE,
            external=True,
        )
        wheels.extend(str(client) for client in clients.glob("*.whl"))

    session.install("--force-reinstall", *wheels)
    consumer = work / "consumer"
    shutil.rmtree(consumer, ignore_errors=True)
    consumer.mkdir()

    for example in (ROOT / "examples").glob("*.py"):
        shutil.copy(example, consumer)

    shutil.copy(ROOT / "tests" / "signing" / "vectors.py", consumer / "vectors.py")

    with session.chdir(consumer):
        session.run(
            "python",
            "-c",
            f"import {PACKAGE}, pathlib; "
            f"assert 'site-packages' in {PACKAGE}.__file__, {PACKAGE}.__file__; "
            f"assert (pathlib.Path({PACKAGE}.__file__).parent / 'py.typed').exists()",
        )
        # The installed wheel reproduces every signing vector.
        session.run("python", "-c", SIGN_VECTORS)
        # The shipped type information, checked from outside the repository.
        session.run("mypy", "--strict", ".")


SIGN_VECTORS = """
from vectors import SIGNING_VECTORS
from useceleris_server import create_signer

for vector in SIGNING_VECTORS:
    signer = create_signer(
        client_id=vector.client_id,
        signing_secret=vector.signing_secret,
        clock=lambda vector=vector: vector.timestamp,
    )
    credentials = signer.sign(vector.claims)
    assert credentials.payload == vector.payload, vector.name
    assert credentials.signature == vector.signature, vector.name
"""


def check_wheel(wheel: Path) -> None:
    sources = sorted(
        path.relative_to(ROOT / "src").as_posix()
        for path in (ROOT / "src" / PACKAGE).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )

    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        packaged = sorted(name for name in names if name.startswith(f"{PACKAGE}/"))
        (metadata_file,) = (name for name in names if name.endswith("/METADATA"))
        metadata = Parser().parsestr(archive.read(metadata_file).decode())

    assert packaged == sources, f"Wheel files differ from src: {packaged}"
    assert all(
        ".dist-info/" in name for name in names if not name.startswith(f"{PACKAGE}/")
    )

    required = {
        Requirement(entry).name for entry in metadata.get_all("Requires-Dist") or []
    }
    assert required == RUNTIME_DEPENDENCIES, required
