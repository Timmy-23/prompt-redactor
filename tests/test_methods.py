"""Tests for full redaction, pseudonymization and the optional surrogate condition. Run with:  python -m pytest -q"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detector import apply, detect, restore  # noqa: E402
from detector.recognizers import luhn_valid  # noqa: E402

PROMPT = ("Customer Sarah Thompson (CUST-104882), sarah.thompson@gmail.com, (519) 824-4120, "
          "50 Stone Rd E, N1G 2W1, SIN 130 692 544, card 4532 0151 1283 0366. "
          "Also Daniel Okafor, d.okafor@example.org, 226-979-3311. Remind Sarah Thompson; Sarah prefers email.")
REAL = ["Sarah Thompson", "CUST-104882", "sarah.thompson@gmail.com", "(519) 824-4120", "50 Stone Rd E",
        "N1G 2W1", "130 692 544", "4532 0151 1283 0366", "Daniel Okafor", "d.okafor@example.org", "226-979-3311"]


def test_full_redaction_removes_everything_and_cannot_be_restored():
    out = apply(PROMPT, detect(PROMPT), method="redact")
    for v in REAL:
        assert v not in out["text"]
    assert out["text"].count("[REDACTED]") == len(detect(PROMPT))  # one uniform token
    assert out["mapping"] == {}
    assert "[PERSON_1]" not in out["text"]  # no types, no numbering


def test_pseudonymization_uses_consistent_typed_placeholders():
    out = apply(PROMPT, detect(PROMPT), method="pseudonymize")
    for v in REAL:
        assert v not in out["text"]
    assert out["text"].startswith("Customer [PERSON_1] ([ACCOUNT_ID_1]), [EMAIL_1], [PHONE_1]")
    assert out["text"].count("[PERSON_1]") == 3  # full name twice + "Sarah" alone
    assert "[PERSON_2]" in out["text"]  # Daniel Okafor is told apart
    assert restore(out["text"], out["mapping"]).replace("Sarah Thompson prefers", "Sarah prefers") == PROMPT


def test_surrogates_remove_everything_and_restore():
    out = apply(PROMPT, detect(PROMPT), method="surrogate", seed=1)
    for v in REAL:
        assert v not in out["text"]
    assert restore(out["text"], out["mapping"]) == PROMPT


def test_surrogates_are_consistent_and_linked():
    out = apply(PROMPT, detect(PROMPT), method="surrogate", seed=2)
    inv = {v: k for k, v in out["mapping"].items()}
    fake_full = inv["Sarah Thompson"]
    assert out["text"].count(fake_full) == 2  # same person, same fake name
    assert inv["Sarah"] == fake_full.split()[0]  # "Sarah" alone gets the fake first name
    assert inv["Daniel Okafor"] != fake_full


def test_surrogate_values_cannot_be_real():
    for seed in range(20):
        out = apply(PROMPT, detect(PROMPT), method="surrogate", seed=seed)
        inv = {v: k for k, v in out["mapping"].items()}
        assert inv["sarah.thompson@gmail.com"].endswith(("@example.com", "@example.org", "@example.net"))
        phone = re.sub(r"\D", "", inv["(519) 824-4120"])
        assert phone[3:8] == "55501"  # 555-0100..0199 are reserved for fiction
        sin = re.sub(r"\D", "", inv["130 692 544"])
        assert sin.startswith("0") and luhn_valid(sin)  # never issued
        assert inv["N1G 2W1"][0] in "ZW"  # never used as a first letter
        assert inv["4532 0151 1283 0366"].replace(" ", "") in {
            "4111111111111111", "4242424242424242", "4012888888881881", "4000056655665556", "4005519200000004"}
        # formats are kept
        assert re.fullmatch(r"\(\d{3}\) \d{3}-\d{4}", inv["(519) 824-4120"])
        assert re.fullmatch(r"\d{3} \d{3} \d{3}", inv["130 692 544"])
        assert re.fullmatch(r"CUST-\d{6}", inv["CUST-104882"])
        assert inv["50 Stone Rd E"].endswith(" E")


def test_surrogate_email_does_not_keep_real_initials():
    out = apply(PROMPT, detect(PROMPT), method="surrogate", seed=4)
    inv = {v: k for k, v in out["mapping"].items()}
    fake = inv["d.okafor@example.org"]
    fake_daniel = inv["Daniel Okafor"].split()
    assert fake.startswith(fake_daniel[0][0].lower() + ".")
    assert "okafor" not in fake


def test_surrogate_restore_handles_shortened_names():
    out = apply(PROMPT, detect(PROMPT), method="surrogate", seed=5)
    inv = {v: k for k, v in out["mapping"].items()}
    first = inv["Sarah Thompson"].split()[0]
    reply = f"Hi {first}, I've sorted the list. Have a good day!"
    assert restore(reply, out["mapping"]) == "Hi Sarah, I've sorted the list. Have a good day!"
