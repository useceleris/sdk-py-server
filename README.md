# useceleris-server

[![PyPI](https://img.shields.io/pypi/v/useceleris-server)](https://pypi.org/project/useceleris-server/)
[![Python versions](https://img.shields.io/pypi/pyversions/useceleris-server)](https://pypi.org/project/useceleris-server/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](https://github.com/useceleris/sdk-py-server/blob/main/LICENSE)

Credential signing for Celeris on trusted servers, plus the bridge from the signer to [`useceleris-client`](https://pypi.org/project/useceleris-client/)'s credential provider.

## How it fits

Your server authenticates the user, decides what they may do (which channels, which segments, read or write, replay, echo), and signs those claims with your signing secret. The client connects with the resulting opaque credentials, which it fetches fresh for every connection attempt:

```text
app --(your session)--> your credential endpoint --signer.sign()--> {payload, signature}
app --(payload, signature)--> Celeris
```

A backend that itself publishes or receives uses `useceleris-client` like any other application, and signs its own credentials in-process.

## Install

```sh
pip install --pre useceleris-server
```

Python 3.10 to 3.14, with type information (`py.typed`). It installs `useceleris-client`, whose `Credentials`, `CredentialRequest` and `ConfigurationError` it uses; the client never depends on this package. Install it only where the signing secret may live.

## Sign credentials

```python
import os

from useceleris_server import create_signer

signer = create_signer(
    client_id=os.environ["CELERIS_CLIENT_ID"],
    signing_secret=os.environ["CELERIS_SIGNING_SECRET"],
)

# Least privilege: one channel, explicit segment permissions.
credentials = signer.sign(
    {
        "channels": {"kind": "restricted", "references": ["room-42"]},
        "permissions": {
            "kind": "restricted",
            "segments": [{"segment_id": "chat", "read": True, "write": True}],
        },
        "reference": "user-8317",  # the identity peers see
    }
)
# credentials.payload and credentials.signature go to the client unchanged.
```

`create_signer` validates its options at once. `sign(claims)` is synchronous: it validates the claims, stamps the current time in Unix milliseconds, and returns `Credentials(payload, signature)`, opaque strings that `repr()` never shows. Sign fresh for every request; never cache or backdate. A signer holds no resources and needs no disposal, and its `repr()` never shows the secret. The optional `clock`, returning Unix milliseconds, exists for tests.

Unrestricted access is an explicit opt-in, never an empty list:

```python
broad = signer.sign(
    {
        "channels": {"kind": "all"},
        "permissions": {"kind": "all", "read": True, "write": False},
    }
)
```

## Claims reference

| Claim         | Values                                                                                                                                                                                           | Default  |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------- |
| `channels`    | `{"kind": "all"}`, or `{"kind": "restricted", "references": [...]}`: at least one reference, no repeats, each 1 to 255 ASCII letters, digits, hyphens or underscores                              | Required |
| `permissions` | `{"kind": "all", "read": bool, "write": bool}`, or `{"kind": "restricted", "segments": [{"segment_id": str, "read": bool, "write": bool}, ...]}`: segment ids non-empty, without CR or LF, no repeats; an empty list grants nothing | Required |
| `reference`   | The identity peers see in message metadata and presence: non-empty, without a colon, CR or LF                                                                                                     | Not set  |
| `replay`      | `False`, `True` for the server's default replay window, or `{"lookback_ms": int}` from 0 to 4294967295                                                                                            | `False`  |
| `allow_echo`  | `True` lets a connection receive its own publishes                                                                                                                                               | `False`  |

Validation is strict: `1` is not a `bool`, a tuple is not a list, and text with unpaired surrogates is refused. Keys beyond these are ignored, so never rely on one to grant or restrict anything. A member with `write` but not `read` receives nothing, silently. `SigningClaims` and its parts (`ChannelScope`, `SegmentPermissions`, `SegmentClaim`, `ReplayLookback`, and the `All*` / `Restricted*` shapes) are exported for annotations.

## A credential endpoint

Every application you ship to users (browser, mobile, desktop, CLI) fetches credentials from an endpoint like this one. It runs behind your own authentication, authorizes the requested channel, decides the claims server-side, and signs fresh for each request:

```python
from useceleris_server import SigningClaims


def credentials_for(
    user: User, channel_reference: str, replay_lookback_ms: int | None
) -> dict[str, str]:
    # `user` is the caller your framework authenticated (a session or bearer
    # token), never something read from the request body.
    if not user.may_access(channel_reference):
        raise PermissionError("forbidden")  # answer 403

    claims: SigningClaims = {
        "channels": {"kind": "restricted", "references": [channel_reference]},
        "permissions": permissions_for(user, channel_reference),  # your decision
        "reference": user.reference,
        # A reconnect asks to replay its outage; cap it by your own policy.
        "replay": (
            {"lookback_ms": min(replay_lookback_ms, 30_000)}
            if replay_lookback_ms is not None
            else False
        ),
    }
    credentials = signer.sign(claims)

    return {"payload": credentials.payload, "signature": credentials.signature}
```

Return the dictionary as JSON from any framework's authenticated route (Django, Flask, FastAPI, a serverless function). Never sign permissions the caller asked for. [examples/credential_endpoint.py](https://github.com/useceleris/sdk-py-server/blob/main/examples/credential_endpoint.py) serves the same pattern on the standard library's `http.server`, answering 401 and 403 itself.

## A backend that consumes realtime

A trusted backend that connects with `useceleris-client` signs its own credentials. `create_credential_provider` turns a signer and a claims function into the client's credential provider:

```python
from useceleris_client import create_client

from useceleris_server import (
    CredentialRequest,
    SigningClaims,
    create_credential_provider,
)


def claims_for(request: CredentialRequest) -> SigningClaims:
    if request.channel_reference != "room-42":
        raise PermissionError("this worker serves room-42 only")

    return {
        "channels": {"kind": "restricted", "references": ["room-42"]},
        "permissions": {
            "kind": "restricted",
            "segments": [{"segment_id": "chat", "read": True, "write": True}],
        },
        "reference": "worker-1",
        # request.reason is "initial" or "reconnect"; on reconnect,
        # request.replay_lookback_ms covers the outage.
        "replay": (
            {"lookback_ms": min(request.replay_lookback_ms, 30_000)}
            if request.replay_lookback_ms is not None
            else False
        ),
    }


client = create_client(
    credential_provider=create_credential_provider(signer=signer, claims=claims_for)
)
channel = client.channel("room-42")
await channel.connect()
```

The provider calls `claims(request)` for every connection attempt, awaits it if it is an `async def` (for a database lookup, say), and signs the result with a fresh timestamp. The claims function is authoritative: nothing from the request widens scope beyond what it returns. Cancelling the attempt while it is awaited cancels it, and nothing is signed. An error it raises, or invalid claims it returns, fails the attempt with the client's generic `Transport` error, which never repeats what went wrong; to see which claim and rule failed, sign its result directly with `signer.sign(claims_for(request))`.

[examples/quickstart.py](https://github.com/useceleris/sdk-py-server/blob/main/examples/quickstart.py) is a complete worker that connects, subscribes, publishes and lists presence.

## Errors

Every failure raises `ConfigurationError` from `useceleris_client`, with `code` `"Configuration"`. Its message names each option or claim that failed and the rule it broke, never the value, the secret or the claims:

```python
from useceleris_client import ConfigurationError

try:
    signer.sign(
        {
            "channels": {"kind": "restricted", "references": []},
            "permissions": {"kind": "all", "read": True, "write": True},
        }
    )
except ConfigurationError as error:
    # Invalid claims. channels.references: Must list at least one channel reference.
    print(error.code, error)
```

| Raised by                      | When                                                                                                                      |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| `create_signer()`              | `client_id` is empty or contains a colon, CR or LF; `signing_secret` is empty; either holds unpaired surrogates; `clock` is not callable |
| `Signer.sign()`                | The claims are invalid, or `clock()` raised or returned something other than an `int` from 1 to 253402300799999            |
| `create_credential_provider()` | `signer` has no callable `sign`, or `claims` is not callable                                                              |

An unknown keyword argument is Python's own `TypeError`.

## Trust boundary and keeping the secret

- The signing secret belongs to a trusted server process: never a browser, a mobile or desktop app, a CLI you distribute, or anything else on a user's device. Anyone holding it can sign any claims for your application.
- Read it from the environment or a secret manager; never commit it. This package never logs, prints or `repr()`s it, a credential or your claims, and its errors never repeat them.
- Credentials are short-lived and opaque: sign per request or per connection attempt, never cache or backdate, and scope each to the narrowest channels and segments the user needs.
- The dependency runs server to client only: the client package never depends on this one, and its package check asserts that it carries no signing facility.

## Further documentation

- Server-side usage guide: <https://useceleris.com/docs/sdks/python/server>
- API reference: <https://useceleris.com/docs/api-reference/python-server>
- More walkthroughs: [EXAMPLES.md](https://github.com/useceleris/sdk-py-server/blob/main/EXAMPLES.md)

## Development

```sh
uv sync
uv run nox
CELERIS_CLIENT_SOURCE=../sdk-py-client uv run --frozen nox
```

`uv sync` creates `.venv` with the package and its development tools at the versions in `uv.lock`. `uv run nox` runs the whole check: lint, `mypy --strict`, the unit suites on every supported Python (which also type-check every Python snippet in this README and in EXAMPLES.md), and the package check (build, install the wheel, verify its contents and dependencies, and sign every shared vector with it). `uv run nox -s live` runs the acceptance suites against a real Celeris stack, reading `CELERIS_WS_URL`, `CELERIS_CLIENT_ID` and `CELERIS_SIGNING_SECRET` from a gitignored `.env` or the environment.

`useceleris-client` comes from PyPI, so a client release precedes the server release that requires it. To work against an unreleased client, set `CELERIS_CLIENT_SOURCE` to its checkout and pass `--frozen`, so uv keeps the lock instead of resolving a version PyPI does not have yet. `make release` runs the check, builds, and uploads to PyPI from a clean git tree; `make release-test` rehearses on TestPyPI, and `make smoke` installs the published version in a fresh environment. Both release targets check against the client on PyPI, even when `CELERIS_CLIENT_SOURCE` is set.

Give a runtime dependency a range (`uv add "httpx>=0.28,<1"`) and pin a development tool exactly (`uv add --group dev "coverage==7.10.0"`). Read [CONVENTIONS.md](https://github.com/useceleris/sdk-py-server/blob/main/CONVENTIONS.md) before contributing, and [SECURITY.md](https://github.com/useceleris/sdk-py-server/blob/main/SECURITY.md) before reporting a vulnerability.

## License

[Apache 2.0](https://github.com/useceleris/sdk-py-server/blob/main/LICENSE).
