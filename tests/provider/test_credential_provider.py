import asyncio
import base64
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest
from useceleris_client import (
    ConfigurationError,
    CredentialProvider,
    CredentialRequest,
    Credentials,
)

from useceleris_server import (
    SigningClaims,
    create_credential_provider,
    create_signer,
)

SIGNER_OPTIONS: dict[str, Any] = {
    "client_id": "client-1",
    "signing_secret": "signing-secret-1",
    "clock": lambda: 1_700_000_000_000,
}

RESTRICTED_CLAIMS: SigningClaims = {
    "channels": {"kind": "restricted", "references": ["room-1"]},
    "permissions": {
        "kind": "restricted",
        "segments": [{"segment_id": "chat", "read": True, "write": False}],
    },
}

INITIAL_REQUEST = CredentialRequest(channel_reference="room-1", reason="initial")


def reconnect_request(replay_lookback_ms: int) -> CredentialRequest:
    return CredentialRequest(
        channel_reference="room-1",
        reason="reconnect",
        disconnected_at=1_700_000_000_000,
        replay_lookback_ms=replay_lookback_ms,
    )


# end function reconnect_request


def decode(credentials: Credentials) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(base64.b64decode(credentials.payload))
    return payload


# end function decode


async def test_invokes_claims_freshly_per_call_and_signs_a_fresh_timestamp() -> None:
    timestamps = iter([1_700_000_000_000, 1_700_000_000_001])
    claims = Mock(return_value=RESTRICTED_CLAIMS)
    provider = create_credential_provider(
        signer=create_signer(**{**SIGNER_OPTIONS, "clock": lambda: next(timestamps)}),
        claims=claims,
    )

    first = await provider(INITIAL_REQUEST)
    second = await provider(INITIAL_REQUEST)

    assert claims.call_count == 2
    claims.assert_called_with(INITIAL_REQUEST)
    assert decode(first)["timestamp"] == 1_700_000_000_000
    assert decode(second)["timestamp"] == 1_700_000_000_001
    assert first != second


# end function test_invokes_claims_freshly_per_call_and_signs_a_fresh_timestamp


async def test_maps_the_replay_lookback_through_the_claims_callback() -> None:
    # The canonical callback: replay comes from the request on reconnect.
    def claims(request: CredentialRequest) -> SigningClaims:
        return {
            **RESTRICTED_CLAIMS,
            "replay": (
                {"lookback_ms": request.replay_lookback_ms}
                if request.replay_lookback_ms is not None
                else False
            ),
        }

    # end function claims

    provider = create_credential_provider(
        signer=create_signer(**SIGNER_OPTIONS), claims=claims
    )

    reconnect = await provider(reconnect_request(30_000))
    initial = await provider(INITIAL_REQUEST)

    assert decode(reconnect)["replay"] == 30_000
    assert decode(initial)["replay"] is False


# end function test_maps_the_replay_lookback_through_the_claims_callback


async def test_accepts_an_asynchronous_claims_callback() -> None:
    async def claims(request: CredentialRequest) -> SigningClaims:
        await asyncio.sleep(0)
        return RESTRICTED_CLAIMS

    # end function claims

    provider = create_credential_provider(
        signer=create_signer(**SIGNER_OPTIONS), claims=claims
    )

    assert decode(await provider(INITIAL_REQUEST))["channel_references"] == ["room-1"]


# end function test_accepts_an_asynchronous_claims_callback


async def test_cancelling_during_pending_claims_never_signs() -> None:
    # A cancellation that lands while the callback is awaited raises there, so
    # no signature ever exists for the client to suppress (AUTH-04).
    sign = Mock()
    started = asyncio.Event()
    release = asyncio.Event()

    async def claims(request: CredentialRequest) -> SigningClaims:
        started.set()
        await release.wait()
        return RESTRICTED_CLAIMS

    # end function claims

    signer: Any = Mock(sign=sign)
    provider = create_credential_provider(signer=signer, claims=claims)
    pending = asyncio.ensure_future(provider(INITIAL_REQUEST))
    await started.wait()

    pending.cancel()
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await pending

    sign.assert_not_called()


# end function test_cancelling_during_pending_claims_never_signs


async def test_signers_hold_no_shared_credential_state() -> None:
    provider_a = create_credential_provider(
        signer=create_signer(**SIGNER_OPTIONS), claims=lambda request: RESTRICTED_CLAIMS
    )
    provider_b = create_credential_provider(
        signer=create_signer(
            **{**SIGNER_OPTIONS, "signing_secret": "other-signing-secret"}
        ),
        claims=lambda request: RESTRICTED_CLAIMS,
    )

    first_a = await provider_a(INITIAL_REQUEST)
    first_b = await provider_b(INITIAL_REQUEST)
    second_a = await provider_a(INITIAL_REQUEST)

    assert first_a.payload == first_b.payload
    assert first_a.signature != first_b.signature
    assert second_a == first_a


# end function test_signers_hold_no_shared_credential_state


