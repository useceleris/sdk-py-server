# Security policy

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it privately through GitHub's [Security Advisories](https://github.com/useceleris/sdk-py-server/security/advisories/new) on this repository. That channel is private between you and the maintainer, and it lets us prepare a fix before anything is disclosed.

Include what you need to make the problem reproducible: the affected version, the Python version you saw it on, and the smallest example that shows it. A suggested fix is welcome but not required.

You should get an acknowledgement within a few days. We will tell you what we found, what we intend to do, and when we expect a fix to land, and we will credit you when it is published unless you would rather we did not.

## Supported versions

Fixes land on the latest release. There is no long-term support branch.

## Scope

In scope: anything in this package that signs credentials granting more than the claims the caller passed, any leak of the signing secret or a credential into a place it should not reach, and any input that can crash or corrupt a consuming application.

Out of scope: the Celeris service itself, which is reported through the same channel on its own repository, and findings that require an attacker who already holds the signing secret. That secret is the trust boundary, and its compromise is total by design.

## What this package promises

This is the server package. It holds your signing secret and **must never be shipped in a browser, mobile or desktop application**. It signs the claims your code decides; it never derives permissions from anything a caller supplied.

Errors raised here name the option or claim that failed and the rule it broke, but never echo your secret, your claims or your input, and never chain an exception that holds them. A signer's `repr()` never shows the secret.
