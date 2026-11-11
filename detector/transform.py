"""Turn a prompt plus its confirmed detections into a safer prompt.

The two methods compared in the project (see the proposal, Phase 2):

  - "redact"        Full redaction. Every item becomes the same uniform token,
                    [REDACTED]. It hides the type of data, and mentions can't be
                    linked. Nothing can be restored.

  - "pseudonymize"  Pseudonymization with consistent, typed placeholders
                    ([PERSON_1], [EMAIL_1]), following the category-unique
                    approach of Deusser et al. (2026). The same value always gets
                    the same placeholder, so the AI can tell people apart. The
                    placeholder -> original mapping stays on the user's device so
                    the AI's answer can be restored.

An optional extra condition, "surrogate", replaces items with realistic fake
values instead of placeholders ("Sarah Thompson" -> "Emily Clark"), similar
to SurrogateShield (Jathanna, 2026). It is not part of the main comparison.
Its fake values are chosen so they cannot be someone's real data:
  - emails use the reserved domains example.com / .org / .net (RFC 2606)
  - phone numbers use 555-0100 to 555-0199, reserved for fiction in North America
  - SINs start with 0, which is never issued (still pass the checksum)
  - card numbers are published test numbers that cannot be charged
  - postal codes start with Z or W, which Canada Post never uses as a first letter
  - names, streets and IDs are random and checked against the prompt so a fake
    value never equals a real one in the same text
"""
import random
import re
from typing import Dict, List, Optional

from faker import Faker

from .engine import Detection, _normalize
from .recognizers import luhn_valid

METHODS = ("redact", "pseudonymize", "surrogate")
REDACT_TOKEN = "[REDACTED]"

TAG_NAMES = {
    "PERSON": "PERSON", "EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "PHONE", "CA_SIN": "SIN",
    "CREDIT_CARD": "CARD", "CA_POSTAL_CODE": "POSTAL_CODE", "STREET_ADDRESS": "ADDRESS",
    "ACCOUNT_ID": "ACCOUNT_ID", "LOCATION": "PLACE", "OTHER": "REDACTED",
}

# Published payment-network test numbers (never chargeable), by brand.
TEST_CARDS = {
    "visa": ["4111111111111111", "4242424242424242", "4012888888881881", "4000056655665556", "4005519200000004"],
    "mastercard": ["5555555555554444", "5105105105105100", "5200828282828210", "2223003122003222", "2223000048410010"],
    "amex": ["378282246310005", "371449635398431", "378734493671000"],
    "other": ["6011111111111117", "6011000990139424", "3530111333300000"],
}
# Fake names must not be everyday words, or restoring "Have a good Day" would
# turn it into "Have a good Thompson".
COMMON_WORD_NAMES = set("""
day best king young hope may rose white black brown green gray grey bell hill wood woods long little
strong price rich small hall love grant church field fields park stone lane banks booth cash cook short
moon frost snow rice page mark bill will joy faith grace summer winter mason hunter major nash case bond
hart fox wolf free holiday christmas walker baker miller carpenter turner taylor parker cole lee chance
star sun rain storm north south west east bush pope dean judge knight bishop guy jack sky dawn early
""".split())

STREET_TYPES = ["Street", "St", "Road", "Rd", "Avenue", "Ave", "Drive", "Dr", "Crescent", "Cres",
                "Court", "Ct", "Lane", "Ln", "Way", "Boulevard", "Blvd", "Place", "Pl", "Trail"]


def _apply_digits(template: str, digits: str) -> str:
    """Write `digits` into the digit positions of `template`, keeping its format."""
    it = iter(digits)
    return "".join(next(it) if c.isdigit() else c for c in template)


def _luhn_complete(prefix: str) -> str:
    for d in "0123456789":
        if luhn_valid(prefix + d):
            return prefix + d
    raise AssertionError


