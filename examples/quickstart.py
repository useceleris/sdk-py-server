"""useceleris-server quickstart for a trusted backend process.

It signs its own short-lived credentials and consumes realtime through
useceleris-client: the pattern for a backend worker, not a browser. The
signing secret never leaves this process.

Run with CELERIS_WS_URL, CELERIS_CLIENT_ID and CELERIS_SIGNING_SECRET set.
"""

import asyncio
import os
import time

from useceleris_client import (
    ChannelError,
    MessageMetadata,
    ServerError,
    create_client,
    read_text,
)

from useceleris_server import (
    CredentialRequest,
    SigningClaims,
    create_credential_provider,
    create_signer,
)

signer = create_signer(
    client_id=os.environ["CELERIS_CLIENT_ID"],
    signing_secret=os.environ["CELERIS_SIGNING_SECRET"],
)


# Fresh claims and a fresh timestamp per connection attempt. The callback is
# authoritative: nothing from the request widens its scope.
def claims_for(request: CredentialRequest) -> SigningClaims:
    return {
        "channels": {"kind": "restricted", "references": [request.channel_reference]},
        "permissions": {"kind": "all", "read": True, "write": True},
        "reference": "server-quickstart",
        # This connection sees its own publishes.
        "allow_echo": True,
        # On reconnect, catch up on what the outage missed.
        "replay": (
            {"lookback_ms": request.replay_lookback_ms}
            if request.replay_lookback_ms is not None
            else False
        ),
    }


# end function claims_for


def report(error: ChannelError) -> None:
    print("error:", error.type if isinstance(error, ServerError) else error.code)


# end function report


async def main() -> None:
    client = create_client(
        base_url=os.environ["CELERIS_WS_URL"],
        # A local ws:// stack; production uses wss://.
        allow_insecure_loopback=True,
        credential_provider=create_credential_provider(
            signer=signer, claims=claims_for
        ),
    )
    channel = client.channel(f"server-quickstart-{int(time.time() * 1000)}")
    channel.events().on_error(report)

    await channel.connect()

    chat = channel.segment("chat")
    delivered: asyncio.Future[str] = asyncio.get_running_loop().create_future()

    def receive(payload: bytes, metadata: MessageMetadata) -> None:
        if not delivered.done():
            delivered.set_result(read_text(payload))

    # end function receive

    chat.on_message(receive)
    chat.subscribe()
    await asyncio.sleep(1)

    await chat.publish(b"hello from server")
    body = await asyncio.wait_for(delivered, 15)
    presence = await chat.presence_list(page=1, per_page=10)
    await channel.close()

    print(f"example: ok delivered={body} present={presence.total}")


# end function main


if __name__ == "__main__":
    asyncio.run(main())
