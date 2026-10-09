# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""The runtime gate.

Every request an agent makes -- "give me field F at rung R for patient P" --
gets one of three answers:

  release   the request is already at or above the safe floor
  coarsen   release the field, but at the floor rung instead
  withhold  the field is withheld entirely by the policy

The decision is a lookup in the published release policy. It never looks
at the patient's record or at the rest of the data, so every patient gets
the same decision for the same request. A withheld answer therefore says
nothing about the patient that the policy didn't already say about
everyone. The record is read only AFTER the decision, to produce the value.
"""

import math
from dataclasses import dataclass

from . import ladders as LD

RELEASE, COARSEN, WITHHOLD = "release", "coarsen", "withhold"

# Purposes under which private fields may be released (at harm-level only).
# The decision depends on the purpose and the policy -- never on the patient.
PERMITTED_PURPOSES = {"consented-prescreening"}


@dataclass
class Decision:
    action: str
    rung: int            # rung released; -1 when withheld
    rule: str


def crowd(records, patient, known):
    """Everyone indistinguishable from `patient` given what is known."""
    want = {f: LD.coarsen(f, patient[f], r)
            for f, r in known.items() if r != math.inf}
    return [r for r in records
            if all(LD.coarsen(f, r[f], known[f]) == v for f, v in want.items())]


class Gate:
    def __init__(self, policy):
        self.policy = policy

    def decide(self, field, requested_rung):
        """Pure function of (field, requested rung, policy). No patient."""
        floor = self.policy.floor[field]
        v = self.policy.version
        if floor >= LD.top_rung(field):
            return Decision(WITHHOLD, -1, f"{v}/{field}/withheld")
        if requested_rung >= floor:
            return Decision(RELEASE, requested_rung, f"{v}/{field}/ok")
        return Decision(COARSEN, floor, f"{v}/{field}/floor-{floor}")

    def handle(self, agent, record, field, requested_rung, ledger):
        d = self.decide(field, requested_rung)
        value = None
        if d.action != WITHHOLD:
            value = LD.coarsen(field, record[field], d.rung)
            ledger.record_release(agent, record["patient_id"], field, d.rung)
        ledger.log(agent, record["patient_id"], field, requested_rung,
                   d.action, d.rung, d.rule)
        return d, value

    def decide_private(self, purpose):
        """Whether private fields may be released for this purpose."""
        v = self.policy.version
        if purpose not in PERMITTED_PURPOSES:
            return Decision(WITHHOLD, -1, f"{v}/private/purpose-not-permitted")
        if not self.policy.private_release_allowed:
            return Decision(WITHHOLD, -1, f"{v}/private/not-allowed-by-policy")
        return Decision(RELEASE, 1, f"{v}/private/purpose:{purpose}")

    def release_private(self, agent, record, purpose, ledger):
        """Release ALL private fields together, at harm level, or none."""
        d = self.decide_private(purpose)
        out = {}
        for field in LD.PRIVATE_FIELDS:
            rung = LD.HARM_RUNG[field]
            if d.action == RELEASE:
                out[field] = LD.coarsen(field, record[field], rung)
                ledger.record_release(agent, record["patient_id"], field, rung)
            ledger.log(agent, record["patient_id"], field, rung, d.action,
                       rung if d.action == RELEASE else -1, d.rule)
        return d, out
