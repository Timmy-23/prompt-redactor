"""Generate a synthetic, labelled test set of GenAI prompts.

Every personal detail is fake (Faker) and inserted by this script, so its exact
position is known and serves as ground truth. No real personal information.

    python eval/generate.py --n 300 --seed 6550 --out eval/data/test_set.jsonl

Each line: {"id", "category", "n_people", "text", "entities": [{"type","start","end","value","meta"}]}
Categories (prompt types): draft, summarize, advice, data, negative (no personal information).
"""
import argparse
import json
import random
import re
from pathlib import Path

from faker import Faker

# Name locales, so recall can be compared across name origins (bias check).
NAME_LOCALES = {
    "en_CA": "Anglo-Canadian",
    "fr_CA": "French-Canadian",
    "en_IN": "South Asian",
    "es_MX": "Hispanic",
    "zh_CN": "Chinese (romanized)",
    "en_NG": "Nigerian",
}
AREA_CODES = ["519", "226", "548", "416", "647", "437", "905", "289", "613", "343", "705", "604", "403", "514"]
STREET_TYPES = ["Street", "St", "Road", "Rd", "Avenue", "Ave", "Drive", "Dr", "Crescent", "Court", "Lane", "Way", "Boulevard", "Blvd", "Place"]
DIRECTIONS = ["", "", "", " N", " S", " E", " W"]
ID_PREFIXES = ["CUST", "ACC", "PT", "STU", "EMP"]
CITIES = ["Guelph", "Kitchener", "Waterloo", "Toronto", "Hamilton", "Ottawa", "London", "Mississauga"]


class Gen:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        Faker.seed(seed)
        self.fakers = {loc: Faker(loc) for loc in NAME_LOCALES}
        self.f = self.fakers["en_CA"]

    # ---- value generators: return (value, meta)
    def person(self):
        loc = self.rng.choice(list(NAME_LOCALES))
        fk = self.fakers[loc]
        if loc == "zh_CN":  # romanize: Faker zh_CN has pinyin helpers
            first = fk.first_romanized_name()
            last = fk.last_romanized_name()
        else:
            first, last = fk.first_name(), fk.last_name()
        return f"{first} {last}", {"origin": NAME_LOCALES[loc], "first": first}

    def email(self, name=None):
        if name:
            base = re.sub(r"[^a-z.]", "", name.lower().replace(" ", self.rng.choice([".", "_", ""])))
            base = base or self.f.user_name()
        else:
            base = self.f.user_name()
        return f"{base}@{self.rng.choice(['example.com', 'example.org', 'example.net'])}", {}

    def phone(self):
        a = self.rng.choice(AREA_CODES)
        ex = f"{self.rng.randint(2, 9)}{self.rng.randint(0, 9)}{self.rng.randint(0, 9)}"
        while ex == "555":
            ex = f"{self.rng.randint(2, 9)}{self.rng.randint(0, 9)}{self.rng.randint(0, 9)}"
        ln = f"{self.rng.randint(0, 9999):04d}"
        fmt = self.rng.choice(["({a}) {e}-{l}", "{a}-{e}-{l}", "{a}.{e}.{l}", "+1 {a} {e} {l}", "{a} {e} {l}"])
        return fmt.format(a=a, e=ex, l=ln), {"format": fmt}

    def sin(self):
        s = self.f.ssn()  # Faker en_CA SINs are Luhn-valid, "123 456 789"
        if self.rng.random() < 0.3:
            s = s.replace(" ", "-")
        return s, {}

    def card(self):
        n = self.f.credit_card_number(card_type=self.rng.choice(["visa16", "mastercard", "amex"]))
        if len(n) == 16 and self.rng.random() < 0.6:
            n = " ".join(n[i:i + 4] for i in range(0, 16, 4))
        return n, {}

    def postal(self):
        p = self.f.postcode()
        if self.rng.random() < 0.2:
            p = p.replace(" ", "")
        return p, {}

    def address(self):
        num = self.rng.randint(1, 9999)
        name = self.rng.choice([self.f.last_name(), self.f.first_name(), self.rng.choice(["Maple", "King", "Queen", "Elm", "Victoria", "Gordon", "Stone"])])
        v = f"{num} {name} {self.rng.choice(STREET_TYPES)}{self.rng.choice(DIRECTIONS)}"
        if self.rng.random() < 0.15:
            v = f"Unit {self.rng.randint(1, 40)}, {v}"
        return v, {}

    def account(self):
        p = self.rng.choice(ID_PREFIXES)
        if self.rng.random() < 0.3:
            return f"{p}-{self.rng.randint(2019, 2026)}-{self.rng.randint(100, 99999):05d}", {}
        return f"{p}-{self.rng.randint(10000, 9999999)}", {}


