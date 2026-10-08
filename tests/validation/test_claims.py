import base64
import copy
import json
from typing import Any

import pytest
from useceleris_client import ConfigurationError

from useceleris_server import create_signer

CLAIMS: dict[str, Any] = {
    "channels": {"kind": "restricted", "references": ["room-1"]},
    "permissions": {"kind": "restricted", "segments": []},
}

SIGNER = create_signer(
    client_id="synthetic-client", signing_secret="synthetic-secret", clock=lambda: 123
)


def token_for(claims: object) -> dict[str, Any]:
    untyped: Any = claims
    token: dict[str, Any] = json.loads(base64.b64decode(SIGNER.sign(untyped).payload))
    return token


# end function token_for


def token_with(**overrides: object) -> dict[str, Any]:
    return token_for({**copy.deepcopy(CLAIMS), **overrides})


# end function token_with


def test_constructs_the_exact_deny_all_payload_with_explicit_defaults() -> None:
    assert token_with() == {
        "timestamp": 123,
        "channel_references": ["room-1"],
        "token_permission": [],
        "replay": False,
        "allow_echo": False,
    }
    assert list(token_with()) == [
        "timestamp",
        "channel_references",
        "token_permission",
        "replay",
        "allow_echo",
    ]


# end function test_constructs_the_exact_deny_all_payload_with_explicit_defaults


def test_accepts_letters_digits_hyphens_and_underscores_in_references() -> None:
    token = token_with(channels={"kind": "restricted", "references": ["room_1-A"]})

    assert token["channel_references"] == ["room_1-A"]


# end function test_accepts_letters_digits_hyphens_and_underscores_in_references


@pytest.mark.parametrize(
    ("claim", "overrides"),
    [
        (
            "permissions.segments[0].segment_id",
            {
                "permissions": {
                    "kind": "restricted",
                    "segments": [
                        {"segment_id": "chat\ud800", "read": True, "write": False}
                    ],
                }
            },
        ),
        ("reference", {"reference": "user\udc00"}),
    ],
)
def test_rejects_an_unpaired_surrogate(claim: str, overrides: dict[str, Any]) -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_with(**overrides)

    assert str(caught.value) == (
        f"Invalid claims. {claim}: Must not contain unpaired UTF-16 surrogates."
    )


# end function test_rejects_an_unpaired_surrogate


def test_keeps_well_formed_non_bmp_characters_in_identifiers() -> None:
    token = token_with(
        reference="user-😀",
        permissions={
            "kind": "restricted",
            "segments": [{"segment_id": "chat-😀", "read": True, "write": False}],
        },
    )

    assert token["reference"] == "user-😀"
    assert token["token_permission"] == [
        {"segment_id": "chat-😀", "read": True, "write": False}
    ]


# end function test_keeps_well_formed_non_bmp_characters_in_identifiers


def test_names_the_failed_claim_and_rule_without_repeating_the_input() -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_with(channels={"kind": "restricted", "references": ["room 1"]})

    assert str(caught.value) == (
        "Invalid claims. channels.references[0]: Must contain only ASCII letters, "
        "digits, hyphens (-) or underscores (_)."
    )


# end function test_names_the_failed_claim_and_rule_without_repeating_the_input


@pytest.mark.parametrize("length", [1, 255])
def test_accepts_channel_length(length: int) -> None:
    references = ["a" * length]

    assert (
        token_with(channels={"kind": "restricted", "references": references})[
            "channel_references"
        ]
        == references
    )


# end function test_accepts_channel_length


@pytest.mark.parametrize(
    "references",
    [
        [],
        [""],
        ["a", "a"],
        ["a" * 256],
        ["é"],
        ["a.b"],
        ["a:b"],
        ["a\n"],
        ["a\r"],
        [None],
        [12],
        ("room",),
    ],
)
def test_rejects_an_unsafe_channel_list(references: object) -> None:
    with pytest.raises(ConfigurationError):
        token_with(channels={"kind": "restricted", "references": references})


# end function test_rejects_an_unsafe_channel_list


@pytest.mark.parametrize(
    "channels",
    [None, [], {}, {"kind": "unknown"}, {"kind": "restricted", "references": "room"}],
)
def test_rejects_a_malformed_channel_scope(channels: object) -> None:
    with pytest.raises(ConfigurationError):
        token_with(channels=channels)


# end function test_rejects_a_malformed_channel_scope


def test_names_an_unknown_kind_without_repeating_it() -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_with(channels={"kind": "synthetic-kind"})

    assert str(caught.value) == (
        "Invalid claims. channels: Must have kind 'all' or 'restricted'."
    )


# end function test_names_an_unknown_kind_without_repeating_it


@pytest.mark.parametrize(
    ("read", "write"), [(False, False), (True, False), (False, True), (True, True)]
)
def test_preserves_access(read: bool, write: bool) -> None:
    assert token_with(
        channels={"kind": "all"},
        permissions={"kind": "all", "read": read, "write": write},
    ) == {
        "timestamp": 123,
        "channel_references": None,
        "token_permission": {"read": read, "write": write},
        "replay": False,
        "allow_echo": False,
    }
    assert token_with(
        permissions={
            "kind": "restricted",
            "segments": [{"segment_id": "雪", "read": read, "write": write}],
        }
    )["token_permission"] == [{"segment_id": "雪", "read": read, "write": write}]


