import base64
import json
import math
from collections.abc import Callable
from typing import Any
from unittest.mock import Mock

import pytest
from useceleris_client import ConfigurationError

from useceleris_server import create_signer

CLAIMS: dict[str, Any] = {
    "channels": {"kind": "all"},
    "permissions": {"kind": "restricted", "segments": []},
}


def token_for(claims: object, clock: Any = lambda: 1) -> dict[str, Any]:
    signer = create_signer(
        client_id="synthetic-client", signing_secret="synthetic-secret", clock=clock
    )
    untyped: Any = claims
    token: dict[str, Any] = json.loads(base64.b64decode(signer.sign(untyped).payload))
    return token


# end function token_for


@pytest.mark.parametrize(
    "replay", [False, True, {"lookback_ms": 0}, {"lookback_ms": 4294967295}]
)
def test_preserves_replay(replay: Any) -> None:
    token = token_for({**CLAIMS, "replay": replay, "allow_echo": True})

    assert token["replay"] == (
        replay if isinstance(replay, bool) else replay["lookback_ms"]
    )
    assert token["allow_echo"] is True


# end function test_preserves_replay


@pytest.mark.parametrize(
    "lookback_ms",
    [-1, 0.5, 4294967296, math.nan, math.inf, -math.inf, True, "0", None, 1.0],
)
def test_rejects_an_invalid_lookback(lookback_ms: object) -> None:
    with pytest.raises(ConfigurationError, match=r"^Invalid claims\. replay"):
        token_for({**CLAIMS, "replay": {"lookback_ms": lookback_ms}})


# end function test_rejects_an_invalid_lookback


@pytest.mark.parametrize("replay", [None, 0, "false", [], {}])
def test_rejects_a_malformed_replay(replay: object) -> None:
    with pytest.raises(ConfigurationError, match=r"^Invalid claims\. replay"):
        token_for({**CLAIMS, "replay": replay})


# end function test_rejects_a_malformed_replay


def test_names_a_malformed_replay_without_repeating_it() -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_for({**CLAIMS, "replay": "synthetic-marker"})

    assert str(caught.value) == (
        "Invalid claims. replay: Must be a boolean or a dict with an integer "
        "lookback_ms."
    )


# end function test_names_a_malformed_replay_without_repeating_it


@pytest.mark.parametrize("allow_echo", [None, 0, "false", [], {}])
def test_rejects_a_malformed_echo(allow_echo: object) -> None:
    with pytest.raises(ConfigurationError, match=r"^Invalid claims\. allow_echo"):
        token_for({**CLAIMS, "allow_echo": allow_echo})


# end function test_rejects_a_malformed_echo


@pytest.mark.parametrize("timestamp", [1, 253402300799999])
def test_preserves_the_clock_endpoint_and_calls_it_once(timestamp: int) -> None:
    clock = Mock(return_value=timestamp)

    assert token_for(CLAIMS, clock)["timestamp"] == timestamp
    clock.assert_called_once_with()


# end function test_preserves_the_clock_endpoint_and_calls_it_once


@pytest.mark.parametrize(
    "timestamp",
    [
        -1,
        0,
        253402300800000,
        0.5,
        math.nan,
        math.inf,
        -math.inf,
        True,
        "0",
        None,
        1_700_000_000_000.0,
    ],
)
def test_rejects_an_invalid_clock_value(timestamp: object) -> None:
    with pytest.raises(
        ConfigurationError, match=r"^Invalid timestamp from clock\(\)\. "
    ):
        token_for(CLAIMS, lambda: timestamp)


# end function test_rejects_an_invalid_clock_value


def test_uses_the_current_time_when_no_clock_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("time.time_ns", lambda: 456_000_000)
    signer = create_signer(client_id="synthetic-client", signing_secret="secret")
    untyped: Any = CLAIMS

    token = json.loads(base64.b64decode(signer.sign(untyped).payload))

    assert token["timestamp"] == 456


# end function test_uses_the_current_time_when_no_clock_is_given


def test_validation_and_clock_errors_never_expose_values_or_causes() -> None:
    marker = "synthetic-sensitive-marker"

    def raise_marker() -> int:
        raise RuntimeError(marker)

    # end function raise_marker

    operations: list[Callable[[], object]] = [
        lambda: token_for({**CLAIMS, "reference": f"{marker}\n"}),
        lambda: token_for(CLAIMS, raise_marker),
    ]

    for operation in operations:
        with pytest.raises(ConfigurationError) as caught:
            operation()

        error = caught.value
        assert error.code == "Configuration"
        assert error.__cause__ is None
        assert error.__context__ is None
        assert marker not in repr(error)


# end function test_validation_and_clock_errors_never_expose_values_or_causes


def test_reports_a_clock_that_raises() -> None:
    def fail() -> int:
        raise RuntimeError("synthetic")

    # end function fail

    with pytest.raises(ConfigurationError) as caught:
        token_for(CLAIMS, fail)

    assert str(caught.value) == (
        "clock() raised an error instead of returning a millisecond timestamp."
    )


# end function test_reports_a_clock_that_raises


@pytest.mark.parametrize(
    ("replay", "message"),
    [
        (0, "replay: Must be a boolean or a dict with an integer lookback_ms."),
        (
            {"lookback_ms": -1},
            "replay.lookback_ms: Input should be greater than or equal to 0.",
        ),
    ],
)
def test_names_a_replay_failure_at_the_claim_the_caller_wrote(
    replay: object, message: str
) -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_for({**CLAIMS, "replay": replay})

    assert str(caught.value) == f"Invalid claims. {message}"


# end function test_names_a_replay_failure_at_the_claim_the_caller_wrote


def test_reads_no_time_for_claims_it_refuses() -> None:
    clock = Mock(return_value=1)

    with pytest.raises(ConfigurationError):
        token_for({**CLAIMS, "reference": ""}, clock)

    clock.assert_not_called()


# end function test_reads_no_time_for_claims_it_refuses


def test_reads_the_default_clock_once_per_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = Mock(return_value=456_000_000)
    monkeypatch.setattr("time.time_ns", reads)
    signer = create_signer(client_id="synthetic-client", signing_secret="secret")
    untyped: Any = CLAIMS

    signer.sign(untyped)

    reads.assert_called_once_with()


# end function test_reads_the_default_clock_once_per_signature


def test_uses_a_supplied_clock_however_it_converts_to_bool() -> None:
    class FalsyClock:
        def __bool__(self) -> bool:
            return False

        # end method __bool__

        def __call__(self) -> int:
            return 42

        # end method __call__

    # end class FalsyClock

    assert token_for(CLAIMS, FalsyClock())["timestamp"] == 42


# end function test_uses_a_supplied_clock_however_it_converts_to_bool
