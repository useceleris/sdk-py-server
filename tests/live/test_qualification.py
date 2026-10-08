import asyncio
from collections.abc import Callable

import pytest
from useceleris_client import CelerisConnectionError, ServerError, read_text

from tests.live.helpers import (
    GENERATED_MESSAGE_ID,
    all_permission_claims,
    connected_channel,
    next_error,
    next_message,
    next_notice,
    next_presence,
    now_ms,
    qualification_client,
    unique_channel_reference,
)
from useceleris_server import CredentialRequest, SigningClaims

pytestmark = pytest.mark.live


def shifted(offset_ms: int) -> Callable[[], int]:
    """A clock running offset_ms ahead of now, or behind it."""
    return lambda: now_ms() + offset_ms


# end function shifted


class TestServerSignedCredentials:
    async def test_connects_with_server_signed_credentials(self) -> None:
        reference = unique_channel_reference("auth")
        channel = qualification_client(all_permission_claims(reference)).channel(
            reference
        )
        notices: list[str] = []
        channel.events().on_notice(
            lambda notice: notices.append(read_text(notice.payload))
        )

        await channel.connect()
        await next_notice(
            channel,
            lambda notice: len(notices) >= 2,
            "the connect and default-subscribe greetings",
        )

        assert any("Successfully connected" in notice for notice in notices)
        await channel.close()

    # end method test_connects_with_server_signed_credentials

    async def test_rejects_a_wrong_secret_and_an_unknown_client_as_transport(
        self,
    ) -> None:
        reference = unique_channel_reference("reject")
        claims = all_permission_claims(reference)
        wrong_secret = qualification_client(
            claims, secret="wrong-signing-secret"
        ).channel(reference)

        with pytest.raises(CelerisConnectionError) as caught:
            await wrong_secret.connect()

        assert caught.value.code == "Transport"
        assert wrong_secret.state == "failed"
        assert "wrong-signing-secret" not in repr(caught.value)

        unknown_client = qualification_client(
            claims, signing_client_id="pyqual-unknown"
        ).channel(reference)

        with pytest.raises(CelerisConnectionError) as caught:
            await unknown_client.connect()

        assert caught.value.code == "Transport"

    # end method test_rejects_a_wrong_secret_and_an_unknown_client_as_transport

    async def test_rejects_expired_and_future_clocks_inside_the_observed_window(
        self,
    ) -> None:
        reference = unique_channel_reference("window")
        claims = all_permission_claims(reference)

        for offset_ms in [-61 * 60 * 1_000, 5 * 60 * 1_000]:
            channel = qualification_client(claims, clock=shifted(offset_ms)).channel(
                reference
            )

            with pytest.raises(CelerisConnectionError) as caught:
                await channel.connect()

            assert caught.value.code == "Transport"

        # D-001: the server accepts up to the observed 60-minute window against
        # a documented 60-second intent; recorded, not relied upon.
        stale = qualification_client(claims, clock=shifted(-59 * 60 * 1_000)).channel(
            reference
        )
        await stale.connect()
        await stale.close()

    # end method test_rejects_expired_and_future_clocks_inside_the_observed_window

    async def test_enforces_the_tokens_channel_restriction(self) -> None:
        allowed = unique_channel_reference("scope-allowed")
        denied = unique_channel_reference("scope-denied")
        claims = all_permission_claims(allowed)

        with pytest.raises(CelerisConnectionError) as caught:
            await qualification_client(claims).channel(denied).connect()

        assert caught.value.code == "Transport"

        inside = await connected_channel(allowed, claims)
        assert inside.state == "connected"
        await inside.close()

    # end method test_enforces_the_tokens_channel_restriction


# end class TestServerSignedCredentials


