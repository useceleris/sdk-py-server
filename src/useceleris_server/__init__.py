"""Celeris credential signing for trusted servers."""

from useceleris_client import CredentialRequest, Credentials

from useceleris_server._claims import (
    AllChannels,
    AllSegments,
    ChannelScope,
    ReplayLookback,
    RestrictedChannels,
    RestrictedSegments,
    SegmentClaim,
    SegmentPermissions,
    SigningClaims,
)
from useceleris_server._credential_provider import (
    ClaimsCallback,
    SupportsSign,
    create_credential_provider,
)
from useceleris_server._signer import Signer, create_signer

__all__ = [
    "AllChannels",
    "AllSegments",
    "ChannelScope",
    "ClaimsCallback",
    "CredentialRequest",
    "Credentials",
    "ReplayLookback",
    "RestrictedChannels",
    "RestrictedSegments",
    "SegmentClaim",
    "SegmentPermissions",
    "Signer",
    "SigningClaims",
    "SupportsSign",
    "create_credential_provider",
    "create_signer",
]
