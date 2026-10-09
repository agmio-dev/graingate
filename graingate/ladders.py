# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""Detail ladders: how precisely each field can be released.

Every field has a ladder of rungs from exact (rung 0) to withheld ("*").
Each coarser rung is a pure function of the finer one -- e.g. a pincode
always maps to the same zone -- so knowing a fine value always implies the
coarse value. GrainGate relies on that property to summarise everything an
agent has learned about a person with one rung per field.

Demo geography: a synthetic diagnostic-lab network across Bengaluru.
"""

PINCODE_TO_ZONE = {
    # North
    "560024": "Bengaluru North", "560032": "Bengaluru North",
    "560045": "Bengaluru North", "560064": "Bengaluru North",
    "560092": "Bengaluru North", "560094": "Bengaluru North",
    "560097": "Bengaluru North",
    # South
    "560004": "Bengaluru South", "560011": "Bengaluru South",
    "560041": "Bengaluru South", "560070": "Bengaluru South",
    "560076": "Bengaluru South", "560078": "Bengaluru South",
    "560085": "Bengaluru South", "560111": "Bengaluru South",
    # East
    "560008": "Bengaluru East", "560016": "Bengaluru East",
    "560017": "Bengaluru East", "560037": "Bengaluru East",
    "560038": "Bengaluru East", "560066": "Bengaluru East",
    "560093": "Bengaluru East", "560103": "Bengaluru East",
    # West
    "560010": "Bengaluru West", "560021": "Bengaluru West",
    "560040": "Bengaluru West", "560072": "Bengaluru West",
    "560079": "Bengaluru West", "560086": "Bengaluru West",
    "560096": "Bengaluru West",
}

PANEL_TO_FAMILY = {
    "Complete Blood Count": "Routine", "Lipid Profile": "Routine",
    "Diabetes Panel": "Routine", "Thyroid Profile": "Routine",
    "Vitamin Panel": "Routine",
    "Kidney Function": "Specialised", "Liver Function": "Specialised",
    "Cardiac Markers": "Specialised", "Tumour Markers": "Specialised",
    "Fertility Panel": "Specialised", "Hepatitis Panel": "Specialised",
}

FINDING_TO_GROUP = {
    "Anaemia": "Haematologic", "Raised WBC": "Haematologic",
    "High LDL": "Cardiovascular", "Low HDL": "Cardiovascular",
    "Raised troponin": "Cardiovascular", "Raised BNP": "Cardiovascular",
    "Diabetic-range HbA1c": "Metabolic", "Prediabetic HbA1c": "Metabolic",
    "Hypothyroid TSH": "Endocrine", "Hyperthyroid TSH": "Endocrine",
    "Vitamin D deficiency": "Nutritional", "B12 deficiency": "Nutritional",
    "Reduced eGFR": "Renal", "Proteinuria": "Renal",
    "Raised liver enzymes": "Hepatic", "Fatty-liver pattern": "Hepatic",
    "Raised PSA": "Oncologic", "Raised CA-125": "Oncologic",
    "Low AMH": "Reproductive", "Raised FSH": "Reproductive",
    "HBsAg reactive": "Infectious", "Anti-HCV reactive": "Infectious",
}

THERAPY_TO_CLASS = {
    "ferrous sulfate": "Supplement", "cholecalciferol": "Supplement",
    "methylcobalamin": "Supplement",
    "amoxicillin": "Antibiotic",
    "atorvastatin": "Lipid-lowering", "rosuvastatin": "Lipid-lowering",
    "metformin": "Antidiabetic", "insulin glargine": "Antidiabetic",
    "levothyroxine": "Thyroid", "carbimazole": "Thyroid",
    "furosemide": "Diuretic", "telmisartan": "Antihypertensive",
    "aspirin": "Antiplatelet", "ursodiol": "Hepatoprotective",
    "tamsulosin": "Urological", "paclitaxel": "Oncology",
    "letrozole": "Fertility", "clomiphene": "Fertility",
    "tenofovir": "Antiviral", "sofosbuvir": "Antiviral",
}

WITHHELD = "*"


def _age_band(a):
    lo = (int(a) // 10) * 10
    return f"{lo}-{lo + 9}"


# Fields an outside party could plausibly know or observe about a person.
IDENTIFYING = {
    "pincode": [
        lambda v: str(v),
        lambda v: PINCODE_TO_ZONE[str(v)],
        lambda v: "Bengaluru",
        lambda v: WITHHELD,
    ],
    "age": [lambda v: str(v), _age_band, lambda v: WITHHELD],
    "sex": [lambda v: str(v), lambda v: WITHHELD],
    "panel": [
        lambda v: str(v),
        lambda v: PANEL_TO_FAMILY[str(v)],
        lambda v: WITHHELD,
    ],
    "visit_month": [
        lambda v: f"M{int(v):02d}",
        lambda v: f"Q{(int(v) - 1) // 3 + 1}",
        lambda v: WITHHELD,
    ],
}

# Fields that must stay private unless a permitted purpose releases them.
PRIVATE = {
    "finding": [lambda v: str(v), lambda v: FINDING_TO_GROUP[str(v)],
                lambda v: WITHHELD],
    "therapy": [lambda v: str(v), lambda v: THERAPY_TO_CLASS[str(v)],
                lambda v: WITHHELD],
}

# The coarsest rung at which a private field still hurts if it leaks.
# "Reproductive" is already harmful, so ambiguity is measured at group level.
HARM_RUNG = {"finding": 1, "therapy": 1}

IDENTIFYING_FIELDS = list(IDENTIFYING.keys())
PRIVATE_FIELDS = list(PRIVATE.keys())
LADDERS = {**IDENTIFYING, **PRIVATE}


def top_rung(field):
    return len(LADDERS[field]) - 1


def coarsen(field, exact_value, rung):
    """Value of `field` at `rung`, computed from the exact value."""
    ladder = LADDERS[field]
    if rung < 0 or rung > top_rung(field):
        raise ValueError(f"rung {rung} out of range for {field}")
    return ladder[rung](exact_value)


def vocabulary():
    """Every phrase GrainGate itself may emit, mapped to (field, rung).

    Used by the summary verifier to recognise claims in free text without
    trusting the writer to declare them.
    """
    vocab = {}
    sources = {
        "pincode": PINCODE_TO_ZONE.keys(),
        "panel": PANEL_TO_FAMILY.keys(),
        "finding": FINDING_TO_GROUP.keys(),
        "therapy": THERAPY_TO_CLASS.keys(),
    }
    for field, values in sources.items():
        for v in values:
            for rung in range(top_rung(field)):
                vocab.setdefault(coarsen(field, v, rung), (field, rung))
    for a in range(0, 100):
        vocab.setdefault(str(a), ("age", 0))
        vocab.setdefault(_age_band(a), ("age", 1))
    for m in range(1, 13):
        vocab.setdefault(coarsen("visit_month", m, 0), ("visit_month", 0))
        vocab.setdefault(coarsen("visit_month", m, 1), ("visit_month", 1))
    return vocab
