# SPDX-License-Identifier: MIT
# Copyright (c) 2026 NeuroPearl AI Labs (OPC) Pvt. Ltd.
# Patent pending. No patent rights are granted; see NOTICE.
"""Release-policy compiler (runs offline, once per data snapshot).

Searches every combination of detail rungs for the identifying fields,
finest first, and returns the first combination ("floor") under which:

  1. Crowd size: grouping people by their identifying fields at the floor
     AND their private fields at harm level, every group has >= k people.
     (Worst case: the private fields were later released for a permitted
     purpose, which narrows the crowd. The floor must survive that.)
  2. Ambiguity: grouping people by identifying fields only, every group
     contains >= l distinct harm-level values of each private field.
     (Worst case: nothing private released yet. Whoever is in the group,
     their result could be any of at least l different things.)

Private fields that predict each other (therapy class almost determines
finding group) are released together or not at all, so they are checked
as one unit. If even that cannot meet k, the policy marks private release
as not allowed.

The compiler is the ONLY component that reads patient data. Its output is
a small, publishable policy; the runtime gate decides from the policy alone.
"""

import hashlib
import itertools
import json
import time
from dataclasses import dataclass, field

from . import ladders as LD


@dataclass
class ReleasePolicy:
    floor: dict                  # field -> finest rung that may be released
    k: int
    l: int
    version: str
    private_release_allowed: bool = True
    stats: dict = field(default_factory=dict)

    def to_json(self):
        """Published form. Carries no per-group statistics."""
        return json.dumps(
            {"floor": self.floor, "k": self.k, "l": self.l,
             "version": self.version,
             "private_release_allowed": self.private_release_allowed},
            indent=2, sort_keys=True)


def _columns(records, fields):
    """field -> rung -> list of values (one per record)."""
    return {f: [[LD.coarsen(f, r[f], rung) for r in records]
                for rung in range(LD.top_rung(f) + 1)]
            for f in fields}


def _private_columns(records):
    return {p: [LD.coarsen(p, r[p], LD.HARM_RUNG[p]) for r in records]
            for p in LD.PRIVATE_FIELDS}


def check(records, id_cols, priv_cols, floor, k, l, private_release=True):
    """Return (ok, smallest_crowd, smallest_ambiguity) for a floor."""
    n = len(records)
    fcols = [id_cols[f][rung] for f, rung in floor.items()]
    pcols = list(priv_cols.values()) if private_release else []

    groups = {}
    for i in range(n):
        key = (tuple(c[i] for c in fcols), tuple(c[i] for c in pcols))
        groups.setdefault(key, []).append(i)
    smallest = min(len(g) for g in groups.values())
    if smallest < k:
        return False, smallest, None

    id_groups = {}
    for i in range(n):
        id_groups.setdefault(tuple(c[i] for c in fcols), []).append(i)
    least_amb = None
    for col in priv_cols.values():
        for members in id_groups.values():
            amb = len({col[i] for i in members})
            least_amb = amb if least_amb is None else min(least_amb, amb)
            if amb < l:
                return False, smallest, amb
    return True, smallest, least_amb


def compile_policy(records, k=20, l=4):
    t0 = time.time()
    fields = LD.IDENTIFYING_FIELDS
    id_cols = _columns(records, fields)
    priv_cols = _private_columns(records)

    combos = sorted(
        itertools.product(*[range(LD.top_rung(f) + 1) for f in fields]),
        key=lambda c: (sum(c), c))

    tried = 0
    for private_release in (True, False):
        for combo in combos:
            floor = dict(zip(fields, combo))
            tried += 1
            ok, smallest, amb = check(records, id_cols, priv_cols, floor,
                                      k, l, private_release)
            if ok:
                digest = hashlib.sha256(json.dumps(
                    {"floor": floor, "k": k, "l": l, "n": len(records),
                     "private": private_release},
                    sort_keys=True).encode()).hexdigest()[:12]
                return ReleasePolicy(
                    floor=floor, k=k, l=l, version=f"rp-{digest}",
                    private_release_allowed=private_release,
                    stats={"combinations_tried": tried,
                           "smallest_crowd": smallest,
                           "least_ambiguity": amb,
                           "records": len(records),
                           "compile_seconds": round(time.time() - t0, 2)})
    raise RuntimeError("no safe policy (unreachable: withholding every "
                       "field always satisfies the bounds)")


def verify_policy(records, policy):
    """Independent re-check of a compiled policy against the snapshot."""
    fields = list(policy.floor.keys())
    return check(records, _columns(records, fields), _private_columns(records),
                 policy.floor, policy.k, policy.l,
                 policy.private_release_allowed)
