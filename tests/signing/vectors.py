from typing import Any, NamedTuple


class SigningVector(NamedTuple):
    name: str
    client_id: str
    signing_secret: str
    timestamp: int
    claims: dict[str, Any]
    payload_json: str
    digest_hex: str
    payload: str
    signature: str


# end class SigningVector


# The reference SDK's fixed synthetic vectors, generated independently with
# Python's json, base64, hmac and hashlib.sha512. Only the claims are spelled
# the Python way (segment_id, lookback_ms, allow_echo); every expected value
# is copied unchanged.
SIGNING_VECTORS = [
    SigningVector(
        name="scoped",
        client_id="synthetic-client",
        signing_secret="synthetic-secret",
        timestamp=123456789,
        claims={
            "channels": {"kind": "restricted", "references": ["room-1"]},
            "permissions": {
                "kind": "restricted",
                "segments": [{"segment_id": "messages", "read": True, "write": False}],
            },
        },
        payload_json=(
            '{"timestamp":123456789,"channel_references":["room-1"],'
            '"token_permission":[{"segment_id":"messages","read":true,"write":false}],'
            '"replay":false,"allow_echo":false}'
        ),
        digest_hex=(
            "a258d39dfb68289d31667e05c0da76f30291f2a030ffaed14655f72f3c08a449"
            "1cdf8bb46b97ffb765f329c41bcd5e3fd336b64a6652327d57fd65d85b9028ce"
        ),
        payload=(
            "eyJ0aW1lc3RhbXAiOjEyMzQ1Njc4OSwiY2hhbm5lbF9yZWZlcmVuY2VzIjpbInJvb20t"
            "MSJdLCJ0b2tlbl9wZXJtaXNzaW9uIjpbeyJzZWdtZW50X2lkIjoibWVzc2FnZXMiLCJy"
            "ZWFkIjp0cnVlLCJ3cml0ZSI6ZmFsc2V9XSwicmVwbGF5IjpmYWxzZSwiYWxsb3dfZWNo"
            "byI6ZmFsc2V9"
        ),
        signature=(
            "c3ludGhldGljLWNsaWVudDphMjU4ZDM5ZGZiNjgyODlkMzE2NjdlMDVjMGRhNzZmMzAy"
            "OTFmMmEwMzBmZmFlZDE0NjU1ZjcyZjNjMDhhNDQ5MWNkZjhiYjQ2Yjk3ZmZiNzY1ZjMy"
            "OWM0MWJjZDVlM2ZkMzM2YjY0YTY2NTIzMjdkNTdmZDY1ZDg1YjkwMjhjZQ=="
        ),
    ),
    SigningVector(
        name="all",
        client_id="synthetic-client",
        signing_secret="synthetic-secret",
        timestamp=123456789,
        claims={
            "channels": {"kind": "all"},
            "permissions": {"kind": "all", "read": True, "write": True},
            "replay": True,
            "allow_echo": True,
        },
        payload_json=(
            '{"timestamp":123456789,"channel_references":null,'
            '"token_permission":{"read":true,"write":true},"replay":true,'
            '"allow_echo":true}'
        ),
        digest_hex=(
            "a0ae04c3de174b3368a67c57558310cdcc05df8beac44e19943084830ee5c505"
            "1f58b5d0503ce13548fbe3a267d3452998c7af39e850be61bbe65f4cda3f4b46"
        ),
        payload=(
            "eyJ0aW1lc3RhbXAiOjEyMzQ1Njc4OSwiY2hhbm5lbF9yZWZlcmVuY2VzIjpudWxsLCJ0"
            "b2tlbl9wZXJtaXNzaW9uIjp7InJlYWQiOnRydWUsIndyaXRlIjp0cnVlfSwicmVwbGF5"
            "Ijp0cnVlLCJhbGxvd19lY2hvIjp0cnVlfQ=="
        ),
        signature=(
            "c3ludGhldGljLWNsaWVudDphMGFlMDRjM2RlMTc0YjMzNjhhNjdjNTc1NTgzMTBjZGNj"
            "MDVkZjhiZWFjNDRlMTk5NDMwODQ4MzBlZTVjNTA1MWY1OGI1ZDA1MDNjZTEzNTQ4ZmJl"
            "M2EyNjdkMzQ1Mjk5OGM3YWYzOWU4NTBiZTYxYmJlNjVmNGNkYTNmNGI0Ng=="
        ),
    ),
    SigningVector(
        name="deny-all",
        client_id="synthetic-client",
        signing_secret="synthetic-secret",
        timestamp=123456789,
        claims={
            "channels": {"kind": "restricted", "references": ["room-1"]},
            "permissions": {"kind": "restricted", "segments": []},
        },
        payload_json=(
            '{"timestamp":123456789,"channel_references":["room-1"],'
            '"token_permission":[],"replay":false,"allow_echo":false}'
        ),
        digest_hex=(
            "498a76990eeab364ca58e9de4077c126096552ddbd7255a15d1f2efafd2446d1"
            "6941bfbd87e9e2963d11266ff95c286da57bc5691a45b18833ae5907e4390de0"
        ),
        payload=(
            "eyJ0aW1lc3RhbXAiOjEyMzQ1Njc4OSwiY2hhbm5lbF9yZWZlcmVuY2VzIjpbInJvb20t"
            "MSJdLCJ0b2tlbl9wZXJtaXNzaW9uIjpbXSwicmVwbGF5IjpmYWxzZSwiYWxsb3dfZWNo"
            "byI6ZmFsc2V9"
        ),
        signature=(
            "c3ludGhldGljLWNsaWVudDo0OThhNzY5OTBlZWFiMzY0Y2E1OGU5ZGU0MDc3YzEyNjA5"
            "NjU1MmRkYmQ3MjU1YTE1ZDFmMmVmYWZkMjQ0NmQxNjk0MWJmYmQ4N2U5ZTI5NjNkMTEy"
            "NjZmZjk1YzI4NmRhNTdiYzU2OTFhNDViMTg4MzNhZTU5MDdlNDM5MGRlMA=="
        ),
    ),
    SigningVector(
        name="unicode-zero",
        client_id="client-雪",
        signing_secret="secret-雪",
        timestamp=123456789,
        claims={
            "channels": {"kind": "all"},
            "permissions": {
                "kind": "restricted",
                "segments": [{"segment_id": "雪", "read": False, "write": True}],
            },
            "reference": "身分",
            "replay": {"lookback_ms": 0},
        },
        payload_json=(
            '{"timestamp":123456789,"reference":"身分","channel_references":null,'
            '"token_permission":[{"segment_id":"雪","read":false,"write":true}],'
            '"replay":0,"allow_echo":false}'
        ),
        digest_hex=(
            "825ee34404877a60c2ffbcf957064dfdf38cce185d13bb74f7518a67e3e94cbf"
            "05b64e04501628b823c5be40bbe3df0093acd96148c19094704390a9af2fe98d"
        ),
        payload=(
            "eyJ0aW1lc3RhbXAiOjEyMzQ1Njc4OSwicmVmZXJlbmNlIjoi6Lqr5YiGIiwiY2hhbm5l"
            "bF9yZWZlcmVuY2VzIjpudWxsLCJ0b2tlbl9wZXJtaXNzaW9uIjpbeyJzZWdtZW50X2lk"
            "Ijoi6ZuqIiwicmVhZCI6ZmFsc2UsIndyaXRlIjp0cnVlfV0sInJlcGxheSI6MCwiYWxs"
            "b3dfZWNobyI6ZmFsc2V9"
        ),
        signature=(
            "Y2xpZW50Lembqjo4MjVlZTM0NDA0ODc3YTYwYzJmZmJjZjk1NzA2NGRmZGYzOGNjZTE4"
            "NWQxM2JiNzRmNzUxOGE2N2UzZTk0Y2JmMDViNjRlMDQ1MDE2MjhiODIzYzViZTQwYmJl"
            "M2RmMDA5M2FjZDk2MTQ4YzE5MDk0NzA0MzkwYTlhZjJmZTk4ZA=="
        ),
    ),
    SigningVector(
        name="replay-max",
        client_id="synthetic-client",
        signing_secret="synthetic-secret",
        timestamp=123456789,
        claims={
            "channels": {"kind": "all"},
            "permissions": {"kind": "all", "read": False, "write": False},
            "replay": {"lookback_ms": 4294967295},
        },
        payload_json=(
            '{"timestamp":123456789,"channel_references":null,'
            '"token_permission":{"read":false,"write":false},"replay":4294967295,'
            '"allow_echo":false}'
        ),
        digest_hex=(
            "b26f3f600358f3e78a0e48457914bb74d3bc11dc031f5423ac2162a743e53c88"
            "4e7a1e716e1cb9d95057b5904cef64b5ab0ef1243d2bf9d52dbdb3b2eb16e98f"
        ),
        payload=(
            "eyJ0aW1lc3RhbXAiOjEyMzQ1Njc4OSwiY2hhbm5lbF9yZWZlcmVuY2VzIjpudWxsLCJ0"
            "b2tlbl9wZXJtaXNzaW9uIjp7InJlYWQiOmZhbHNlLCJ3cml0ZSI6ZmFsc2V9LCJyZXBs"
            "YXkiOjQyOTQ5NjcyOTUsImFsbG93X2VjaG8iOmZhbHNlfQ=="
        ),
        signature=(
            "c3ludGhldGljLWNsaWVudDpiMjZmM2Y2MDAzNThmM2U3OGEwZTQ4NDU3OTE0YmI3NGQz"
            "YmMxMWRjMDMxZjU0MjNhYzIxNjJhNzQzZTUzYzg4NGU3YTFlNzE2ZTFjYjlkOTUwNTdi"
            "NTkwNGNlZjY0YjVhYjBlZjEyNDNkMmJmOWQ1MmRiZGIzYjJlYjE2ZTk4Zg=="
        ),
    ),
    # Characters JSON escapes, and ones JSON.stringify leaves raw (DEL, NEL,
    # the line and paragraph separators, the byte order mark, an astral
    # character). Generated with the reference SDK's own signer.
    SigningVector(
        name="escapes",
        client_id="synthetic-client",
        signing_secret="synthetic-secret",
        timestamp=123456789,
        claims={
            "channels": {"kind": "all"},
            "permissions": {
                "kind": "restricted",
                "segments": [
                    {"segment_id": "s:</script>\x08\x0c", "read": True, "write": False}
                ],
            },
            "reference": 'u"\\/\t\x00\x1f\x7f\x85\u2028\u2029\ufeff\U0001f600',
        },
        payload_json=(
            '{"timestamp":123456789,"reference":"u\\"\\\\/\\t\\u0000\\u001f\x7f\x85\u2028\u2029'
            '\ufeff\U0001f600","channel_references":null,"token_permission":[{"segment_'
            'id":"s:</script>\\b\\f","read":true,"write":false}],"replay":f'
            'alse,"allow_echo":false}'
        ),
        digest_hex=(
            "3d06d0224ea29dc9c79614a290fadd618c7e20b67a2b28cd46fc56dda6a3688b"
            "13762000b8f05bd7e6100f91586b70f8c9468b57c0a818c76fac7cbae458aef1"
        ),
        payload=(
            "eyJ0aW1lc3RhbXAiOjEyMzQ1Njc4OSwicmVmZXJlbmNlIjoidVwiXFwvXHRcdTAwMDBc"
            "dTAwMWZ/woXigKjigKnvu7/wn5iAIiwiY2hhbm5lbF9yZWZlcmVuY2VzIjpudWxsLCJ0"
            "b2tlbl9wZXJtaXNzaW9uIjpbeyJzZWdtZW50X2lkIjoiczo8L3NjcmlwdD5cYlxmIiwi"
            "cmVhZCI6dHJ1ZSwid3JpdGUiOmZhbHNlfV0sInJlcGxheSI6ZmFsc2UsImFsbG93X2Vj"
            "aG8iOmZhbHNlfQ=="
        ),
        signature=(
            "c3ludGhldGljLWNsaWVudDozZDA2ZDAyMjRlYTI5ZGM5Yzc5NjE0YTI5MGZhZGQ2MThj"
            "N2UyMGI2N2EyYjI4Y2Q0NmZjNTZkZGE2YTM2ODhiMTM3NjIwMDBiOGYwNWJkN2U2MTAw"
            "ZjkxNTg2YjcwZjhjOTQ2OGI1N2MwYTgxOGM3NmZhYzdjYmFlNDU4YWVmMQ=="
        ),
    ),
]
