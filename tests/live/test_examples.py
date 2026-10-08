import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest
from useceleris_client import (
    ChannelError,
    CredentialRequest,
    Credentials,
    ServerError,
    create_client,
)

from tests.live.helpers import websocket_url

pytestmark = pytest.mark.live

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

# The credential endpoint authorizes exactly this channel for its demo user.
ENDPOINT_CHANNEL = "room-42"


def test_runs_the_quickstart() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "quickstart.py")],
        capture_output=True,
        text=True,
        timeout=60,
        env=dict(os.environ),
        check=True,
    )

    assert re.search(
        r"example: ok delivered=hello from server present=\d+", result.stdout
    ), result.stdout


# end function test_runs_the_quickstart


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port: int = probe.getsockname()[1]
        return port


# end function free_port


@pytest.fixture
def endpoint() -> Iterator[str]:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(EXAMPLES / "credential_endpoint.py")],
        env={**os.environ, "CELERIS_EXAMPLE_PORT": str(port)},
        stdout=subprocess.PIPE,
        text=True,
    )

    try:
        assert process.stdout is not None
        assert "listening" in process.stdout.readline()
        yield f"http://127.0.0.1:{port}/"
    finally:
        process.terminate()
        process.wait(timeout=10)

        if process.stdout is not None:
            process.stdout.close()


# end function endpoint


def post(url: str, authorization: str, channel_reference: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        data=json.dumps({"channel_reference": channel_reference}).encode(),
        headers={"authorization": authorization, "content-type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        status = error.code
        error.close()
        return status, b""


# end function post


async def test_mints_credentials_through_the_endpoint_and_connects_with_them(
    endpoint: str,
) -> None:
    # The endpoint authenticates and authorizes server-side.
    assert (await asyncio.to_thread(post, endpoint, "Bearer wrong", ENDPOINT_CHANNEL))[
        0
    ] == 401
    assert (
        await asyncio.to_thread(post, endpoint, "Bearer demo-session", "other-room")
    )[0] == 403

    status, body = await asyncio.to_thread(
        post, endpoint, "Bearer demo-session", ENDPOINT_CHANNEL
    )
    assert status == 200
    credentials = Credentials(**json.loads(body))

    async def provide(request: CredentialRequest) -> Credentials:
        return credentials

    # end function provide

    # The endpoint's credentials drive a real connection: the demo user is
    # read-only on "chat", so a publish is denied while reads work.
    reader = create_client(
        base_url=websocket_url(),
        allow_insecure_loopback=True,
        credential_provider=provide,
    ).channel(ENDPOINT_CHANNEL)
    denials: list[str] = []

    def record(error: ChannelError) -> None:
        if isinstance(error, ServerError):
            denials.append(error.type)

    # end function record

    reader.events().on_error(record)
    await reader.connect()
    reader.segment("chat").subscribe()
    await asyncio.sleep(1.5)

    await reader.segment("chat").publish(b"should be denied")
    await asyncio.sleep(3)

    assert "PermissionDeniedError" in denials
    assert reader.state == "connected"
    await reader.close()


# end function test_mints_credentials_through_the_endpoint_and_connects_with_them
