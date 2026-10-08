import base64
import contextlib
import hashlib
import hmac
import json
import time
from collections.abc import Callable
from typing import Any

from useceleris_client import ConfigurationError, Credentials

from useceleris_server._claims import (
    SIGNER_OPTIONS,
    SIGNING_CLAIMS,
    TIMESTAMP,
    SigningClaims,
)
from useceleris_server._constants import CLAIM_KINDS, REPLAY_SHAPES
from useceleris_server._parse_error import validate_input

# Stands in for a timestamp when clock() raises.
_CLOCK_FAILED = object()


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


# end function _now_ms


class Signer:
    """Signs short-lived credentials. It holds the signing secret, so it
    belongs on a trusted server only."""

    def __init__(
        self,
        *,
        client_id: str,
        signing_secret: str,
        clock: Callable[[], int] | None = None,
    ) -> None:
        options = validate_input(
            SIGNER_OPTIONS,
            {"client_id": client_id, "signing_secret": signing_secret, "clock": clock},
            "signer options",
        )
        self._client_id = options["client_id"]
        self._signing_secret = options["signing_secret"]
        self._clock = _now_ms if options["clock"] is None else options["clock"]

    # end method __init__

    def __repr__(self) -> str:
        # Never shows the signing secret.
        return "Signer()"

    # end method __repr__

    def sign(self, claims: SigningClaims) -> Credentials:
        """Synchronous: validates the claims, stamps the current time and
        signs."""
        token = _prepare_token_payload(claims, self._clock)
        payload = base64.b64encode(
            json.dumps(token, ensure_ascii=False, separators=(",", ":")).encode()
        ).decode()
        digest = hmac.new(
            self._signing_secret.encode(), payload.encode(), hashlib.sha512
        ).hexdigest()
        signature = base64.b64encode(f"{self._client_id}:{digest}".encode()).decode()

        return Credentials(payload=payload, signature=signature)

    # end method sign


# end class Signer


def create_signer(
    *,
    client_id: str,
    signing_secret: str,
    clock: Callable[[], int] | None = None,
) -> Signer:
    return Signer(client_id=client_id, signing_secret=signing_secret, clock=clock)


# end function create_signer


def _prepare_token_payload(claims: object, clock: Callable[[], int]) -> dict[str, Any]:
    """The wire token, keys in the order the server documents."""
    validated = validate_input(
        SIGNING_CLAIMS, claims, "claims", CLAIM_KINDS | REPLAY_SHAPES
    )
    timestamp: object = _CLOCK_FAILED

    with contextlib.suppress(Exception):
        timestamp = clock()

    # Raised once the clock's own error, which might carry anything, is
    # suppressed.
    if timestamp is _CLOCK_FAILED:
        raise ConfigurationError(
            "clock() raised an error instead of returning a millisecond timestamp."
        )

    token: dict[str, Any] = {
        "timestamp": validate_input(TIMESTAMP, timestamp, "timestamp from clock()")
    }

    if "reference" in validated:
        token["reference"] = validated["reference"]

    channels = validated["channels"]
    token["channel_references"] = (
        None if channels["kind"] == "all" else channels["references"]
    )

    permissions = validated["permissions"]

    if permissions["kind"] == "all":
        token["token_permission"] = {
            "read": permissions["read"],
            "write": permissions["write"],
        }
    else:
        token["token_permission"] = [
            {
                "segment_id": segment["segment_id"],
                "read": segment["read"],
                "write": segment["write"],
            }
            for segment in permissions["segments"]
        ]

    replay = validated.get("replay", False)
    token["replay"] = replay if isinstance(replay, bool) else replay["lookback_ms"]
    token["allow_echo"] = validated.get("allow_echo", False)

    return token


# end function _prepare_token_payload
