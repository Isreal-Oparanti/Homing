"""The secret screen. Pure code, run on every text before it's stored or sent anywhere.

Saves that look like codes, account numbers or keys become private: kept for the owner,
never sent to a model. We record the *kind* of match, never the matched value.
See docs/09-security-privacy.md#secret-screen.
"""

import math
import re
from dataclasses import dataclass

NIGERIAN_BANKS = (
    r"opay|palmpay|moniepoint|kuda|gtb|gtbank|guaranty|access|zenith|uba|first ?bank|fidelity"
    r"|union ?bank|sterling|wema|fcmb|stanbic|ecobank|polaris|keystone|providus|jaiz"
)

_BACKUP_TOKEN = re.compile(r"^(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{4,}$")
# People label what they save: "Google backup codes: 8423 1957 …", "seed phrase: …".
_CODE_LABEL = re.compile(r"\b(?:backup|recovery|2fa|mfa|two[- ]factor)\s+codes?\b", re.I)
_CODEISH = re.compile(r"^(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{4,}$")
_PHRASE_LABEL = re.compile(r"\b(?:seed|recovery|secret|mnemonic)\s+(?:phrase|words)\b", re.I)
_OTP = re.compile(r"\b(otp|code|pin|token)\b[^0-9]{0,20}\b\d{4,8}\b", re.I)
_NUBAN = re.compile(
    rf"(?:\b(?:acct|account|a/c|{NIGERIAN_BANKS})\b)[\s\S]{{0,40}}?\b\d{{10}}\b", re.I
)
_NUBAN_AFTER = re.compile(
    rf"\b\d{{10}}\b[\s\S]{{0,40}}?\b(?:acct|account|{NIGERIAN_BANKS})\b", re.I
)
_BVN_NIN = re.compile(r"\b(bvn|nin)\b[^0-9]{0,20}\b\d{11}\b", re.I)
_CARD = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_API_KEY = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{16,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{20,}|xox[bpas]-[A-Za-z0-9-]{10,}"
    r"|LLM_\d{6,}_[A-Za-z0-9_-]{8,})"
)
_PASSWORD = re.compile(r"\b(password|passwd|pwd|pass)\s*[:=]\s*\S+", re.I)
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9+/_=-]{32,}\b")
_URL = re.compile(r"https?://\S+|www\.\S+", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?234[\s-]?|0)[789][01]\d(?:[\s-]?\d){7}(?!\d)")


@dataclass(frozen=True)
class ScreenResult:
    private: bool
    reason: str | None = None  # the kind of match, never the value


def _luhn_ok(digits: str) -> bool:
    total, double = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if double:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        double = not double
    return total % 10 == 0


def _entropy(token: str) -> float:
    counts = {c: token.count(c) for c in set(token)}
    return -sum(n / len(token) * math.log2(n / len(token)) for n in counts.values())


def _looks_like_backup_codes(text: str) -> bool:
    tokens = [t for t in re.split(r"[\s,;|]+", text.strip()) if t]
    if not tokens or len(tokens) > 20:
        return False
    parts = [p for t in tokens for p in t.split("-") if p]
    return bool(parts) and all(_BACKUP_TOKEN.match(p) for p in parts)


def _looks_like_labelled_codes(text: str) -> bool:
    if label := _CODE_LABEL.search(text):
        parts = re.split(r"[\s,;|:-]+", text[label.end() :])
        return sum(1 for p in parts if _CODEISH.match(p)) >= 2
    return False


def _looks_like_seed_phrase(text: str) -> bool:
    if label := _PHRASE_LABEL.search(text):
        return len(re.findall(r"\b[a-z]{3,8}\b", text[label.end() :])) >= 12
    return False


def screen(text: str | None) -> ScreenResult:
    """Decide whether a save must stay private. Order: most specific first."""
    if not text or not text.strip():
        return ScreenResult(False)
    if _API_KEY.search(text):  # keys count even inside links (?key=…)
        return ScreenResult(True, "looks_like_api_key")
    # Everything else ignores links: ids inside URLs look like codes and numbers.
    text = _URL.sub(" ", text)
    if _PASSWORD.search(text):
        return ScreenResult(True, "looks_like_password")
    if _BVN_NIN.search(text):
        return ScreenResult(True, "looks_like_id_number")
    if _NUBAN.search(text) or _NUBAN_AFTER.search(text):
        return ScreenResult(True, "looks_like_account_number")
    if _OTP.search(text):
        return ScreenResult(True, "looks_like_one_time_code")
    for match in _CARD.finditer(text):
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            return ScreenResult(True, "looks_like_card_number")
    if _looks_like_backup_codes(text) or _looks_like_labelled_codes(text):
        return ScreenResult(True, "looks_like_code")
    if _looks_like_seed_phrase(text):
        return ScreenResult(True, "looks_like_seed_phrase")
    for token in _LONG_TOKEN.findall(text):
        if _entropy(token) > 4.0:
            return ScreenResult(True, "looks_like_secret_token")
    return ScreenResult(False)


def mask_phones(text: str) -> str:
    """Phone numbers aren't secrets, but they're masked before any model call or demo."""
    return _PHONE.sub("[phone]", text)
