# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""Safe summaries: free text written from released fields only, then checked.

GrainGate never tries to clean up the lab's own notes. Instead, outgoing
text is WRITTEN from the fields the agent has already been given, and a
verifier reads the finished text back before it leaves:

  - every recognised phrase becomes a claim (field, rung, value), and the
    claim must match what the exposure ledger allows -- same value, no
    finer than the rung already released;
  - every word that is neither template wording nor a recognised phrase is
    rejected as unrecognised content (fail-closed).

The verifier extracts claims from the text itself; it does not trust the
writer to say what it wrote. The same check blocks made-up facts: a claim
with no ledger entry fails exactly like a leaked one.
"""

import math
import re

from . import ladders as LD

SEX_WORDS = {"female": "F", "male": "M"}
SEX_DISPLAY = {v: k for k, v in SEX_WORDS.items()}

TEMPLATE = {
    "opening": "Pre-screening summary:",
    "sex": "{} candidate,",
    "age": "aged {},",
    "pincode": "from {},",
    "panel": "{} panel,",
    "finding": "finding group {},",
    "therapy": "on {} therapy.",
    "closing": "Eligible for site contact.",
}
TEMPLATE_WORDS = {
    w.lower() for part in TEMPLATE.values()
    for w in re.findall(r"[A-Za-z]+", part.replace("{}", ""))
}

_VOCAB = LD.vocabulary()
_PHRASES = sorted(list(_VOCAB) + list(SEX_WORDS), key=len, reverse=True)
_PHRASE_RE = re.compile(
    r"(?<![\w.\-])(" + "|".join(re.escape(p) for p in _PHRASES) + r")(?![\w\-]|\.\d)")


def released_view(record, agent, ledger):
    """field -> (rung, value) for everything the agent has been given."""
    return {f: (r, LD.coarsen(f, record[f], r))
            for f, r in ledger.known(agent, record["patient_id"]).items()
            if r != math.inf}


def write_summary(view):
    """Template writer. Input is the released view and nothing else."""
    parts = [TEMPLATE["opening"]]
    for field in ["sex", "age", "pincode", "panel", "finding", "therapy"]:
        if field in view:
            _, value = view[field]
            shown = SEX_DISPLAY.get(value, value) if field == "sex" else value
            parts.append(TEMPLATE[field].format(shown))
    parts.append(TEMPLATE["closing"])
    return " ".join(parts)


def write_summary_leaky(view, record):
    """Imitates a contaminated writer that also read the lab note."""
    note = record["note"]
    occupation = note.split(" a ", 1)[1].split(" from", 1)[0]
    value = re.search(r"measured value ([\d.]+)", note).group(1)
    return (write_summary(view) +
            f" Patient is a {occupation}, measured value {value},"
            f" finding {record['finding']}.")


def extract_claims(text):
    """Deterministically read claims back out of a finished summary."""
    claims = []
    for m in _PHRASE_RE.finditer(text):
        phrase = m.group(1)
        if phrase in SEX_WORDS:
            claims.append({"field": "sex", "rung": 0,
                           "value": SEX_WORDS[phrase]})
        else:
            field, rung = _VOCAB[phrase]
            claims.append({"field": field, "rung": rung, "value": phrase})
    leftover = _PHRASE_RE.sub(" ", text)
    unknown = [w for w in re.findall(r"[A-Za-z]+|\d+(?:\.\d+)?", leftover)
               if w.lower() not in TEMPLATE_WORDS]
    return claims, unknown


def verify(text, record, agent, ledger):
    """Pass iff every claim is allowed and nothing unrecognised remains."""
    claims, unknown = extract_claims(text)
    violations = []
    for c in claims:
        field, rung, value = c["field"], c["rung"], c["value"]
        allowed = ledger.rung(agent, record["patient_id"], field)
        if allowed == math.inf:
            violations.append((field, f"'{value}': field was never released"))
        elif rung < allowed:
            violations.append(
                (field, f"'{value}': rung {rung} is finer than released rung {allowed}"))
        elif LD.coarsen(field, record[field], rung) != value:
            violations.append((field, f"'{value}': does not match the record"))
    if unknown:
        violations.append(("text", "unrecognised content: " + " ".join(unknown)))
    return len(violations) == 0, claims, violations
