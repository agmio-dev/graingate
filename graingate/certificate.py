# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""Release certificate: evidence that travels with an outgoing summary.

Binds the policy version, the parameters, what was released, the head of
the ledger hash chain, and every claim in the summary under one hash. A
receiving compliance team can check it against the published policy
without access to any patient data.
"""

import hashlib
import json
import math
from datetime import datetime, timezone


def build(policy, ledger, agent, patient_id, claims, summary_ok,
          issued_at=None):
    released = {f: (None if r == math.inf else r)
                for f, r in ledger.known(agent, patient_id).items()}
    cert = {
        "type": "graingate-release-certificate",
        "issued_at": issued_at or datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "patient": patient_id,
        "policy_version": policy.version,
        "parameters": {"k": policy.k, "l": policy.l},
        "released_rungs": released,
        "ledger_head": ledger.head,
        "ledger_intact": ledger.chain_intact(),
        "claims": claims,
        "summary_check": "pass" if summary_ok else "fail",
    }
    cert["certificate_hash"] = hashlib.sha256(
        json.dumps(cert, sort_keys=True).encode()).hexdigest()
    return cert


def check(cert):
    """Recompute the certificate hash (detects any edit to the file)."""
    body = {k: v for k, v in cert.items() if k != "certificate_hash"}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest() == \
        cert.get("certificate_hash")
