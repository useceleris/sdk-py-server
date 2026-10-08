import inspect
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeAlias

from useceleris_client import (
    ConfigurationError,
    CredentialProvider,
    CredentialRequest,
    Credentials,
)

from useceleris_server._claims import SigningClaims

# Called once per connection attempt with the client's request; may be
# synchronous or asynchronous.
ClaimsCallback: TypeAlias = Callable[
    [CredentialRequest], SigningClaims | Awaitable[SigningClaims]
]


class SupportsSign(Protocol):
    def sign(self, claims: SigningClaims) -> Credentials: ...

    # end method sign


# end class SupportsSign


def create_credential_provider(
    *, signer: SupportsSign, claims: ClaimsCallback
) -> CredentialProvider:
    """Bridges the synchronous signer to the client's asynchronous credential
    provider.

    The claims callback is authoritative: nothing from the untrusted request
    widens scope beyond what it returns, and each call signs fresh claims with
    a fresh timestamp. Cancelling the attempt while the callback is awaited
    cancels it, so nothing is signed.
    """
    failures = []

    if not callable(getattr(signer, "sign", None)):
        failures.append("signer: Must be an object with a sign() method.")

    if not callable(claims):
        failures.append("claims: Must be callable.")

    if failures:
        raise ConfigurationError(
            f"Invalid credential provider options. {' '.join(failures)}"
        )

    async def provide(request: CredentialRequest) -> Credentials:
        signing_claims = claims(request)

        if inspect.isawaitable(signing_claims):
            signing_claims = await signing_claims

        return signer.sign(signing_claims)

    # end function provide

    return provide


# end function create_credential_provider
