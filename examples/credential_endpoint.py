"""A framework-neutral credential endpoint: the pattern every browser or mobile
application needs.

The application authenticates its own user and derives the authorized claims
here, server-side; a permission the client asks for is never trusted. The
standard library's http.server keeps it framework-neutral: the handler body is
the part that ports to Django, Flask, FastAPI or a serverless function.

Run with CELERIS_CLIENT_ID and CELERIS_SIGNING_SECRET set, then POST
{"channel_reference": "room-42"} with "Authorization: Bearer demo-session".
"""

import json
import os
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from useceleris_server import SigningClaims, create_signer

signer = create_signer(
    client_id=os.environ["CELERIS_CLIENT_ID"],
    signing_secret=os.environ["CELERIS_SIGNING_SECRET"],
)


@dataclass(frozen=True)
class User:
    id: str
    rooms: tuple[str, ...]
    moderator: bool


# Stands in for YOUR authentication: a session cookie, bearer token or the
# framework's user object. It must never come from the request body.
def authenticate(authorization: str | None) -> User | None:
    if authorization != "Bearer demo-session":
        return None

    return User(id="user-8317", rooms=("room-42",), moderator=False)


# The server decides scope. A moderator may write; everyone else reads.
def claims_for(user: User, channel_reference: str) -> SigningClaims:
    return {
        "channels": {"kind": "restricted", "references": [channel_reference]},
        "permissions": {
            "kind": "restricted",
            "segments": [
                {"segment_id": "chat", "read": True, "write": user.moderator},
                {"segment_id": "presence", "read": True, "write": False},
            ],
        },
        # The identity peers see; no colons, CR or LF.
        "reference": user.id,
        "replay": {"lookback_ms": 30_000},
    }


class CredentialEndpoint(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        user = authenticate(self.headers.get("authorization"))

        if user is None:
            self.respond(401, {"error": "unauthenticated"})
            return

        length = int(self.headers.get("content-length") or 0)

        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None

        # Authorize the requested channel against what the user may access.
        channel_reference = (
            body.get("channel_reference") if isinstance(body, dict) else None
        )

        if channel_reference not in user.rooms:
            self.respond(403, {"error": "forbidden"})
            return

        # Sign fresh per request; never cache or backdate credentials.
        credentials = signer.sign(claims_for(user, channel_reference))
        self.respond(
            200, {"payload": credentials.payload, "signature": credentials.signature}
        )

    def respond(self, status: int, body: dict[str, str]) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


if __name__ == "__main__":
    port = int(os.environ.get("CELERIS_EXAMPLE_PORT", "8080"))
    server = ThreadingHTTPServer(("127.0.0.1", port), CredentialEndpoint)
    print("example: credential endpoint listening", flush=True)
    server.serve_forever()
