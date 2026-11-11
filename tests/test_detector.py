"""Unit tests. Run with:  python -m pytest -q"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from detector import apply, detect, restore  # noqa: E402
from detector.recognizers import luhn_valid  # noqa: E402


def types(text, mode="hybrid"):
    return {(d.entity, d.text) for d in detect(text, mode=mode)}


def test_luhn():
    assert luhn_valid("130 692 544")
    assert not luhn_valid("130 692 545")


def test_sin_needs_valid_checksum():
    assert ("CA_SIN", "130 692 544") in types("My SIN is 130 692 544.")
    assert not any(e == "CA_SIN" for e, _ in types("My SIN is 130 692 545."))


def test_core_entities():
    t = ("Sarah Thompson, sarah.t@example.com, (519) 824-4120, 50 Stone Rd E, "
         "N1G 2W1, CUST-104882, card 4532 0151 1283 0366")
    found = types(t)
    for item in [("PERSON", "Sarah Thompson"), ("EMAIL_ADDRESS", "sarah.t@example.com"),
                 ("PHONE_NUMBER", "(519) 824-4120"), ("STREET_ADDRESS", "50 Stone Rd E"),
                 ("CA_POSTAL_CODE", "N1G 2W1"), ("ACCOUNT_ID", "CUST-104882"),
                 ("CREDIT_CARD", "4532 0151 1283 0366")]:
        assert item in found, item


def test_space_separated_phone_and_mastercard_2_series():
    assert ("PHONE_NUMBER", "437 869 5381") in types("call 437 869 5381")
    assert ("CREDIT_CARD", "2223 0000 4841 0010") in types("card 2223 0000 4841 0010")


def test_no_false_alarms_on_clean_text():
    for t in ["Order 4471 shipped on March 2 for $129.99.",
              "Convert 500 square feet to square metres.",
              "Python 3.12.0 was released in 2023."]:
        assert detect(t) == [], t


def test_address_not_tagged_as_person():
    found = types("She lives at 3117 Ruth Place N in town.")
    assert ("STREET_ADDRESS", "3117 Ruth Place N") in found
    assert not any(e == "PERSON" for e, _ in found)


def test_rules_mode_finds_no_names_and_ner_mode_finds_no_emails():
    t = "Email Sarah Thompson at sarah.t@example.com"
    assert not any(e == "PERSON" for e, _ in types(t, "rules"))
    assert not any(e == "EMAIL_ADDRESS" for e, _ in types(t, "ner"))


def test_pseudonymize_placeholders_are_consistent_and_restore():
    t = "Tell Sarah Thompson that Sarah Thompson's order is late. Call (519) 824-4120."
    out = apply(t, detect(t), method="pseudonymize")
    assert "Sarah Thompson" not in out["text"]
    assert out["text"].count("[PERSON_1]") == 2
    assert restore("Hi [PERSON_1], we called [PHONE_1].", out["mapping"]) == \
        "Hi Sarah Thompson, we called (519) 824-4120."
