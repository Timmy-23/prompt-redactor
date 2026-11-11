"""Custom pattern recognizers for Canadian identifiers and record-style data.

Presidio ships with recognizers for emails, phone numbers and credit cards,
but not for Canadian Social Insurance Numbers, postal codes, street addresses
or internal account/customer IDs. These are added here.
"""
import re
from typing import List, Optional

from presidio_analyzer import Pattern, PatternRecognizer


def luhn_valid(number: str) -> bool:
    digits = [int(c) for c in number if c.isdigit()][::-1]
    if not digits:
        return False
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


class CaSinRecognizer(PatternRecognizer):
    """Canadian Social Insurance Number: 9 digits, Luhn checksum.

    Valid SINs never start with 0 or 8 (8 is reserved for business numbers).
    Without the checksum, any 9-digit number (and many phone numbers) would match.
    """

    PATTERNS = [
        Pattern("SIN (grouped)", r"\b[1-79]\d{2}[ -]\d{3}[ -]\d{3}\b", 0.5),
        Pattern("SIN (plain)", r"\b[1-79]\d{8}\b", 0.3),
    ]
    CONTEXT = ["sin", "social insurance", "insurance number", "nas"]

    def __init__(self):
        super().__init__(
            supported_entity="CA_SIN",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            name="CaSinRecognizer",
        )

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        # True -> score raised to 1.0; False -> result dropped.
        return luhn_valid(pattern_text)


class CaPostalCodeRecognizer(PatternRecognizer):
    # Letters D, F, I, O, Q, U never appear; W and Z never appear first.
    PATTERNS = [
        Pattern(
            "Canadian postal code",
            r"\b[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ -]?\d[ABCEGHJ-NPRSTV-Z]\d\b",
            0.6,
        )
    ]
    CONTEXT = ["postal", "address", "postcode", "code"]

    def __init__(self):
        super().__init__(
            supported_entity="CA_POSTAL_CODE",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            name="CaPostalCodeRecognizer",
        )


STREET_SUFFIXES = (
    "Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Crescent|Cres|Court|Ct|"
    "Lane|Ln|Way|Place|Pl|Trail|Terrace|Circle|Parkway|Pkwy|Highway|Hwy|Square|Sq"
)


class StreetAddressRecognizer(PatternRecognizer):
    """Number + street name + street type, with optional direction and unit.

    e.g. "50 Stone Rd E", "1204 Maple Crescent, Unit 3", "Apt 12, 88 King St W".
    """

    PATTERNS = [
        Pattern(
            "Street address",
            r"\b(?:(?:Unit|Apt|Suite)\s*\d+[A-Z]?,?\s+)?\d{1,5}\s+(?:[A-Z][a-zA-Z'\-]+\s+){1,3}"
            r"(?:" + STREET_SUFFIXES + r")\.?(?:\s+(?:N|S|E|W|North|South|East|West))?\b"
            r"(?:,?\s+(?:Unit|Apt|Suite)\s*\d+[A-Z]?)?",
            0.6,
        )
    ]
    CONTEXT = ["address", "lives", "live", "located", "ship", "mail", "deliver"]

    def __init__(self):
        super().__init__(
            supported_entity="STREET_ADDRESS",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            name="StreetAddressRecognizer",
            # Presidio ignores case by default; street names must be capitalized,
            # otherwise "500 square feet to square" looks like an address.
            global_regex_flags=re.DOTALL | re.MULTILINE,
        )


class AccountIdRecognizer(PatternRecognizer):
    """Internal customer / account / patient / student record IDs.

    Organizations use their own formats, so the prefixes are configurable.
    Default examples: CUST-104882, ACC-2024-00931, PT-55821, STU-1408808.
    """

    DEFAULT_PREFIXES = ["CUST", "CUS", "ACC", "ACCT", "PT", "PAT", "STU", "EMP", "MRN", "CID"]
    CONTEXT = ["customer", "account", "acct", "patient", "student", "employee", "record", "id"]

    def __init__(self, prefixes: Optional[List[str]] = None):
        prefixes = prefixes or self.DEFAULT_PREFIXES
        alt = "|".join(sorted(prefixes, key=len, reverse=True))
        patterns = [
            Pattern("Record ID", r"\b(?:" + alt + r")[-#]?\d{4,10}(?:-\d{2,6})?\b", 0.6),
            Pattern("Record ID (year)", r"\b(?:" + alt + r")-\d{4}-\d{3,8}\b", 0.65),
        ]
        super().__init__(
            supported_entity="ACCOUNT_ID",
            patterns=patterns,
            context=self.CONTEXT,
            name="AccountIdRecognizer",
        )


class CaPhoneRecognizer(PatternRecognizer):
    """North American phone numbers in the formats Canadians actually type.

    Presidio's built-in phone recognizer scores "519 824 4120" (spaces only)
    and many dashed numbers below the threshold when there are no context
    words, so this adds a stricter NANP pattern: area code and exchange both
    start with 2-9.
    """

    PATTERNS = [
        Pattern(
            "NANP phone",
            r"(?<![\w-])(?:\+?1[ .-]?)?(?:\([2-9]\d{2}\)|[2-9]\d{2})[ .-]?[2-9]\d{2}[ .-]\d{4}(?:\s*(?:x|ext\.?)\s*\d{1,5})?(?![\w-])",
            0.6,
        )
    ]
    CONTEXT = ["phone", "call", "cell", "mobile", "tel", "reach", "contact", "text"]

    def __init__(self):
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            name="CaPhoneRecognizer",
        )


class MastercardSeries2Recognizer(PatternRecognizer):
    """Mastercard 2-series numbers (2221-2720), which Presidio's card pattern misses."""

    PATTERNS = [
        Pattern(
            "Mastercard 2-series",
            r"\b2(?:2[2-9]\d|[3-6]\d{2}|7[01]\d|720)[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b",
            0.5,
        )
    ]
    CONTEXT = ["card", "credit", "visa", "mastercard", "payment"]

    def __init__(self):
        super().__init__(
            supported_entity="CREDIT_CARD",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            name="MastercardSeries2Recognizer",
        )

    def validate_result(self, pattern_text: str) -> Optional[bool]:
        return luhn_valid(pattern_text)


def custom_recognizers() -> list:
    return [
        CaSinRecognizer(),
        CaPostalCodeRecognizer(),
        StreetAddressRecognizer(),
        AccountIdRecognizer(),
        CaPhoneRecognizer(),
        MastercardSeries2Recognizer(),
    ]