# Prompt types follow the proposal (Phase 3): everyday tasks such as drafting an
# email, summarizing a record or asking for advice, plus data handling. Several
# templates involve two or more people, where telling people apart matters.
TEMPLATES = {
    "draft": [
        "Can you make this email sound more professional?\n\nHi {PERSON},\nThanks for calling about your account {ACCOUNT_ID}. I've updated your phone number to {PHONE_NUMBER} and we'll send the confirmation to {EMAIL_ADDRESS}. Let me know if anything else is wrong.\n\nBest,\n{PERSON}",
        "Rewrite this so it's friendlier: Dear {PERSON}, your payment with card {CREDIT_CARD} was declined. Please call us at {PHONE_NUMBER} or reply to {EMAIL_ADDRESS}.",
        "Write a short email from me ({PERSON}) to my manager {PERSON} asking to swap my Friday shift with {PERSON}. My number is {PHONE_NUMBER} if she wants to call.",
        "Draft a reply to {PERSON} confirming their appointment on Tuesday. Send it to {EMAIL_ADDRESS}. Their student number is {ACCOUNT_ID}.",
        "Help me write a reference letter for my former employee {PERSON}. Mention that she worked closely with {PERSON} on the inventory project. She can be reached at {PHONE_NUMBER}.",
        "Translate to French: Hello {PERSON}, we received your documents. Your file number is {ACCOUNT_ID}. Call {PHONE_NUMBER} with questions.",
    ],
    "summarize": [
        "Summarize this thread in two sentences.\nFrom: {PERSON} <{EMAIL_ADDRESS}>\nTo: {PERSON} <{EMAIL_ADDRESS}>\nSubject: Delivery to {STREET_ADDRESS}\nThe parcel for {STREET_ADDRESS}, {CITY} {CA_POSTAL_CODE} came back. Can you confirm the address with the customer?",
        "Clean up this patient intake note and summarize it: patient {PERSON}, ID {ACCOUNT_ID}, lives at {STREET_ADDRESS}, {CITY}, phone {PHONE_NUMBER}, emergency contact {PERSON} {PHONE_NUMBER}.",
        "Summarize this meeting note in three bullet points: {PERSON} will send the updated contract to {PERSON} by Friday. {PERSON} asked that invoices go to {EMAIL_ADDRESS} instead of the old address.",
        "Summarize this customer complaint: {PERSON} (account {ACCOUNT_ID}) says she was charged twice on card {CREDIT_CARD} and wants a call back at {PHONE_NUMBER}.",
        "Give me a one-paragraph summary of this incident report: on Monday {PERSON} reported that a package addressed to {PERSON} at {STREET_ADDRESS}, {CITY} {CA_POSTAL_CODE} was left at the wrong door.",
    ],
    "advice": [
        "My SIN is {CA_SIN} and my postal code is {CA_POSTAL_CODE}. What tax forms do I need for a first job in Ontario?",
        "My coworker {PERSON} keeps taking credit for my work in meetings with our boss {PERSON}. How should I bring this up without making it awkward?",
        "I'm {PERSON} and my landlord {PERSON} hasn't returned my deposit for the unit at {STREET_ADDRESS}. What are my options in Ontario?",
        "My card {CREDIT_CARD} was charged by a company I've never heard of. My bank's number is on file as {PHONE_NUMBER}. What should I do first?",
        "Should I tell my team lead {PERSON} that {PERSON} has been missing deadlines, or talk to {PERSON} directly first?",
        "My student account {ACCOUNT_ID} was locked after I changed my email to {EMAIL_ADDRESS}. How do I usually get this fixed?",
    ],
    "data": [
        "Sort these customer records by postal code:\n{PERSON}, {EMAIL_ADDRESS}, {PHONE_NUMBER}, {STREET_ADDRESS}, {CITY} ON {CA_POSTAL_CODE}\n{PERSON}, {EMAIL_ADDRESS}, {PHONE_NUMBER}, {STREET_ADDRESS}, {CITY} ON {CA_POSTAL_CODE}\n{PERSON}, {EMAIL_ADDRESS}, {PHONE_NUMBER}, {STREET_ADDRESS}, {CITY} ON {CA_POSTAL_CODE}",
        "Turn this into a table with columns Name, ID, Phone:\n- {PERSON} ({ACCOUNT_ID}) {PHONE_NUMBER}\n- {PERSON} ({ACCOUNT_ID}) {PHONE_NUMBER}\n- {PERSON} ({ACCOUNT_ID}) {PHONE_NUMBER}\n- {PERSON} ({ACCOUNT_ID}) {PHONE_NUMBER}",
        "Find duplicates in this list:\n{ACCOUNT_ID} | {PERSON} | {EMAIL_ADDRESS}\n{ACCOUNT_ID} | {PERSON} | {EMAIL_ADDRESS}\n{ACCOUNT_ID} | {PERSON} | {EMAIL_ADDRESS}",
        "Check which of these payroll entries is missing data:\n{PERSON} SIN {CA_SIN} {EMAIL_ADDRESS}\n{PERSON} SIN {CA_SIN}\n{PERSON} {EMAIL_ADDRESS} SIN {CA_SIN}",
        "Is this refund request complete? Customer {PERSON}, account {ACCOUNT_ID}, card {CREDIT_CARD}, contact {EMAIL_ADDRESS}.",
    ],
    # No personal information: measures false alarms. Includes decoys that look
    # like identifiers (order numbers, dates, prices, SKUs, versions).
    "negative": [
        "Write a SQL query that returns orders over $250 placed between 2024-01-01 and 2024-03-31, grouped by month.",
        "Order 4471 shipped on March 2 with 3 items (SKU 88213, 99120, 10442). Write a short shipping update for our newsletter.",
        "Explain the difference between version 3.11.4 and 3.12.0 of Python in simple terms.",
        "Our store had 1,284 visitors and 312 sales last week, up 14%. Write a two-line summary for the team.",
        "Summarize the main points of PIPEDA's ten fair information principles.",
        "Convert 2,500 square feet to square metres and explain the formula.",
        "Write a regex that matches invoice numbers like INV-2024-00031.",
        "Suggest five names for a coffee shop near the University of Guelph.",
        "Rewrite this: the meeting moved from 10:30 to 14:00 on Friday, room 2208.",
        "What is a good way to back up 500 GB of photos? I have a 2 TB drive.",
    ],
}


