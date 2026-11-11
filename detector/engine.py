"""Detection engine (finding personal information).

What to replace it with lives in transform.py.

Three detection modes, so the evaluation can compare them:
  - "rules":  pattern recognizers only (regex + checksums + context words)
  - "ner":    spaCy named-entity recognition only
  - "hybrid": both (the default used by the web app)

Everything runs in-process on this machine. No text is sent anywhere.
"""
from . import offline  # noqa: F401  (must be imported before presidio_analyzer)

import re
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import Dict, List, Optional

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from .recognizers import custom_recognizers

# Entities the project treats as in scope (see proposal, Section 4, Phase 1).
ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CA_SIN",
    "CREDIT_CARD",
    "CA_POSTAL_CODE",
    "STREET_ADDRESS",
    "ACCOUNT_ID",
]

LABELS = {
    "PERSON": "Name",
    "EMAIL_ADDRESS": "Email",
    "PHONE_NUMBER": "Phone",
    "CA_SIN": "SIN",
    "CREDIT_CARD": "Card number",
    "CA_POSTAL_CODE": "Postal code",
    "STREET_ADDRESS": "Street address",
    "ACCOUNT_ID": "Account / record ID",
    "LOCATION": "City / place",  # manual additions only
    "OTHER": "Other sensitive detail",  # manual additions only
}

MODES = ("rules", "ner", "hybrid")
SPACY_MODEL = "en_core_web_lg"
DEFAULT_THRESHOLD = 0.4


@dataclass
class Detection:
    entity: str
    start: int
    end: int
    text: str
    score: float
    source: str  # which recognizer found it

    @property
    def label(self) -> str:
        return LABELS.get(self.entity, self.entity)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["label"] = self.label
        return d


@lru_cache(maxsize=None)
def _nlp_engine():
    provider = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
        }
    )
    return provider.create_engine()


@lru_cache(maxsize=None)
def get_analyzer(mode: str = "hybrid") -> AnalyzerEngine:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(languages=["en"])
    for rec in custom_recognizers():
        registry.add_recognizer(rec)

    is_ner = lambda r: r.name in ("SpacyRecognizer",)  # noqa: E731
    if mode == "rules":
        registry.recognizers = [r for r in registry.recognizers if not is_ner(r)]
    elif mode == "ner":
        registry.recognizers = [r for r in registry.recognizers if is_ner(r)]

    return AnalyzerEngine(registry=registry, nlp_engine=_nlp_engine(), supported_languages=["en"])


NER_SOURCES = {"SpacyRecognizer"}
LEADING_NON_NAMES = {
    "email", "call", "text", "tell", "ask", "remind", "contact", "dear", "hi", "hello",
    "hey", "thanks", "name", "patient", "customer", "client", "student", "employee", "mr", "mrs", "ms", "dr",
}


def _resolve_overlaps(dets: List[Detection]) -> List[Detection]:
    """Keep one detection where spans overlap.

    Pattern matches (structured, often checksum-validated) win over NER
    guesses, because NER tends to grab pieces of addresses and postal codes
    ("Ruth Place N", "Waterloo R5S6N4") and labelling them PERSON leaves the
    rest of the value unredacted. Among the same kind, the higher score wins
    (e.g. a Luhn-valid SIN beats a phone-number guess on the same digits).
    """
    ranked = sorted(dets, key=lambda d: (d.source in NER_SOURCES, -d.score, -(d.end - d.start), d.start))
    kept: List[Detection] = []
    for d in ranked:
        if all(d.end <= k.start or d.start >= k.end for k in kept):
            kept.append(d)
    return sorted(kept, key=lambda d: d.start)


def _after_street_number(text: str, start: int) -> bool:
    """True if the span follows a lone house number on the same line ("3117 ").

    A number at the end of a digit group (a SIN or phone on the previous line,
    "130 692 544 Name") does not count.
    """
    before = text[max(0, start - 30) : start]
    m = re.search(r"(?:^|[ \t,(])(\d{1,5})[ \t]+$", before)
    if not m:
        return False
    return not re.search(r"\d[ \t.-]?$", before[: m.start(1)])


def detect(
    text: str,
    mode: str = "hybrid",
    threshold: float = DEFAULT_THRESHOLD,
    entities: Optional[List[str]] = None,
) -> List[Detection]:
    if not text.strip():
        return []
    results = get_analyzer(mode).analyze(
        text=text,
        language="en",
        entities=entities or ENTITIES,
        score_threshold=threshold,
        return_decision_process=True,
    )
    dets = []
    for r in results:
        source = "?"
        if r.analysis_explanation is not None:
            source = r.analysis_explanation.recognizer
        span = text[r.start : r.end]
        # spaCy sometimes includes a trailing possessive or punctuation.
        while span and span[-1] in ".,;:'’" and r.entity_type == "PERSON":
            span = span[:-1]
            r.end -= 1
        if span.lower().endswith(("'s", "’s")) and r.entity_type == "PERSON":
            span = span[:-2]
            r.end -= 2
        if r.entity_type == "PERSON":
            # spaCy sometimes pulls a leading verb/greeting into the name ("Email Priya Raman").
            first, _, rest = span.partition(" ")
            if rest and first.lower().strip(",:") in LEADING_NON_NAMES:
                r.start += len(first) + 1
                span = rest
        if not span.strip():
            continue
        if r.entity_type == "PERSON" and source in NER_SOURCES:
            # NER sometimes labels numbers, postal codes or street names as people.
            if any(c.isdigit() for c in span):
                continue
            if _after_street_number(text, r.start):  # "3117 Ruth Place" is a street, not a person
                continue
        dets.append(Detection(r.entity_type, r.start, r.end, span, round(float(r.score), 2), source))
    return _resolve_overlaps(dets)


def _normalize(entity: str, value: str) -> str:
    if entity in ("PHONE_NUMBER", "CA_SIN", "CREDIT_CARD", "CA_POSTAL_CODE"):
        return "".join(c for c in value if c.isalnum()).upper()
    return " ".join(value.lower().split())
