# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""GrainGate test suite.

Each test names the product property it checks.
Run: python -m pytest tests/ -q
"""

import math
import random

import pytest

from graingate import ladders as LD
from graingate.certificate import build as build_certificate
from graingate.certificate import check as check_certificate
from graingate.exposure import ExposureLedger
from graingate.gate import COARSEN, RELEASE, WITHHOLD, Gate, crowd
from graingate.policy import compile_policy, verify_policy
from graingate.sample_data import generate
from graingate.summary import (extract_claims, released_view, verify,
                               write_summary, write_summary_leaky)
from demos import linkage

K, L, N, SEED = 15, 3, 4000, 7
AGENT = "recruiter-agent"


@pytest.fixture(scope="module")
def records():
    return generate(n=N, seed=SEED)


@pytest.fixture(scope="module")
def policy(records):
    return compile_policy(records, k=K, l=L)


@pytest.fixture(scope="module")
def target(records):
    fert = [r for r in records if r["panel"] == "Fertility Panel"]
    assert fert, "planted fertility group missing"
    return fert[0]


def _session(policy, target, private_purpose=None):
    gate, led = Gate(policy), ExposureLedger()
    for f in LD.IDENTIFYING_FIELDS:
        gate.handle(AGENT, target, f, 0, led)
    if private_purpose:
        gate.release_private(AGENT, target, private_purpose, led)
    return gate, led


# ------------------------------------------------------------ ladders ---
def test_ladders_are_consistent(records):
    """A fine value always determines its coarser values."""
    sample = random.Random(0).sample(records, 200)
    for f in LD.LADDERS:
        top = LD.top_rung(f)
        for fine in range(top):
            for coarse in range(fine + 1, top + 1):
                seen = {}
                for r in sample:
                    a = LD.coarsen(f, r[f], fine)
                    b = LD.coarsen(f, r[f], coarse)
                    assert seen.setdefault(a, b) == b, (f, fine, coarse)


# ------------------------------------------------------------- policy ---
def test_policy_is_safe(records, policy):
    ok, smallest, amb = verify_policy(records, policy)
    assert ok and smallest >= K and amb >= L


def test_policy_falls_back_when_private_release_cannot_be_safe():
    tiny = generate(n=60, seed=1)
    p = compile_policy(tiny, k=50, l=1)
    assert p.private_release_allowed is False
    ok, smallest, _ = verify_policy(tiny, p)
    assert ok and smallest >= 50


def test_published_policy_has_no_group_statistics(policy):
    assert "smallest_crowd" not in policy.to_json()


# --------------------------------------------------------------- gate ---
def test_gate_decisions_match_policy(policy):
    gate = Gate(policy)
    for f in LD.IDENTIFYING_FIELDS:
        floor = policy.floor[f]
        for rung in range(LD.top_rung(f) + 1):
            d = gate.decide(f, rung)
            if floor >= LD.top_rung(f):
                assert d.action == WITHHOLD
            elif rung >= floor:
                assert d.action == RELEASE and d.rung == rung
            else:
                assert d.action == COARSEN and d.rung == floor


def test_same_decisions_for_every_patient(records, policy):
    """Decisions never depend on whose record is asked about."""
    gate = Gate(policy)
    reference = None
    for p in random.Random(1).sample(records, 300):
        led = ExposureLedger()
        seen = []
        for f in LD.IDENTIFYING_FIELDS:
            for rung in range(LD.top_rung(f) + 1):
                d, _ = gate.handle(AGENT, p, f, rung, led)
                seen.append((f, rung, d.action, d.rung, d.rule))
        reference = reference or seen
        assert seen == reference


def test_private_release_needs_a_permitted_purpose(policy, target):
    _, led = _session(policy, target, private_purpose="marketing")
    assert "finding" not in led.known(AGENT, target["patient_id"])
    _, led = _session(policy, target, private_purpose="consented-prescreening")
    known = led.known(AGENT, target["patient_id"])
    assert known["finding"] == LD.HARM_RUNG["finding"]
    assert known["therapy"] == LD.HARM_RUNG["therapy"]


# ------------------------------------------------------------- ledger ---
def test_ledger_only_gets_finer_and_detects_tampering():
    led = ExposureLedger()
    led.record_release("a", "p", "age", 1)
    led.record_release("a", "p", "age", 2)
    assert led.rung("a", "p", "age") == 1
    led.record_release("a", "p", "age", 0)
    assert led.rung("a", "p", "age") == 0
    for i in range(5):
        led.log("a", "p", "age", 0, RELEASE, 0, f"r{i}")
    assert led.chain_intact()
    led.events[2]["decision"] = WITHHOLD
    assert not led.chain_intact()


# ----------------------------------------------------- linkage attack ---
def test_crowd_never_drops_below_k(records, policy, target):
    rows, _ = linkage.run(records, policy, target)   # also checks ledger
    assert all(r["gate_candidates"] >= K for r in rows)


def test_plain_masking_identifies_and_exposes(records, policy, target):
    rows, _ = linkage.run(records, policy, target)
    assert rows[-1]["plain_candidates"] < K
    assert rows[-1]["plain_groups"] == 1


def test_finding_stays_ambiguous_before_release(records, policy, target):
    rows, _ = linkage.run(records, policy, target)
    assert rows[-1]["gate_groups"] >= L


def test_crowd_still_k_after_consented_release(records, policy, target):
    _, led = _session(policy, target, private_purpose="consented-prescreening")
    assert len(crowd(records, target,
                     led.known(AGENT, target["patient_id"]))) >= K


# ------------------------------------------------------------ summary ---
def test_clean_summary_passes(policy, target):
    _, led = _session(policy, target, private_purpose="consented-prescreening")
    view = released_view(target, AGENT, led)
    text = write_summary(view)
    ok, claims, violations = verify(text, target, AGENT, led)
    assert ok, violations
    assert target["finding"] not in text
    # every released field is claimed, read back from the text alone
    assert {c["field"] for c in claims} == set(view)


def test_leaky_summary_is_rejected_from_text_alone(policy, target):
    _, led = _session(policy, target, private_purpose="consented-prescreening")
    view = released_view(target, AGENT, led)
    ok, _, violations = verify(write_summary_leaky(view, target),
                               target, AGENT, led)
    assert not ok
    kinds = {f for f, _ in violations}
    assert {"finding", "text"} <= kinds


def test_unreleased_field_in_summary_is_rejected(policy, target):
    _, led = _session(policy, target)          # nothing private released
    text = write_summary(released_view(target, AGENT, led)) + \
        " finding group Reproductive,"
    ok, _, violations = verify(text, target, AGENT, led)
    assert not ok
    assert any("never released" in why for _, why in violations)


def test_extractor_reads_claims_without_writer_help():
    claims, unknown = extract_claims(
        "Pre-screening summary: female candidate, from Bengaluru East.")
    assert {"field": "pincode", "rung": 1, "value": "Bengaluru East"} in claims
    assert not unknown


# -------------------------------------------------------- certificate ---
def test_certificate_binds_and_detects_edits(policy, target):
    _, led = _session(policy, target, private_purpose="consented-prescreening")
    text = write_summary(released_view(target, AGENT, led))
    ok, claims, _ = verify(text, target, AGENT, led)
    cert = build_certificate(policy, led, AGENT, target["patient_id"],
                             claims, ok, issued_at="2026-01-01T00:00:00Z")
    assert cert["ledger_intact"] and cert["summary_check"] == "pass"
    assert check_certificate(cert)
    cert["parameters"]["k"] = 2
    assert not check_certificate(cert)
