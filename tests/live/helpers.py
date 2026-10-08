import asyncio
import itertools
import os
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from useceleris_client import (
    Channel,
    ChannelError,
    Client,
    MessageMetadata,
    PresenceEvent,
    Segment,
    ServerNotice,
    create_client,
)

from useceleris_server import (
    CredentialRequest,
    SigningClaims,
    create_credential_provider,
    create_signer,
)

# The client gives every publish its own id, which the server delivers as is
# (RESEND-01): 16 random bytes, hex-encoded.
GENERATED_MESSAGE_ID = re.compile("[0-9a-f]{32}")

Value = TypeVar("Value")

Claims = (
    SigningClaims
    | Callable[[CredentialRequest], SigningClaims | Awaitable[SigningClaims]]
)

_channel_counter = itertools.count(1)


def now_ms() -> int:
    return int(time.time() * 1000)


# end function now_ms


def websocket_url() -> str:
    return os.environ["CELERIS_WS_URL"]


# end function websocket_url


def client_id() -> str:
    return os.environ["CELERIS_CLIENT_ID"]


# end function client_id


def signing_secret() -> str:
    return os.environ["CELERIS_SIGNING_SECRET"]


# end function signing_secret


def unique_channel_reference(label: str) -> str:
    return f"pyqual-server-{label}-{now_ms()}-{next(_channel_counter)}"


# end function unique_channel_reference


def qualification_client(
    claims: Claims,
    *,
    signing_client_id: str | None = None,
    secret: str | None = None,
    clock: Callable[[], int] | None = None,
) -> Client:
    """Every live connection runs the real pipeline: signer, credential
    provider, client."""
    signer = create_signer(
        client_id=signing_client_id or client_id(),
        signing_secret=secret or signing_secret(),
        clock=clock,
    )
    callback = claims if callable(claims) else (lambda request: claims)

    return create_client(
        base_url=websocket_url(),
        allow_insecure_loopback=True,
        credential_provider=create_credential_provider(signer=signer, claims=callback),
    )


# end function qualification_client


def all_permission_claims(reference: str) -> SigningClaims:
    return {
        "channels": {"kind": "restricted", "references": [reference]},
        "permissions": {"kind": "all", "read": True, "write": True},
    }


# end function all_permission_claims


async def connected_channel(reference: str, claims: Claims) -> Channel:
    channel = qualification_client(claims).channel(reference)
    await channel.connect()

    return channel


# end function connected_channel


async def wait_for(
    register: Callable[[Callable[[Value], None]], Callable[[], None]],
    predicate: Callable[[Value], bool],
    description: str,
    timeout_s: float = 15,
) -> Value:
    arrived: asyncio.Future[Value] = asyncio.get_running_loop().create_future()

    def deliver(value: Value) -> None:
        if not arrived.done() and predicate(value):
            arrived.set_result(value)

    # end function deliver

    dispose = register(deliver)

    try:
        return await asyncio.wait_for(arrived, timeout_s)
    except asyncio.TimeoutError:
        raise AssertionError(f"Timed out waiting for {description}.") from None
    finally:
        dispose()


# end function wait_for


@dataclass(frozen=True)
class DeliveredMessage:
    payload: bytes
    metadata: MessageMetadata


# end class DeliveredMessage


async def next_message(
    segment: Segment,
    predicate: Callable[[DeliveredMessage], bool],
    description: str = "a message delivery",
    timeout_s: float = 15,
) -> DeliveredMessage:
    def register(deliver: Callable[[DeliveredMessage], None]) -> Callable[[], None]:
        return segment.on_message(
            lambda payload, metadata: deliver(DeliveredMessage(payload, metadata))
        )

    # end function register

    return await wait_for(register, predicate, description, timeout_s)


# end function next_message


async def next_notice(
    channel: Channel,
    predicate: Callable[[ServerNotice], bool],
    description: str = "a server notice",
) -> ServerNotice:
    return await wait_for(channel.events().on_notice, predicate, description)


# end function next_notice


async def next_presence(
    segment: Segment,
    predicate: Callable[[PresenceEvent], bool],
    description: str = "a presence notification",
    timeout_s: float = 15,
) -> PresenceEvent:
    return await wait_for(segment.on_presence, predicate, description, timeout_s)


# end function next_presence


async def next_error(
    channel: Channel,
    predicate: Callable[[ChannelError], bool],
    description: str = "a channel error",
) -> ChannelError:
    return await wait_for(channel.events().on_error, predicate, description)


# end function next_error
