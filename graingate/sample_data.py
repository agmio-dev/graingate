# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""Synthetic diagnostic-lab network (one data snapshot).

Models a chain of collection centres across Bengaluru. Each record is one
patient's most recent visit: who they are (identifying fields), what was
ordered, and what was found. Findings and therapies depend on the panel.

Two small, sensitive groups are planted on purpose, because they are where
naive anonymisation fails:
  - a fertility-testing group from a partner IVF clinic, concentrated in a
    few East Bengaluru pincodes, and
  - a hepatitis-screening group from a partner liver clinic, concentrated
    in two West Bengaluru pincodes.
Inside each group everyone shares the same finding group, so learning that
someone belongs to the group is the same as learning their result.

No real patient data is used anywhere.
"""

import random

from .ladders import PINCODE_TO_ZONE

PANEL_PROFILES = {
    # panel: (weight, [(finding, therapy), ...])
    "Complete Blood Count": (14, [("Anaemia", "ferrous sulfate"),
                                  ("Raised WBC", "amoxicillin")]),
    "Lipid Profile": (14, [("High LDL", "atorvastatin"),
                           ("Low HDL", "rosuvastatin")]),
    "Diabetes Panel": (16, [("Diabetic-range HbA1c", "metformin"),
                            ("Prediabetic HbA1c", "metformin"),
                            ("Diabetic-range HbA1c", "insulin glargine")]),
    "Thyroid Profile": (10, [("Hypothyroid TSH", "levothyroxine"),
                             ("Hyperthyroid TSH", "carbimazole")]),
    "Vitamin Panel": (9, [("Vitamin D deficiency", "cholecalciferol"),
                          ("B12 deficiency", "methylcobalamin")]),
    "Kidney Function": (8, [("Reduced eGFR", "furosemide"),
                            ("Proteinuria", "telmisartan")]),
    "Liver Function": (8, [("Raised liver enzymes", "ursodiol"),
                           ("Fatty-liver pattern", "ursodiol")]),
    "Cardiac Markers": (7, [("Raised troponin", "aspirin"),
                            ("Raised BNP", "furosemide")]),
    "Tumour Markers": (6, [("Raised PSA", "tamsulosin"),
                           ("Raised CA-125", "paclitaxel")]),
    # Planted groups only (weight 0 = never drawn at random)
    "Fertility Panel": (0, [("Low AMH", "letrozole"),
                            ("Raised FSH", "clomiphene")]),
    "Hepatitis Panel": (0, [("HBsAg reactive", "tenofovir"),
                            ("Anti-HCV reactive", "sofosbuvir")]),
}

FERTILITY_PINCODES = ["560038", "560008", "560017"]   # near the IVF partner
HEPATITIS_PINCODES = ["560010", "560040"]             # near the liver clinic

OCCUPATIONS = ["software engineer", "school teacher", "bank officer",
               "cab driver", "nurse", "shop owner"]
FAMILY_NOTES = ["spouse also tested here", "sibling under treatment",
                "mother referred by same doctor"]


def generate(n=12000, seed=42, fertility_fraction=0.010,
             hepatitis_fraction=0.006):
    rng = random.Random(seed)
    pincodes = list(PINCODE_TO_ZONE.keys())
    panels, weights = [], []
    for p, (w, _) in PANEL_PROFILES.items():
        if w > 0:
            panels.append(p)
            weights.append(w)

    n_fert = int(n * fertility_fraction)
    n_hep = int(n * hepatitis_fraction)

    records = []
    for i in range(n):
        if i < n_fert:
            panel = "Fertility Panel"
            pincode = rng.choice(FERTILITY_PINCODES)
            sex = "F"
            age = rng.randint(25, 40)
        elif i < n_fert + n_hep:
            panel = "Hepatitis Panel"
            pincode = rng.choice(HEPATITIS_PINCODES)
            sex = rng.choice(["M", "F"])
            age = rng.randint(20, 60)
        else:
            panel = rng.choices(panels, weights=weights)[0]
            pincode = rng.choice(pincodes)
            sex = rng.choice(["M", "F"])
            age = min(90, max(1, int(rng.gauss(44, 17))))
        finding, therapy = rng.choice(PANEL_PROFILES[panel][1])
        if finding == "Raised PSA":
            sex = "M"
        elif finding == "Raised CA-125":
            sex = "F"
        records.append({
            "patient_id": f"L-{i + 1:05d}",
            "age": age,
            "sex": sex,
            "pincode": pincode,
            "panel": panel,
            "visit_month": rng.randint(1, 12),
            "finding": finding,
            "therapy": therapy,
            # Free-text requisition note. Holds details that must never
            # leave the lab: occupation, the exact measured value, family.
            "note": (f"Patient is a {rng.choice(OCCUPATIONS)} from {pincode}; "
                     f"measured value {rng.randint(5, 95) / 10:.1f}; "
                     f"{rng.choice(FAMILY_NOTES)}."),
        })
    rng.shuffle(records)
    return records