# end function test_preserves_access


@pytest.mark.parametrize(
    "permissions",
    [
        None,
        [],
        {},
        {"kind": "unknown"},
        {"kind": "all", "read": True},
        {"kind": "all", "read": "true", "write": False},
        {"kind": "all", "read": 1, "write": False},
        {"kind": "restricted", "segments": None},
        {"kind": "restricted", "segments": [None]},
    ],
)
def test_rejects_malformed_permissions(permissions: object) -> None:
    with pytest.raises(ConfigurationError):
        token_with(permissions=permissions)


# end function test_rejects_malformed_permissions


@pytest.mark.parametrize("value", ["", "a\r", "a\n", None, 1])
def test_rejects_an_invalid_segment_and_identity(value: object) -> None:
    with pytest.raises(ConfigurationError):
        token_with(reference=value)

    with pytest.raises(ConfigurationError):
        token_with(
            permissions={
                "kind": "restricted",
                "segments": [{"segment_id": value, "read": True, "write": False}],
            }
        )


# end function test_rejects_an_invalid_segment_and_identity


def test_rejects_duplicate_segments_without_merging_grants() -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_with(
            permissions={
                "kind": "restricted",
                "segments": [
                    {"segment_id": "room", "read": True, "write": False},
                    {"segment_id": "room", "read": False, "write": True},
                ],
            }
        )

    assert str(caught.value) == (
        "Invalid claims. permissions.segments: Must not repeat a segment ID."
    )


# end function test_rejects_duplicate_segments_without_merging_grants


def test_copies_nested_claims_preserves_values_and_excludes_extra_fields() -> None:
    claims = {
        "channels": {"kind": "restricted", "references": ["b", "a"]},
        "permissions": {
            "kind": "restricted",
            "segments": [
                {"segment_id": " 雪 ", "read": True, "write": False, "extra": "omit"}
            ],
        },
        "reference": " 身分 ",
        "extra": "omit",
        "timestamp": 999,
    }
    original = copy.deepcopy(claims)

    token = token_for(claims)

    assert claims == original
    assert token == {
        "timestamp": 123,
        "reference": " 身分 ",
        "channel_references": ["b", "a"],
        "token_permission": [{"segment_id": " 雪 ", "read": True, "write": False}],
        "replay": False,
        "allow_echo": False,
    }


# end function test_copies_nested_claims_preserves_values_and_excludes_extra_fields


@pytest.mark.parametrize("value", [None, [], "claims", 1])
def test_rejects_malformed_claims(value: object) -> None:
    with pytest.raises(ConfigurationError, match=r"^Invalid claims\. "):
        token_for(value)


# end function test_rejects_malformed_claims


def test_rejects_a_colon_in_references_without_restricting_segment_colons() -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_with(reference="user:123")

    assert str(caught.value) == (
        "Invalid claims. reference: Must not contain a colon, CR or LF."
    )
    assert token_with(
        permissions={
            "kind": "restricted",
            "segments": [{"segment_id": "topic:part", "read": True, "write": False}],
        }
    )["token_permission"] == [
        {"segment_id": "topic:part", "read": True, "write": False}
    ]


# end function test_rejects_a_colon_in_references_without_restricting_segment_colons


@pytest.mark.parametrize("missing", ["channels", "permissions"])
def test_requires_both_scopes_without_defaulting_either(missing: str) -> None:
    claims = {key: value for key, value in CLAIMS.items() if key != missing}

    with pytest.raises(ConfigurationError) as caught:
        token_for(claims)

    assert str(caught.value) == f"Invalid claims. {missing}: Field required."


# end function test_requires_both_scopes_without_defaulting_either


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"channels": {"kind": "restricted", "references": [""]}},
            "channels.references[0]: Must not be empty.",
        ),
        ({"channels": None}, "channels: Must have kind 'all' or 'restricted'."),
        ({"channels": []}, "channels: Must have kind 'all' or 'restricted'."),
        ({"permissions": None}, "permissions: Must have kind 'all' or 'restricted'."),
        ({"reference": ""}, "reference: Must not be empty."),
    ],
)
def test_names_each_rule_exactly(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_with(**overrides)

    assert str(caught.value) == f"Invalid claims. {message}"


# end function test_names_each_rule_exactly


def test_reports_a_claims_value_that_is_not_a_dict_at_the_top() -> None:
    with pytest.raises(ConfigurationError) as caught:
        token_for(None)

    assert str(caught.value) == "Invalid claims. Input should be a valid dictionary."


# end function test_reports_a_claims_value_that_is_not_a_dict_at_the_top


def test_reports_the_first_failure_of_each_value() -> None:
    # Each value is checked rule by rule until one fails; list rules wait for
    # valid elements.
    with pytest.raises(ConfigurationError) as caught:
        token_with(channels={"kind": "restricted", "references": ["a", "a", "b c"]})

    assert str(caught.value) == (
        "Invalid claims. channels.references[2]: Must contain only ASCII letters, "
        "digits, hyphens (-) or underscores (_)."
    )


# end function test_reports_the_first_failure_of_each_value
