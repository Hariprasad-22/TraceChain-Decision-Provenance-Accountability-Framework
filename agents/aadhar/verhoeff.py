"""Verhoeff checksum algorithm - the actual algorithm UIDAI uses for
Aadhaar numbers. Shared between the synthetic generator and the agent's
guardrail validation so both sides agree on what "valid" means."""

_D = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],
    [3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],
    [6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],
    [9,8,7,6,5,4,3,2,1,0],
]
_P = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],
    [8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],
    [2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8],
]


def is_valid_aadhaar_checksum(number_str: str) -> bool:
    """True if all 12 digits (including the checksum digit) are internally consistent."""
    if not number_str or not number_str.isdigit() or len(number_str) != 12:
        return False
    c = 0
    digits = [int(d) for d in reversed(number_str)]
    for i, d in enumerate(digits):
        c = _D[c][_P[i % 8][d]]
    return c == 0


def verhoeff_checksum_digit(number_str: str) -> int:
    """Given the first 11 digits, compute the valid 12th (checksum) digit."""
    c = 0
    digits = [int(d) for d in reversed(number_str)]
    for i, d in enumerate(digits):
        c = _D[c][_P[(i + 1) % 8][d]]
    for candidate in range(10):
        if _D[c][_P[0][candidate]] == 0:
            return candidate
    return 0