class Pseudonymizer:
    def __init__(self, text: str, seed: Optional[int] = None):
        self.text_lower = text.lower()
        self.rng = random.Random(seed)
        self.fake = Faker("en_CA")
        self.fake.seed_instance(self.rng.randint(0, 2**31))
        self.used: set = set()
        self.name_tokens: Dict[str, str] = {}  # real name token -> fake token

    def _ok(self, value: str) -> bool:
        v = value.lower()
        return v not in self.used and v not in self.text_lower

    def _unique(self, make) -> str:
        for _ in range(200):
            v = make()
            if self._ok(v):
                self.used.add(v.lower())
                return v
        raise RuntimeError("could not create a unique fake value")

    # --- one generator per entity type ------------------------------------
    def person(self, real: str) -> str:
        tokens = real.split()
        # Reuse earlier choices, so "Sarah" after "Sarah Thompson" stays consistent.
        if all(t.lower() in self.name_tokens for t in tokens):
            return " ".join(self.name_tokens[t.lower()] for t in tokens)

        def make():
            if len(tokens) == 1:
                return self.fake.first_name()
            parts = [self.fake.first_name()]
            parts += [self.fake.first_name() for _ in tokens[1:-1]]  # middle names
            parts.append(self.fake.last_name())
            return " ".join(parts)

        while True:
            fake = self._unique(make)
            fake_tokens = fake.split()
            # a fake token must not collide with a real name token used elsewhere
            taken = {v.lower() for v in self.name_tokens.values()}
            words = set(re.findall(r"[a-z']+", self.text_lower))
            if all(ft.lower() not in words and ft.lower() not in taken and ft.lower() not in COMMON_WORD_NAMES
                   for t, ft in zip(tokens, fake_tokens) if t.lower() not in self.name_tokens):
                break
        for t, ft in zip(tokens, fake_tokens):
            if t.lower() in self.name_tokens:
                ft = self.name_tokens[t.lower()]
            self.name_tokens.setdefault(t.lower(), ft)
        return " ".join(self.name_tokens.get(t.lower(), ft) for t, ft in zip(tokens, fake_tokens))

    def email(self, real: str) -> str:
        local = real.split("@")[0].lower()
        domains = ["example.com", "example.org", "example.net"]
        tokens = {t: re.sub(r"[^a-z]", "", f.lower()) for t, f in self.name_tokens.items() if len(t) > 1}

        def swap(seg: str) -> str:
            if not seg:
                return seg
            if seg.isdigit():
                return str(self.rng.randint(1, 99))
            if len(seg) == 1:
                for t, f in tokens.items():
                    if t.startswith(seg) and f:
                        return f[0]  # an initial: "d.okafor" -> "j.alvarado"
            new, replaced = seg, False
            for t, f in sorted(tokens.items(), key=lambda x: -len(x[0])):
                if len(t) > 2 and t in new:
                    new, replaced = new.replace(t, f), True
            if replaced:
                return re.sub(r"\d+", lambda m: str(self.rng.randint(1, 99)), new)
            # Not linked to a known name: replace the whole piece, never keep real text.
            if len(seg) == 1:
                return self.rng.choice("abcdefghijklmnoprstw")
            return re.sub(r"[^a-z0-9]", "", self.fake.user_name()) or "user"

        def make():
            parts = re.split(r"([._-])", local)
            new_local = "".join(p if p in "._-" and p else swap(p) for p in parts)
            return f"{new_local}@{self.rng.choice(domains)}"

        return self._unique(make)

    def phone(self, real: str) -> str:
        m = re.search(r"\s*(?:x|ext\.?)\s*\d+$", real)
        base, ext = (real[: m.start()], real[m.start():]) if m else (real, "")
        digits = re.sub(r"\D", "", base)

        def make():
            area = self.rng.choice(["519", "226", "416", "647", "905", "613", "604", "403", "514", "778"])
            core = f"{area}55501{self.rng.randint(0, 99):02d}"
            new = ("1" + core) if len(digits) == 11 else core
            if len(new) != len(digits):  # unusual format: fall back to a standard one
                return f"({area}) 555-01{core[-2:]}"
            return _apply_digits(base, new) + ext

        return self._unique(make)

    def sin(self, real: str) -> str:
        def make():
            body = "0" + "".join(str(self.rng.randint(0, 9)) for _ in range(7))
            return _apply_digits(real, _luhn_complete(body))
        return self._unique(make)

    def card(self, real: str) -> str:
        digits = re.sub(r"\D", "", real)
        brand = ("amex" if digits[:2] in ("34", "37") else "visa" if digits[0] == "4"
                 else "mastercard" if digits[0] in "25" else "other")
        pool = [c for c in TEST_CARDS[brand] if len(c) == len(digits)] or [
            c for b in TEST_CARDS.values() for c in b if len(c) == len(digits)]
        def make():
            if pool:
                choice = self.rng.choice(pool)
            else:  # unusual length: Luhn-valid number in a test range
                choice = _luhn_complete("4000" + "".join(str(self.rng.randint(0, 9)) for _ in range(len(digits) - 5)))
            return _apply_digits(real, choice) if len(choice) == len(digits) else choice
        try:
            return self._unique(make)
        except RuntimeError:  # pool exhausted: allow a generated test-range number
            pool.clear()
            return self._unique(make)

    def postal(self, real: str) -> str:
        letters = "ABCEGHJKLMNPRSTVWXYZ"
        def make():
            code = (self.rng.choice("ZW") + str(self.rng.randint(0, 9)) + self.rng.choice(letters)
                    + str(self.rng.randint(0, 9)) + self.rng.choice(letters) + str(self.rng.randint(0, 9)))
            sep = real[3] if len(real) == 7 else ""
            out = code[:3] + sep + code[3:]
            return out if real.isupper() or not real.isalpha() else out.lower()
        return self._unique(make)

    def address(self, real: str) -> str:
        unit = re.match(r"((?:Unit|Apt|Suite)\s*)\d+[A-Z]?(,?\s+)", real)
        direction = re.search(r"\s(N|S|E|W|North|South|East|West)\b(?=\W*$|,)", real)
        def make():
            v = f"{self.rng.randint(1, 9999)} {self.fake.last_name()} {self.rng.choice(STREET_TYPES)}"
            if direction:
                v += " " + direction.group(1)
            if unit:
                v = f"{unit.group(1)}{self.rng.randint(1, 40)}{unit.group(2)}" + v
            return v
        return self._unique(make)

    def account(self, real: str) -> str:
        def make():
            return re.sub(r"\d", lambda m: str(self.rng.randint(0, 9)), real)
        return self._unique(make)

    def location(self, real: str) -> str:
        return self._unique(self.fake.city)

    def other(self, real: str) -> str:
        return "[REDACTED]"

    def make(self, entity: str, real: str) -> str:
        fn = {
            "PERSON": self.person, "EMAIL_ADDRESS": self.email, "PHONE_NUMBER": self.phone,
            "CA_SIN": self.sin, "CREDIT_CARD": self.card, "CA_POSTAL_CODE": self.postal,
            "STREET_ADDRESS": self.address, "ACCOUNT_ID": self.account, "LOCATION": self.location,
        }.get(entity, self.other)
        return fn(real)


