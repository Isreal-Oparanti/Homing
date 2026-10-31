import pytest

from app.verify.secrets import mask_phones, screen

PRIVATE = [
    ("8XK2-9QPL 7MZT-4WQR", "looks_like_code"),
    ("A7K9Q2M4", "looks_like_code"),
    ("recovery codes 8XK2-9QPL 7MZT-4WQR 3HJD-6PLN", "looks_like_code"),
    ("Google backup codes: 8423 1957 6610", "looks_like_code"),
    ("github recovery codes a1b2c-3d4e5 f6a7b-8c9d0", "looks_like_code"),
    (
        "seed phrase: apple river stone cloud mango tiger lemon paper glass ocean bread chair",
        "looks_like_seed_phrase",
    ),
    ("1234-5678-9012-3456-7890", "looks_like_code"),  # prepaid meter token shape
    ("482913570261", "looks_like_code"),
    ("Your OTP code is 482913", "looks_like_one_time_code"),
    ("OPAY 8123456789", "looks_like_account_number"),
    ("acct no: 0123456789 gtbank", "looks_like_account_number"),
    ("BVN: 22123456789", "looks_like_id_number"),
    ("4111 1111 1111 1111", "looks_like_card_number"),
    ("sk-abc123def456ghi789jkl012", "looks_like_api_key"),
    ("https://example.com/api?key=LLM_1234567890_rm_abcdEFGH1234", "looks_like_api_key"),
    ("password: hunter22", "looks_like_password"),
    ("my password is hunter22", "looks_like_password"),
    ("q8ZrT2vLmN4pXw9KsB7dYc1FhJ6gUe3ARtQ0zWv5", "looks_like_secret_token"),
]

NOT_PRIVATE = [
    "Deadline: 31 October 2026",
    "Benefits include a $1,000 monthly stipend, housing allowance and medical insurance.",
    "₦50B+ lost to fraud in Nigerian financial systems",
    "Call me on 08123456789 tomorrow",
    "Meeting at 10:30, room 214",
    "https://www.youtube.com/watch?v=TbB7hSBVKDM",
    "https://docs.google.com/forms/d/e/1FAIpQLSf9xZq2Wk8vT3mR7bN5cJ4hL6pD1sQ0uY9eG/viewform",
    "https://x.com/richtosho/status/2114671452637052976?s=46",
    "Talent apply",
    "WSL",
    "FoundrGeeks",
    "July 18th Dad's birthday",
    "How to store backup codes safely",
    "08123456789",
    "+234 812 345 6789",
    "2026-10-31",
    "What is a seed phrase? https://example.com/seed-phrases-explained",
    "",
]


@pytest.mark.parametrize(("text", "reason"), PRIVATE)
def test_secrets_are_kept_private(text: str, reason: str) -> None:
    result = screen(text)
    assert result.private and result.reason == reason


@pytest.mark.parametrize("text", NOT_PRIVATE)
def test_ordinary_saves_are_not_private(text: str) -> None:
    assert not screen(text).private


def test_reason_never_contains_the_value() -> None:
    assert "482913" not in (screen("Your OTP code is 482913").reason or "")


def test_phones_are_masked() -> None:
    assert mask_phones("Call 08123456789 or +234 812 345 6789") == "Call [phone] or [phone]"
