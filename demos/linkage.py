# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""Linkage attack: piecing a person together from harmless answers.

The agent asks for each identifying field exactly, one at a time, and after
every answer keeps only the patients consistent with EVERYTHING it has been
told. Against a plain masker (names and IDs removed, every value exact) the
candidate list collapses toward one person. Behind GrainGate it stops at
the policy floor, which is never below k.

At every step the demo also checks that the attacker's candidate list is
exactly the crowd computed from the exposure ledger alone -- i.e. that the
ledger really is a complete record of what the agent knows.
"""

from graingate import ladders as LD
from graingate.exposure import ExposureLedger
from graingate.gate import Gate, crowd

PLAN = [("age", 0), ("sex", 0), ("pincode", 0), ("panel", 0),
        ("visit_month", 0)]


def _consistent(records, told):
    return [r for r in records
            if all(LD.coarsen(f, r[f], rung) == v for f, rung, v in told)]


def _groups(people):
    return {LD.coarsen("finding", r["finding"], LD.HARM_RUNG["finding"])
            for r in people}


def run(records, policy, target, agent="recruiter-agent"):
    gate = Gate(policy)
    ledger = ExposureLedger()
    told_gate, told_plain = [], []
    rows = []
    for step, (field, rung) in enumerate(PLAN, 1):
        d, value = gate.handle(agent, target, field, rung, ledger)
        if value is not None:
            told_gate.append((field, d.rung, value))
        told_plain.append((field, rung, LD.coarsen(field, target[field], rung)))

        gate_c = _consistent(records, told_gate)
        plain_c = _consistent(records, told_plain)
        ledger_c = crowd(records, target,
                         ledger.known(agent, target["patient_id"]))
        if {r["patient_id"] for r in gate_c} != \
                {r["patient_id"] for r in ledger_c}:
            raise AssertionError(f"ledger incomplete at step {step}")

        rows.append({
            "step": step, "field": field,
            "decision": d.action, "rung": d.rung, "value": value,
            "gate_candidates": len(gate_c),
            "plain_candidates": len(plain_c),
            "gate_groups": len(_groups(gate_c)),
            "plain_groups": len(_groups(plain_c)),
            "plain_group_values": sorted(_groups(plain_c)),
        })
    return rows, ledger
