import asyncio
from dataclasses import dataclass, field

import pytest
from useceleris_client import (
    CelerisConnectionError,
    Channel,
    ChannelState,
    CredentialProvider,
    CredentialRequest,
    Credentials,
    create_client,
)

from useceleris_server import SigningClaims, create_credential_provider, create_signer

# These drive the real client with the real provider. The client requests
# credentials before it creates any socket, so a gated claims callback needs
# no server: a counting stand-in records whether a socket was ever created.

SIGNING_SECRET = "synthetic-signing-secret-marker"

RESTRICTED_CLAIMS: SigningClaims = {
    "channels": {"kind": "restricted", "references": ["room-1"]},
    "permissions": {
        "kind": "restricted",
        "segments": [{"segment_id": "chat", "read": True, "write": False}],
    },
}


@pytest.fixture
def sockets_created(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    created: list[str] = []

    def count(url: str) -> None:
        created.append(url)
        raise AssertionError("No socket should be created")

    # end function count

    monkeypatch.setattr("useceleris_client._connection.WebSocket", count)
    return created


# end function sockets_created


@dataclass
class Harness:
    channel: Channel
    states: list[ChannelState] = field(default_factory=list)
    signs: int = 0


# end class Harness


def harness_with(claims: object) -> Harness:
    signer = create_signer(
        client_id="client-1", signing_secret=SIGNING_SECRET, clock=lambda: 1
    )
    harness: Harness

    class CountingSigner:
        def sign(self, value: SigningClaims) -> Credentials:
            harness.signs += 1
            return signer.sign(value)

        # end method sign

    # end class CountingSigner

    provider: CredentialProvider = create_credential_provider(
        signer=CountingSigner(),
        claims=claims,  # type: ignore[arg-type]
    )
    channel = create_client(
        base_url="wss://example.invalid", credential_provider=provider
    ).channel("room-1")
    harness = Harness(channel)
    channel.events().on_state_change(harness.states.append)
    return harness


# end function harness_with


class GatedClaims:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    # end method __init__

    async def __call__(self, request: CredentialRequest) -> SigningClaims:
        self.started.set()
        await self.release.wait()
        return RESTRICTED_CLAIMS

    # end method __call__


# end class GatedClaims


async def test_close_during_pending_claims_cancels_and_never_signs(
    sockets_created: list[str],
) -> None:
    gate = GatedClaims()
    harness = harness_with(gate)
    pending = asyncio.ensure_future(harness.channel.connect())
    await gate.started.wait()

    await harness.channel.close()

    with pytest.raises(CelerisConnectionError) as caught:
        await pending

    assert caught.value.code == "Cancelled"
    assert harness.states == ["connecting", "closing", "closed"]

    gate.release.set()
    await asyncio.sleep(0)

    assert sockets_created == []
    assert harness.signs == 0
    assert harness.channel.state == "closed"


# end function test_close_during_pending_claims_cancels_and_never_signs


async def test_cancelling_connect_during_pending_claims_fails_without_a_socket(
    sockets_created: list[str],
) -> None:
    gate = GatedClaims()
    harness = harness_with(gate)
    pending = asyncio.ensure_future(harness.channel.connect())
    await gate.started.wait()

    pending.cancel()

    with pytest.raises(asyncio.CancelledError):
        await pending

    gate.release.set()
    await asyncio.sleep(0)

    assert sockets_created == []
    assert harness.signs == 0
    assert harness.states == ["connecting", "failed"]


# end function test_cancelling_connect_during_pending_claims_fails_without_a_socket


async def test_a_claims_failure_surfaces_only_the_fixed_safe_error(
    sockets_created: list[str],
) -> None:
    def fail(request: CredentialRequest) -> SigningClaims:
        raise RuntimeError(f"synthetic-claims-failure {SIGNING_SECRET}")

    # end function fail

    harness = harness_with(fail)

    with pytest.raises(CelerisConnectionError) as caught:
        await harness.channel.connect()

    error = caught.value
    assert (error.code, str(error)) == (
        "Transport",
        "Credential acquisition failed: the credential provider raised an error.",
    )
    assert error.__cause__ is None
    assert error.__context__ is None
    assert SIGNING_SECRET not in repr(error)
    assert harness.channel.state == "failed"
    assert sockets_created == []


# end function test_a_claims_failure_surfaces_only_the_fixed_safe_error
