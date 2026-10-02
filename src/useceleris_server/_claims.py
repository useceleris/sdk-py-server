import re
from collections.abc import Callable
from typing import Annotated, Literal, TypeAlias

from pydantic import AfterValidator, Discriminator, Field, Tag, TypeAdapter
from pydantic_core import PydanticCustomError
from typing_extensions import NotRequired, TypedDict

from useceleris_server._constants import (
    MAXIMUM_CHANNEL_REFERENCE_LENGTH,
    MAXIMUM_REPLAY_LOOKBACK_MS,
    MAXIMUM_TIMESTAMP_MS,
    MINIMUM_TIMESTAMP_MS,
)

# Text that is not well-formed cannot be encoded as UTF-8, so the signed bytes
# could never match what the caller passed. A Python str holds surrogate code
# points only unpaired.
_SURROGATE = re.compile("[\ud800-\udfff]")

_CHANNEL_REFERENCE = re.compile("[A-Za-z0-9_-]+")


def _check_well_formed(value: str) -> str:
    if not value:
        raise PydanticCustomError("text", "Must not be empty")

    if _SURROGATE.search(value):
        raise PydanticCustomError("text", "Must not contain unpaired UTF-16 surrogates")

    return value


def _check_identifier(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise PydanticCustomError("identifier", "Must not contain CR or LF")

    return value


def _check_colon_free(value: str) -> str:
    if ":" in value or "\r" in value or "\n" in value:
        raise PydanticCustomError("identifier", "Must not contain a colon, CR or LF")

    return value


def _check_channel_reference(value: str) -> str:
    if not value:
        raise PydanticCustomError("channel_reference", "Must not be empty")

    if len(value) > MAXIMUM_CHANNEL_REFERENCE_LENGTH:
        raise PydanticCustomError(
            "channel_reference",
            f"Must be at most {MAXIMUM_CHANNEL_REFERENCE_LENGTH} characters",
        )

    if _CHANNEL_REFERENCE.fullmatch(value) is None:
        raise PydanticCustomError(
            "channel_reference",
            "Must contain only ASCII letters, digits, hyphens (-) or underscores (_)",
        )

    return value


def _check_references(references: list[str]) -> list[str]:
    if not references:
        raise PydanticCustomError(
            "references", "Must list at least one channel reference"
        )

    if len(set(references)) != len(references):
        raise PydanticCustomError("references", "Must not repeat a channel reference")

    return references


def _check_segments(segments: list["SegmentClaim"]) -> list["SegmentClaim"]:
    segment_ids = [segment["segment_id"] for segment in segments]

    if len(set(segment_ids)) != len(segment_ids):
        raise PydanticCustomError("segments", "Must not repeat a segment ID")

    return segments


def _kind(value: object) -> object:
    return value.get("kind") if isinstance(value, dict) else None


# A fixed message: pydantic's own would quote the kind the caller sent.
_KIND = Discriminator(
    _kind,
    custom_error_type="kind",
    custom_error_message="Must have kind 'all' or 'restricted'",
)


WellFormedText: TypeAlias = Annotated[str, AfterValidator(_check_well_formed)]

Identifier: TypeAlias = Annotated[WellFormedText, AfterValidator(_check_identifier)]

ColonFreeIdentifier: TypeAlias = Annotated[
    WellFormedText, AfterValidator(_check_colon_free)
]

ChannelReference: TypeAlias = Annotated[str, AfterValidator(_check_channel_reference)]


class AllChannels(TypedDict):
    """Every channel of the application."""

    kind: Literal["all"]


class RestrictedChannels(TypedDict):
    """Only the listed channels."""

    kind: Literal["restricted"]
    references: Annotated[list[ChannelReference], AfterValidator(_check_references)]


ChannelScope: TypeAlias = Annotated[
    Annotated[AllChannels, Tag("all")]
    | Annotated[RestrictedChannels, Tag("restricted")],
    _KIND,
]


class AllSegments(TypedDict):
    """The same access to every segment."""

    kind: Literal["all"]
    read: bool
    write: bool


class SegmentClaim(TypedDict):
    segment_id: Identifier
    read: bool
    write: bool


class RestrictedSegments(TypedDict):
    """Access to the listed segments only; any other is denied."""

    kind: Literal["restricted"]
    segments: Annotated[list[SegmentClaim], AfterValidator(_check_segments)]


SegmentPermissions: TypeAlias = Annotated[
    Annotated[AllSegments, Tag("all")]
    | Annotated[RestrictedSegments, Tag("restricted")],
    _KIND,
]


class ReplayLookback(TypedDict):
    lookback_ms: Annotated[int, Field(ge=0, le=MAXIMUM_REPLAY_LOOKBACK_MS)]


def _replay_shape(value: object) -> str | None:
    if isinstance(value, bool):
        return "enabled"

    return "lookback" if isinstance(value, dict) else None


Replay: TypeAlias = Annotated[
    Annotated[bool, Tag("enabled")] | Annotated[ReplayLookback, Tag("lookback")],
    Discriminator(
        _replay_shape,
        custom_error_type="replay",
        custom_error_message=(
            "Must be a boolean or a dict with an integer lookback_ms"
        ),
    ),
]


class SigningClaims(TypedDict):
    """What a credential grants. Keys beyond these are ignored."""

    channels: ChannelScope
    permissions: SegmentPermissions
    # The identity peers see, such as a user id.
    reference: NotRequired[ColonFreeIdentifier]
    # False by default. True replays the server's default window; a lookback
    # replays that many milliseconds.
    replay: NotRequired[Replay]
    # False by default: a connection does not receive its own publishes.
    allow_echo: NotRequired[bool]


SIGNING_CLAIMS = TypeAdapter(SigningClaims)

Timestamp: TypeAlias = Annotated[
    int, Field(ge=MINIMUM_TIMESTAMP_MS, le=MAXIMUM_TIMESTAMP_MS)
]

TIMESTAMP = TypeAdapter(Timestamp)


class _SignerOptions(TypedDict):
    client_id: ColonFreeIdentifier
    signing_secret: WellFormedText
    clock: Callable[[], int] | None


SIGNER_OPTIONS = TypeAdapter(_SignerOptions)
