# useceleris-server: consumer examples

> Every snippet below is checked with `mypy --strict` against the public surface on every `nox` run ([drift test](tests/test_examples.py)). The signing secret lives only on trusted servers, never in a browser, mobile or desktop app.

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
        "reference": "user-8317",  # your app's identity for this user (no colons)
        "replay": {"lookback_ms": 30_000},  # or False (the default)
        "allow_echo": False,  # the default
    }
)
# Credentials(payload=..., signature=...): opaque, pass both through unchanged.
```

Unrestricted access needs the explicit opt-in, never an empty list:

```python
broad = signer.sign(
    {
        "channels": {"kind": "all"},
        "permissions": {"kind": "all", "read": True, "write": False},
    }
)
```

Signing is synchronous and deterministic for fixed inputs; the `clock` option exists for tests.

## A credential endpoint

The application authenticates its own user, derives the authorized claims server-side, and signs. Never trust permissions the client asks for. The shape below is framework-neutral; [examples/credential_endpoint.py](examples/credential_endpoint.py) runs it on the standard library's `http.server`.

```python
from useceleris_server import SigningClaims


def credentials_for(
    user: User, channel_reference: str, lookback_ms: int | None
) -> dict[str, str]:
    if not user.may_access(channel_reference):
        raise PermissionError(channel_reference)

    claims: SigningClaims = {
        "channels": {"kind": "restricted", "references": [channel_reference]},
        "permissions": permissions_for(user, channel_reference),  # the server decides
        "reference": user.reference,
        "replay": {"lookback_ms": lookback_ms} if lookback_ms is not None else False,
    }
    credentials = signer.sign(claims)

    return {"payload": credentials.payload, "signature": credentials.signature}
```

Credentials are short-lived: sign fresh per request, never cache or backdate.

## A trusted server consuming realtime

When a trusted server itself consumes realtime, `create_credential_provider` bridges the signer to the client's credential provider: fresh claims and a fresh timestamp per connection attempt.

```python
from useceleris_client import create_client

from useceleris_server import (
    CredentialRequest,
    SigningClaims,
    create_credential_provider,
)


def claims_for(request: CredentialRequest) -> SigningClaims:
    # request.reason is "initial" or "reconnect"; on reconnect,
    # request.replay_lookback_ms covers the outage.
    return {
        "channels": {"kind": "restricted", "references": [request.channel_reference]},
        "permissions": {"kind": "all", "read": True, "write": True},
        "reference": "service-worker-1",
        "replay": (
            {"lookback_ms": request.replay_lookback_ms}
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

`claims_for` is authoritative: nothing from the request can widen scope beyond what it returns. If it returns invalid claims, the connection attempt fails with the client's generic `Transport` error, which never repeats what went wrong; check a claims function by signing its result directly, `signer.sign(claims_for(request))`, which raises a `ConfigurationError` naming the claim and the rule. It may also be an `async def`, for claims that need a database lookup; cancelling the connection attempt while it runs cancels it, and nothing is signed.

## Errors

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

Errors name the option or claim that failed and the rule it broke, never the secret, the claims or the input.

## What never appears here

Signing in a browser, secrets in client code, a second transport or reconnect implementation, credential caching, or a dependency from the client on this package: the dependency runs server to client only.
