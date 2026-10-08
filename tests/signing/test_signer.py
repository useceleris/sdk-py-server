import base64
import copy
from typing import Any, cast

import pytest
from useceleris_client import ConfigurationError, Credentials

from tests.signing.vectors import SIGNING_VECTORS, SigningVector
from useceleris_server import SigningClaims, create_signer

VECTOR = SIGNING_VECTORS[0]

SIGNER_OPTIONS: dict[str, Any] = {
    "client_id": VECTOR.client_id,
    "signing_secret": VECTOR.signing_secret,
    "clock": lambda: VECTOR.timestamp,
}


def claims_of(vector: SigningVector) -> SigningClaims:
    return cast(SigningClaims, copy.deepcopy(vector.claims))


# end function claims_of


@pytest.mark.parametrize(
    "vector", SIGNING_VECTORS, ids=[vector.name for vector in SIGNING_VECTORS]
)
def test_matches_independent_credentials(vector: SigningVector) -> None:
    signer = create_signer(
        client_id=vector.client_id,
        signing_secret=vector.signing_secret,
        clock=lambda: vector.timestamp,
    )

    credentials = signer.sign(claims_of(vector))

    assert credentials == Credentials(
        payload=vector.payload, signature=vector.signature
    )
    assert base64.b64decode(credentials.payload).decode() == vector.payload_json
    assert base64.b64decode(credentials.signature).decode() == (
        f"{vector.client_id}:{vector.digest_hex}"
    )


# end function test_matches_independent_credentials


def test_uses_fresh_timestamps_and_changed_claims_or_secrets() -> None:
    timestamps = iter(range(VECTOR.timestamp, VECTOR.timestamp + 10))
    signer = create_signer(**{**SIGNER_OPTIONS, "clock": lambda: next(timestamps)})

    first = signer.sign(claims_of(VECTOR))
    second = signer.sign(claims_of(VECTOR))

    assert first != second
    assert create_signer(**SIGNER_OPTIONS).sign(
        {**claims_of(VECTOR), "allow_echo": True}
    ) != create_signer(**SIGNER_OPTIONS).sign(claims_of(VECTOR))
    assert create_signer(
        **{**SIGNER_OPTIONS, "signing_secret": "different-secret"}
    ).sign(claims_of(VECTOR)) != create_signer(**SIGNER_OPTIONS).sign(claims_of(VECTOR))


# end function test_uses_fresh_timestamps_and_changed_claims_or_secrets


def test_invalid_configuration_and_claims_raise_synchronously() -> None:
    with pytest.raises(ConfigurationError):
        create_signer(**{**SIGNER_OPTIONS, "client_id": ""})

    with pytest.raises(ConfigurationError) as caught:
        create_signer(**{**SIGNER_OPTIONS, "clock": 1})

    assert str(caught.value) == (
        "Invalid signer options. clock: Input should be callable."
    )

    with pytest.raises(ConfigurationError) as caught:
        create_signer(**SIGNER_OPTIONS).sign(
            {
                **claims_of(VECTOR),
                "channels": {"kind": "restricted", "references": []},
            }
        )

    assert caught.value.code == "Configuration"
    assert str(caught.value) == (
        "Invalid claims. channels.references: Must list at least one channel reference."
    )


# end function test_invalid_configuration_and_claims_raise_synchronously


@pytest.mark.parametrize("option", ["client_id", "signing_secret"])
def test_rejects_an_unpaired_surrogate_at_construction(option: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        create_signer(**{**SIGNER_OPTIONS, option: "value\ud800"})

    assert str(caught.value) == (
        f"Invalid signer options. {option}: Must not contain unpaired UTF-16 "
        "surrogates."
    )


# end function test_rejects_an_unpaired_surrogate_at_construction


def test_caller_mutation_after_signing_does_not_change_credentials() -> None:
    claims: Any = claims_of(VECTOR)
    credentials = create_signer(**SIGNER_OPTIONS).sign(claims)

    claims["channels"]["references"].append("other")
    claims["permissions"]["segments"][0]["write"] = True

    assert credentials == Credentials(
        payload=VECTOR.payload, signature=VECTOR.signature
    )


# end function test_caller_mutation_after_signing_does_not_change_credentials


def test_rejects_an_unknown_option_instead_of_ignoring_it() -> None:
    untyped: Any = create_signer

    with pytest.raises(TypeError):
        untyped(**SIGNER_OPTIONS, crypto={})


# end function test_rejects_an_unknown_option_instead_of_ignoring_it


@pytest.mark.parametrize("client_id", ["", "a:b", "a\r", "a\n", None, 1])
def test_rejects_an_invalid_client_id(client_id: object) -> None:
    with pytest.raises(ConfigurationError, match=r"^Invalid signer options\. "):
        create_signer(**{**SIGNER_OPTIONS, "client_id": client_id})


# end function test_rejects_an_invalid_client_id


@pytest.mark.parametrize("signing_secret", ["", None, 1, b"secret"])
def test_rejects_an_invalid_signing_secret(signing_secret: object) -> None:
    with pytest.raises(ConfigurationError, match=r"^Invalid signer options\. "):
        create_signer(**{**SIGNER_OPTIONS, "signing_secret": signing_secret})


# end function test_rejects_an_invalid_signing_secret


def test_never_shows_the_signing_secret() -> None:
    signer = create_signer(**{**SIGNER_OPTIONS, "signing_secret": "synthetic-marker"})

    assert "synthetic-marker" not in repr(signer)
    assert "synthetic-marker" not in str(signer)


# end function test_never_shows_the_signing_secret


def test_names_every_option_that_failed() -> None:
    with pytest.raises(ConfigurationError) as caught:
        create_signer(client_id="", signing_secret="")

    assert str(caught.value) == (
        "Invalid signer options. client_id: Must not be empty. signing_secret: Must "
        "not be empty."
    )


# end function test_names_every_option_that_failed


def test_option_errors_never_repeat_the_secret() -> None:
    with pytest.raises(ConfigurationError) as caught:
        create_signer(
            client_id="synthetic-marker:", signing_secret="synthetic-marker\ud800"
        )

    assert "synthetic-marker" not in repr(caught.value)
    assert caught.value.__context__ is None


# end function test_option_errors_never_repeat_the_secret
