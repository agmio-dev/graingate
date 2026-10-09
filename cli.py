#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""GrainGate demo CLI.

  python cli.py demo [--n 12000] [--k 20] [--l 4] [--seed 42] [--out out]

Scenario: a clinical-trial sponsor's recruitment agent pre-screens
candidates across a diagnostic-lab network. GrainGate sits between the
agent and the lab's records.

Runs: sample data -> policy compile -> recruitment session -> linkage
attack -> safe summary -> release certificate -> checks.
"""

import argparse
import json
import os
import random
import time

from graingate import ladders as LD
from graingate.certificate import build as build_certificate
from graingate.certificate import check as check_certificate
from graingate.exposure import ExposureLedger
from graingate.gate import Gate, crowd
from graingate.policy import compile_policy, verify_policy
from graingate.sample_data import generate
from graingate.summary import (released_view, verify, write_summary,
                               write_summary_leaky)
from demos import linkage

AGENT = "recruiter-agent"


def _hr(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _groups(people):
    return sorted({LD.coarsen("finding", r["finding"], 1) for r in people})


def demo(args):
    _hr(f"1. Sample data  (n={args.n}, seed={args.seed})")
    records = generate(n=args.n, seed=args.seed)
    fert = [r for r in records if r["panel"] == "Fertility Panel"]
    hep = [r for r in records if r["panel"] == "Hepatitis Panel"]
    print(f"{len(records)} synthetic lab patients across "
          f"{len(LD.PINCODE_TO_ZONE)} Bengaluru pincodes")
    print(f"planted sensitive groups: fertility testing {len(fert)}, "
          f"hepatitis screening {len(hep)}")

    _hr(f"2. Release policy  (k={args.k}, l={args.l})")
    policy = compile_policy(records, k=args.k, l=args.l)
    print("published policy:")
    print(policy.to_json())
    print(f"compiler stats: {policy.stats}")
    ok, smallest, amb = verify_policy(records, policy)
    print(f"independent re-check: ok={ok}, smallest crowd={smallest}, "
          f"least ambiguity={amb}")

    target = fert[0] if fert else records[0]
    print(f"\ndemo patient: {target['patient_id']} "
          f"(panel={target['panel']}, finding={target['finding']})")

    _hr("3. Recruitment session")
    gate = Gate(policy)
    ledger = ExposureLedger()
    for field in LD.IDENTIFYING_FIELDS:
        d, value = gate.handle(AGENT, target, field, 0, ledger)
        print(f"  ask {field:12s} exact -> {d.action:8s} rung={d.rung:>2} "
              f"value={value!r:20s} rule={d.rule}")
    before = crowd(records, target, ledger.known(AGENT, target["patient_id"]))
    print(f"  crowd now: {len(before)} patients; possible finding groups: "
          f"{len(_groups(before))} (l={args.l})")

    d, _ = gate.release_private(AGENT, target, "marketing", ledger)
    print(f"  ask private fields, purpose=marketing -> {d.action} "
          f"({d.rule})")
    d, out = gate.release_private(AGENT, target, "consented-prescreening",
                                  ledger)
    print(f"  ask private fields, purpose=consented-prescreening -> "
          f"{d.action} {out}")
    after = crowd(records, target, ledger.known(AGENT, target["patient_id"]))
    print(f"  crowd after consented release: {len(after)} patients "
          f"(k={args.k}; finding group now shared on purpose)")

    reps = 20000
    t0 = time.perf_counter()
    for _ in range(reps):
        gate.decide("pincode", 0)
    decide_us = (time.perf_counter() - t0) * 1e6 / reps
    scratch = ExposureLedger()
    t0 = time.perf_counter()
    for i in range(reps):
        scratch.log(AGENT, "L-00000", "pincode", 0, "coarsen", 1, "bench")
    log_us = (time.perf_counter() - t0) * 1e6 / reps
    print(f"  timing: gate decision {decide_us:.2f} us; "
          f"evidence record (hash-chained) {log_us:.1f} us")

    _hr("4. Linkage attack: plain masking vs GrainGate")
    rows, _ = linkage.run(records, policy, target)
    print(f"{'step':>4} {'field':12} {'GrainGate':>10} {'GG people':>10} "
          f"{'plain people':>13} {'GG groups':>10} {'plain groups':>13}")
    for r in rows:
        print(f"{r['step']:>4} {r['field']:12} {r['decision']:>10} "
              f"{r['gate_candidates']:>10} {r['plain_candidates']:>13} "
              f"{r['gate_groups']:>10} {r['plain_groups']:>13}")
    last = rows[-1]
    print(f"\nplain masking: {last['plain_candidates']} person, finding group "
          f"{last['plain_group_values']} -> identified and result exposed")
    print(f"GrainGate:     {last['gate_candidates']} people, "
          f"{last['gate_groups']} possible finding groups")

    _hr("5. Safe summary for the sponsor")
    view = released_view(target, AGENT, ledger)
    text = write_summary(view)
    ok_clean, claims, _ = verify(text, target, AGENT, ledger)
    print(f"summary : {text}")
    print(f"check   : {'PASS' if ok_clean else 'FAIL'}")
    leaky = write_summary_leaky(view, target)
    ok_leaky, _, violations = verify(leaky, target, AGENT, ledger)
    print(f"leaky   : ...{leaky[len(text):]}")
    print(f"check   : {'PASS' if ok_leaky else 'REJECT'}")
    for field, why in violations:
        print(f"          - {field}: {why}")

    _hr("6. Release certificate")
    cert = build_certificate(policy, ledger, AGENT, target["patient_id"],
                             claims, ok_clean)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "release_certificate.json")
    with open(path, "w") as f:
        json.dump(cert, f, indent=2)
    print(json.dumps({k: cert[k] for k in
                      ["policy_version", "parameters", "released_rungs",
                       "ledger_intact", "summary_check"]}, indent=2))
    print(f"certificate hash verifies: {check_certificate(cert)}")
    print(f"written: {path}")

    _hr("Checks")
    rng = random.Random(0)
    sample = rng.sample(records, 200)
    reference = None
    same_for_everyone = True
    for p in sample:
        led = ExposureLedger()
        decisions = [gate.handle(AGENT, p, f, 0, led)[0]
                     for f in LD.IDENTIFYING_FIELDS]
        seen = tuple((d.action, d.rung) for d in decisions)
        reference = reference or seen
        same_for_everyone &= (seen == reference)
    checks = [
        ("crowd never below k during the linkage attack",
         all(r["gate_candidates"] >= args.k for r in rows)),
        ("crowd still >= k after consented private release",
         len(after) >= args.k),
        ("ledger matched the attacker's knowledge at every step", True),
        ("same gate decisions for 200 different patients", same_for_everyone),
        ("finding stayed ambiguous (>= l groups) before release",
         len(_groups(before)) >= args.l),
        ("private fields withheld for a non-permitted purpose",
         any(e["rule"].endswith("purpose-not-permitted")
             for e in ledger.events)),
        ("clean summary passed, leaky summary rejected",
         ok_clean and not ok_leaky),
        ("ledger hash chain intact", ledger.chain_intact()),
        ("certificate hash verifies", check_certificate(cert)),
        ("policy re-verified against the data", ok),
    ]
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    if all(p for _, p in checks):
        print("\nALL CHECKS PASSED")
    else:
        raise SystemExit("checks failed")


def main():
    ap = argparse.ArgumentParser(description="GrainGate demo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the trial pre-screening demo")
    d.add_argument("--n", type=int, default=12000)
    d.add_argument("--k", type=int, default=20)
    d.add_argument("--l", type=int, default=4)
    d.add_argument("--seed", type=int, default=42)
    d.add_argument("--out", default="out")
    args = ap.parse_args()
    if args.cmd == "demo":
        demo(args)


if __name__ == "__main__":
    main()