async def test_a_claims_failure_propagates_unchanged_without_signing() -> None:
    failure = RuntimeError("synthetic-claims-failure")
    sign = Mock()

    async def claims(request: CredentialRequest) -> SigningClaims:
        raise failure

    # end function claims

    signer: Any = Mock(sign=sign)
    provider = create_credential_provider(signer=signer, claims=claims)

    with pytest.raises(RuntimeError) as caught:
        await provider(INITIAL_REQUEST)

    assert caught.value is failure
    sign.assert_not_called()


# end function test_a_claims_failure_propagates_unchanged_without_signing


async def test_hostile_request_fields_never_widen_scope_beyond_the_claims() -> None:
    provider = create_credential_provider(
        signer=create_signer(**SIGNER_OPTIONS), claims=lambda request: RESTRICTED_CLAIMS
    )
    hostile = CredentialRequest(
        channel_reference="unauthorized-channel", reason="initial"
    )

    payload = decode(await provider(hostile))

    assert payload["channel_references"] == ["room-1"]
    assert payload["token_permission"] == [
        {"segment_id": "chat", "read": True, "write": False}
    ]


# end function test_hostile_request_fields_never_widen_scope_beyond_the_claims


SIGNER_RULE = "signer: Must be an object with a sign() method."

CLAIMS_RULE = "claims: Must be callable."


@pytest.mark.parametrize(
    ("options", "detail"),
    [
        ({"signer": None, "claims": None}, f"{SIGNER_RULE} {CLAIMS_RULE}"),
        ({"signer": create_signer(**SIGNER_OPTIONS), "claims": None}, CLAIMS_RULE),
        ({"signer": None, "claims": lambda request: RESTRICTED_CLAIMS}, SIGNER_RULE),
        (
            {"signer": object(), "claims": lambda request: RESTRICTED_CLAIMS},
            SIGNER_RULE,
        ),
        (
            {
                "signer": SimpleNamespace(sign=None),
                "claims": lambda request: RESTRICTED_CLAIMS,
            },
            SIGNER_RULE,
        ),
        (
            {"signer": create_signer(**SIGNER_OPTIONS), "claims": "callback"},
            CLAIMS_RULE,
        ),
    ],
)
def test_rejects_invalid_provider_options(options: dict[str, Any], detail: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        create_credential_provider(**options)

    assert caught.value.code == "Configuration"
    assert str(caught.value) == f"Invalid credential provider options. {detail}"
    assert caught.value.__context__ is None
    assert SIGNER_OPTIONS["signing_secret"] not in repr(caught.value)


# end function test_rejects_invalid_provider_options


def test_rejects_an_unknown_option() -> None:
    untyped: Any = create_credential_provider

    with pytest.raises(TypeError):
        untyped(
            signer=create_signer(**SIGNER_OPTIONS),
            claims=lambda request: RESTRICTED_CLAIMS,
            extra=True,
        )


# end function test_rejects_an_unknown_option


async def test_invalid_claims_surface_the_signers_configuration_error() -> None:
    untyped: Any = {
        **RESTRICTED_CLAIMS,
        "channels": {"kind": "restricted", "references": []},
    }
    provider = create_credential_provider(
        signer=create_signer(**SIGNER_OPTIONS), claims=lambda request: untyped
    )

    with pytest.raises(ConfigurationError) as caught:
        await provider(INITIAL_REQUEST)

    assert caught.value.code == "Configuration"


# end function test_invalid_claims_surface_the_signers_configuration_error


async def test_satisfies_the_clients_credential_provider_contract() -> None:
    provider: CredentialProvider = create_credential_provider(
        signer=create_signer(**SIGNER_OPTIONS), claims=lambda request: RESTRICTED_CLAIMS
    )

    credentials = await provider(INITIAL_REQUEST)

    assert isinstance(credentials, Credentials)
    assert credentials.payload
    assert credentials.signature


# end function test_satisfies_the_clients_credential_provider_contract


async def test_awaits_any_awaitable_the_claims_callback_returns() -> None:
    async def lookup() -> SigningClaims:
        return RESTRICTED_CLAIMS

    # end function lookup

    # A task, not a coroutine: anything awaitable is awaited.
    provider = create_credential_provider(
        signer=create_signer(**SIGNER_OPTIONS),
        claims=lambda request: asyncio.ensure_future(lookup()),
    )

    assert decode(await provider(INITIAL_REQUEST))["channel_references"] == ["room-1"]


# end function test_awaits_any_awaitable_the_claims_callback_returns


async def test_a_provider_cancelled_before_it_starts_never_calls_claims() -> None:
    claims = Mock(return_value=RESTRICTED_CLAIMS)
    sign = Mock()
    signer: Any = Mock(sign=sign)
    pending = asyncio.ensure_future(
        create_credential_provider(signer=signer, claims=claims)(INITIAL_REQUEST)
    )

    pending.cancel()

    with pytest.raises(asyncio.CancelledError):
        await pending

    claims.assert_not_called()
    sign.assert_not_called()


# end function test_a_provider_cancelled_before_it_starts_never_calls_claims
