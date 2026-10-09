# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""Exposure ledger: what each agent already knows about each patient.

Keyed by (agent, patient). For every field it keeps the finest rung that
agent has ever received. Rungs only ever get finer, never coarser, so the
ledger is a complete summary of the agent's knowledge: anything it learned
earlier at a coarser rung is implied by the finest rung.

Every gate decision -- including every withheld request -- is appended to
a SHA-256 hash chain, so the record cannot be edited after the fact.
"""

import hashlib
import json
import math

GENESIS = "GENESIS"


class ExposureLedger:
    def __init__(self):
        self._known = {}            # (agent, patient) -> {field: rung}
        self.events = []
        self._head = GENESIS

    # ---------------------------------------------------------- knowledge
    def known(self, agent, patient):
        """field -> finest rung released so far (absent = nothing)."""
        return dict(self._known.get((agent, patient), {}))

    def rung(self, agent, patient, field):
        return self._known.get((agent, patient), {}).get(field, math.inf)

    def record_release(self, agent, patient, field, rung):
        entry = self._known.setdefault((agent, patient), {})
        entry[field] = min(entry.get(field, math.inf), rung)
        return entry[field]

    # ----------------------------------------------------------- evidence
    def log(self, agent, patient, field, requested_rung, decision,
            released_rung, rule):
        event = {
            "seq": len(self.events),
            "agent": agent,
            "patient": patient,
            "field": field,
            "requested_rung": requested_rung,
            "decision": decision,
            "released_rung": released_rung,
            "rule": rule,
        }
        self._head = hashlib.sha256(
            (self._head + json.dumps(event, sort_keys=True)).encode()
        ).hexdigest()
        event["hash"] = self._head
        self.events.append(event)
        return event

    @property
    def head(self):
        return self._head

    def chain_intact(self):
        head = GENESIS
        for event in self.events:
            body = {k: v for k, v in event.items() if k != "hash"}
            head = hashlib.sha256(
                (head + json.dumps(body, sort_keys=True)).encode()).hexdigest()
            if head != event["hash"]:
                return False
        return head == self._head
