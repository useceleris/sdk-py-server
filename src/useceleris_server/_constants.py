# Every fixed value the package uses, in one place. Internal: none of these is
# part of the public surface.

# A token timestamp is Unix milliseconds, at most 9999-12-31T23:59:59.999Z.
MINIMUM_TIMESTAMP_MS = 1

MAXIMUM_TIMESTAMP_MS = 253_402_300_799_999

# The server's largest replay lookback: an unsigned 32-bit millisecond count.
MAXIMUM_REPLAY_LOOKBACK_MS = 4_294_967_295

MAXIMUM_CHANNEL_REFERENCE_LENGTH = 255

# The kinds a channel scope or segment permission names; error paths leave
# them out, so a failure is reported at the field the caller wrote.
CLAIM_KINDS = frozenset({"all", "restricted"})

# The two shapes a replay claim takes, named the same way.
REPLAY_SHAPES = frozenset({"enabled", "lookback"})
