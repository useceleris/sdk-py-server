# useceleris-server

Credential signing for Celeris on trusted servers, plus the bridge from the signer to `useceleris-client`'s credential provider.

```python
from useceleris_server import create_signer

signer = create_signer(
    client_id="synthetic-client",
    signing_secret="synthetic-secret",
)

credentials = signer.sign(
    {
        "channels": {"kind": "restricted", "references": ["room-1"]},
        "permissions": {
            "kind": "restricted",
            "segments": [{"segment_id": "messages", "read": True, "write": False}],
        },
    }
)
```

## Install

```sh
pip install --pre useceleris-server
```

Python 3.10 to 3.14. It installs the matching `useceleris-client` for the credential types and errors.

## Signing

Supply real credentials only from trusted configuration. Authenticate and authorize users before choosing their claims; never sign permissions a caller asked for.

- Channel references allow ASCII letters, digits, hyphens and underscores, 1 to 255 characters.
- The `reference` claim (the identity peers see) must be non-empty and contain no colon, CR or LF.
- Segment ids must be non-empty and contain no CR or LF.
- Replay and echo default to `False`; unrestricted scope needs an explicit `"kind": "all"`.
- Text must be well-formed: an unpaired surrogate is refused, since it cannot be encoded as UTF-8.

`create_signer` validates its options at once. `sign(claims)` is synchronous: it validates the claims, stamps the current time, and returns `Credentials(payload, signature)`, opaque strings to pass through unchanged. It raises `ConfigurationError` (from `useceleris_client`) naming the claim and the rule that failed, never the value. The optional `clock` returns Unix milliseconds and exists for tests. A signer holds no resources and needs no disposal; its `repr()` never shows the secret.

## A trusted server that consumes realtime

`create_credential_provider(signer=..., claims=...)` returns the client's `CredentialProvider`. Each connection attempt calls `claims(request)` afresh, synchronously or awaited, and signs with a fresh timestamp. Nothing from the request widens scope beyond what `claims()` returns, and cancelling the attempt while `claims()` is awaited cancels it before anything is signed. `claims()` decides how `request.replay_lookback_ms` maps to `replay`; see [EXAMPLES.md](EXAMPLES.md).

## Examples

[examples/](examples) holds two runnable programs, both run against a real Celeris stack by the live suite:

- [quickstart.py](examples/quickstart.py): a trusted backend signing its own credentials and consuming realtime through `useceleris-client`.
- [credential_endpoint.py](examples/credential_endpoint.py): the pattern every browser, mobile or desktop application needs. It authenticates the user, derives the authorized claims server-side, signs fresh, and returns `{"payload", "signature"}`. It uses the standard library's `http.server`; the handler body ports unchanged to Django, Flask, FastAPI or a serverless function.

## Trust boundary

The signing secret belongs to a trusted server process only: never a browser, a mobile or desktop app, or anything shipped to a user. The client package never depends on this one, and its package check asserts that it carries no signing facility.

Credentials are short-lived and opaque. Sign per request or per connection attempt, never cache, never backdate. Scope every token to the narrowest channel and segment permissions the user needs; `"kind": "all"` is an explicit opt-in, never a default.

## Development

`uv run nox` runs the whole check: lint, `mypy --strict`, the unit suites on every supported Python, and the package check (build, install the wheel, verify its contents and dependencies, and sign every vector with it). `uv run nox -s live` runs the acceptance suites against a real Celeris stack, reading `CELERIS_WS_URL`, `CELERIS_CLIENT_ID` and `CELERIS_SIGNING_SECRET` from a gitignored `.env` or the environment.

The pinned `useceleris-client` comes from PyPI, so a client release precedes the server release that pins it. To work against an unreleased client, set `CELERIS_CLIENT_SOURCE` to its checkout, with `--frozen` so uv keeps the lock instead of resolving a pin PyPI does not have yet:

```sh
uv sync
uv run nox
CELERIS_CLIENT_SOURCE=../sdk-py-client uv run --frozen nox
```

`uv sync` creates `.venv` with the package and its development tools, at the versions in `uv.lock`. `uv add` and `uv remove` change a dependency in `pyproject.toml` and `uv.lock` together: give a runtime dependency a range (`uv add "httpx>=0.28,<1"`) and pin a tool exactly (`uv add --group dev "coverage==7.10.0"`).

`make release` runs that check, builds, and uploads to PyPI from a clean git tree; `make release-test` rehearses on TestPyPI, and `make smoke` installs the published version in a fresh environment. The server's release check installs the pinned client from PyPI, even when `CELERIS_CLIENT_SOURCE` is set, so release the client first.

Read [CONVENTIONS.md](CONVENTIONS.md) before contributing, and [SECURITY.md](SECURITY.md) before reporting a vulnerability.

## License

[Apache 2.0](LICENSE).