class TestThroughTheProvider:
    async def test_round_trips_a_payload_with_its_id_and_no_self_echo(self) -> None:
        reference = unique_channel_reference("msg")
        claims = all_permission_claims(reference)
        publisher = await connected_channel(reference, claims)
        receiver = await connected_channel(reference, claims)
        publisher_saw: list[str] = []
        publisher.segment("chat").on_message(
            lambda payload, metadata: publisher_saw.append(metadata.message_id)
        )
        publisher.segment("chat").subscribe()
        receiver.segment("chat").subscribe()
        await asyncio.sleep(1.5)

        await publisher.segment("chat").publish("hello-서버".encode())
        message = await next_message(
            receiver.segment("chat"), lambda message: True, "cross-connection delivery"
        )

        assert GENERATED_MESSAGE_ID.fullmatch(message.metadata.message_id)
        assert message.payload.decode() == "hello-서버"
        await asyncio.sleep(1.5)
        assert publisher_saw == []
        await publisher.close()
        await receiver.close()

    # end method test_round_trips_a_payload_with_its_id_and_no_self_echo

    async def test_echoes_to_the_publisher_when_claims_allow_echo(self) -> None:
        reference = unique_channel_reference("echo")
        channel = await connected_channel(
            reference, {**all_permission_claims(reference), "allow_echo": True}
        )
        channel.segment("chat").subscribe()
        await asyncio.sleep(1.5)

        await channel.segment("chat").publish(b"self")
        echoed = await next_message(
            channel.segment("chat"),
            lambda message: message.payload == b"self",
            "an echoed publish",
        )

        assert GENERATED_MESSAGE_ID.fullmatch(echoed.metadata.message_id)
        await channel.close()

    # end method test_echoes_to_the_publisher_when_claims_allow_echo

    async def test_denies_a_read_only_restricted_segments_publish(self) -> None:
        reference = unique_channel_reference("perm")
        # The restricted-segments shape: a segment_id array on the wire.
        read_only = await connected_channel(
            reference,
            {
                "channels": {"kind": "restricted", "references": [reference]},
                "permissions": {
                    "kind": "restricted",
                    "segments": [{"segment_id": "chat", "read": True, "write": False}],
                },
            },
        )

        # Publish returns locally; the denial arrives later, naming the segment.
        await read_only.segment("chat").publish(b"denied")
        denial = await next_error(
            read_only,
            lambda error: (
                isinstance(error, ServerError) and error.type == "PermissionDeniedError"
            ),
            "the PermissionDeniedError frame",
        )

        assert isinstance(denial, ServerError)
        assert (denial.sub_type, denial.resource) == ("PUB", "chat")
        assert read_only.state == "connected"
        await read_only.close()

    # end method test_denies_a_read_only_restricted_segments_publish

    async def test_replays_recent_messages_through_reconnect_claims(self) -> None:
        reference = unique_channel_reference("replay")
        claims = all_permission_claims(reference)
        publisher = await connected_channel(reference, claims)
        live_receiver = await connected_channel(reference, claims)
        live_ids: list[str] = []
        live_receiver.segment("history").on_message(
            lambda payload, metadata: live_ids.append(metadata.message_id)
        )
        live_receiver.segment("history").subscribe()
        await asyncio.sleep(1.5)

        for body in [b"one", b"two", b"three"]:
            await publisher.segment("history").publish(body)

        await next_message(
            live_receiver.segment("history"),
            lambda message: len(live_ids) >= 3,
            "the three live deliveries",
            20,
        )
        await live_receiver.close()

        # A fresh connection whose claims callback applies the request's
        # replay lookback receives the same messages again, ids preserved.
        def replaying(request: CredentialRequest) -> SigningClaims:
            return {
                **claims,
                "replay": {
                    "lookback_ms": request.replay_lookback_ms
                    if request.replay_lookback_ms is not None
                    else 60_000
                },
            }

        # end function replaying

        replay_receiver = await connected_channel(reference, replaying)
        replayed: dict[bytes, str] = {}
        replay_receiver.segment("history").on_message(
            lambda payload, metadata: replayed.__setitem__(payload, metadata.message_id)
        )
        replay_receiver.segment("history").subscribe()
        await next_message(
            replay_receiver.segment("history"),
            lambda message: len(replayed) >= 3,
            "the replayed history",
            25,
        )

        for index, body in enumerate([b"one", b"two", b"three"]):
            assert replayed[body] == live_ids[index]

        await publisher.close()
        await replay_receiver.close()

    # end method test_replays_recent_messages_through_reconnect_claims

    async def test_surfaces_presence_for_a_server_signed_reference(self) -> None:
        reference = unique_channel_reference("presence")
        claims = all_permission_claims(reference)
        watcher = await connected_channel(reference, claims)
        watched = watcher.segment("chat")
        watched.subscribe_presence()
        await asyncio.sleep(1.5)

        actor = await connected_channel(
            reference, {**claims, "reference": "pyqual-server-actor"}
        )
        actor.segment("chat").subscribe()

        # Join and leave are a typed, segment-tagged frame, not prose.
        join = await next_presence(
            watched,
            lambda event: (
                event.joined and event.token_reference == "pyqual-server-actor"
            ),
            "the actor's presence join event",
            20,
        )
        assert join.segment_id == "chat"
        assert join.connection_id != ""

        page = await watcher.segment("chat").presence_list(page=1, per_page=10)

        assert page.total >= 1
        assert any(
            connection.token_reference == "pyqual-server-actor"
            for connection in page.connections
        )
        await actor.close()
        await watcher.close()

    # end method test_surfaces_presence_for_a_server_signed_reference


# end class TestThroughTheProvider