def apply(text: str, detections: List[Detection], method: str = "pseudonymize", seed: Optional[int] = None) -> Dict:
    """Return {"text": safer prompt, "mapping": replacement -> original, "method": method}.

    For "redact" the mapping is empty: full redaction cannot be reversed.
    """
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}")
    dets = sorted(detections, key=lambda d: d.start)
    # Process people first so emails built from their names can reuse the fake names.
    order = sorted(dets, key=lambda d: (d.entity != "PERSON", -len(d.text.split()), d.start))
    ps = Pseudonymizer(text, seed) if method == "surrogate" else None
    counters: Dict[str, int] = {}
    chosen: Dict[tuple, str] = {}
    mapping: Dict[str, str] = {}
    for d in order:
        key = (d.entity, _normalize(d.entity, d.text))
        if key in chosen:
            continue
        if method == "redact":
            chosen[key] = REDACT_TOKEN
            continue
        if method == "pseudonymize":
            base = TAG_NAMES.get(d.entity, d.entity)
            counters[base] = counters.get(base, 0) + 1
            chosen[key] = f"[{base}_{counters[base]}]"
        else:
            chosen[key] = ps.make(d.entity, d.text)
        if chosen[key] != "[REDACTED]":
            mapping[chosen[key]] = d.text

    # Placeholders are numbered in reading order.
    if method == "pseudonymize":
        counters, renum, name_tag = {}, {}, {}

        def new_tag(entity):
            base = TAG_NAMES.get(entity, entity)
            counters[base] = counters.get(base, 0) + 1
            return f"[{base}_{counters[base]}]"

        singles = []
        for d in dets:  # pass 1, reading order: everything except one-word names
            key = (d.entity, _normalize(d.entity, d.text))
            toks = d.text.lower().split()
            if key in renum:
                continue
            if d.entity == "PERSON" and len(toks) == 1:
                singles.append((key, toks[0]))
                continue
            renum[key] = new_tag(d.entity)
            if d.entity == "PERSON":
                for t in toks:
                    name_tag.setdefault(t, renum[key])
        for key, tok in singles:  # pass 2: "Sarah" reuses the tag of "Sarah Thompson"
            if key not in renum:
                renum[key] = name_tag.get(tok) or new_tag("PERSON")
        new_map = {}
        for k, v in chosen.items():
            if v in mapping:
                new_map.setdefault(renum[k], mapping[v])
        mapping = new_map
        chosen = renum

    out, last = [], 0
    for d in dets:
        out.append(text[last:d.start])
        out.append(chosen[(d.entity, _normalize(d.entity, d.text))])
        last = d.end
    out.append(text[last:])

    # For pseudonyms, also let single fake name tokens map back ("Emily" -> "Sarah"),
    # because AI replies often shorten names.
    if method == "surrogate":
        for real_tok, fake_tok in ps.name_tokens.items():
            if len(fake_tok) > 2 and fake_tok not in mapping:
                orig = next((d.text.split()[i] for d in dets if d.entity == "PERSON"
                             for i, t in enumerate(d.text.split()) if t.lower() == real_tok), None)
                if orig:
                    mapping.setdefault(fake_tok, orig)
    return {"text": "".join(out), "mapping": mapping, "method": method}


def restore(text: str, mapping: Dict[str, str]) -> str:
    """Swap replacements back to the original values (longest first)."""
    if not mapping:
        return text
    pattern = re.compile("|".join(
        (r"(?<![\w@.])" + re.escape(k) + r"(?![\w@])") if k[0].isalnum() else re.escape(k)
        for k in sorted(mapping, key=len, reverse=True)))
    return pattern.sub(lambda m: mapping[m.group(0)], text)
