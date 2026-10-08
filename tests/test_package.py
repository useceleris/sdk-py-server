import subprocess
import sys

import useceleris_server

# The public surface, written down in this one place.
PUBLIC_NAMES = [
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


def test_exports_exactly_the_public_surface() -> None:
    assert sorted(useceleris_server.__all__) == PUBLIC_NAMES

    for name in PUBLIC_NAMES:
        assert hasattr(useceleris_server, name), name


# end function test_exports_exactly_the_public_surface


IMPORT_PROBE = """
import socket
import threading

created = []
original = socket.socket.__init__


def record(self, *args, **kwargs):
    created.append(args)
    original(self, *args, **kwargs)


socket.socket.__init__ = record

import useceleris_server

assert created == [], "importing opened a socket"
assert threading.active_count() == 1, "importing started a thread"
"""


def test_importing_opens_no_socket_and_starts_no_work() -> None:
    subprocess.run([sys.executable, "-c", IMPORT_PROBE], check=True)


# end function test_importing_opens_no_socket_and_starts_no_work