def render(template: str, g: Gen):
    ents, out, pos = [], [], 0
    # reuse the same person/email occasionally so consistent placeholders matter
    cache_people = []
    for m in re.finditer(r"\{([A-Z_]+)\}", template):
        out.append(template[pos:m.start()])
        offset = sum(len(s) for s in out)
        kind = m.group(1)
        meta = {}
        if kind == "PERSON":
            if cache_people and g.rng.random() < 0.15:
                value, meta = g.rng.choice(cache_people)
            else:
                value, meta = g.person()
                cache_people.append((value, meta))
        elif kind == "EMAIL_ADDRESS":
            name = cache_people[-1][0] if cache_people and g.rng.random() < 0.6 else None
            value, meta = g.email(name)
        elif kind == "PHONE_NUMBER":
            value, meta = g.phone()
        elif kind == "CA_SIN":
            value, meta = g.sin()
        elif kind == "CREDIT_CARD":
            value, meta = g.card()
        elif kind == "CA_POSTAL_CODE":
            value, meta = g.postal()
        elif kind == "STREET_ADDRESS":
            value, meta = g.address()
        elif kind == "ACCOUNT_ID":
            value, meta = g.account()
        elif kind == "CITY":  # quasi-identifier, deliberately NOT labelled (out of scope)
            value = g.rng.choice(CITIES)
            out.append(value)
            pos = m.end()
            continue
        else:
            raise ValueError(kind)
        out.append(value)
        ents.append({"type": kind, "start": offset, "end": offset + len(value), "value": value, "meta": meta})
        pos = m.end()
    out.append(template[pos:])
    text = "".join(out)
    for e in ents:
        assert text[e["start"]:e["end"]] == e["value"]
    return text, ents


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=6550)
    ap.add_argument("--out", default=str(Path(__file__).parent / "data" / "test_set.jsonl"))
    args = ap.parse_args()
    g = Gen(args.seed)
    weights = {"draft": 0.22, "summarize": 0.22, "advice": 0.20, "data": 0.21, "negative": 0.15}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        for i in range(args.n):
            cat = g.rng.choices(list(weights), weights=list(weights.values()))[0]
            text, ents = render(g.rng.choice(TEMPLATES[cat]), g)
            n_people = len({e["value"] for e in ents if e["type"] == "PERSON"})
            fh.write(json.dumps({"id": i, "category": cat, "n_people": n_people, "text": text,
                                 "entities": ents}, ensure_ascii=False) + "\n")
    print(f"Wrote {args.n} prompts to {args.out}")


if __name__ == "__main__":
    main()
