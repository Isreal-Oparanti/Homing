"""Time-ordered ids (UUIDv7, RFC 9562), so rows sort by creation time."""

import os
import time
import uuid


def uuid7() -> str:
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 random bits
    value = (
        (ms & ((1 << 48) - 1)) << 80
        | 0x7 << 76  # version 7
        | ((rand >> 64) & 0xFFF) << 64  # rand_a, 12 bits
        | 0b10 << 62  # RFC 4122 variant
        | (rand & ((1 << 62) - 1))  # rand_b, 62 bits
    )
    return str(uuid.UUID(int=value))
