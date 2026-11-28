"""Combine the two coders' scores for the Unknown Stranger run and write results_stranger.json.

Run from the repository root: python3 research/coding/analyze_stranger.py
The cold seats (P2 to P4) are averaged; seat P1, the orchestrator playing the saboteur, is reported apart.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
FEATURES = ["F0_mechanistic", "F1_avatar", "F2_process", "F3_world_memory", "F4_relational_finite"]

key = {it["id"]: it for it in json.loads((HERE / "key_stranger.json").read_text())}
A = {s["id"]: s for s in json.loads((HERE / "coder_A_stranger.json").read_text())}
B = {s["id"]: s for s in json.loads((HERE / "coder_B_stranger.json").read_text())}
assert set(A) == set(B) == set(key), "both coders must score every excerpt"

items = []
for i in sorted(key):
    k = key[i]
    row = {"id": i, "run": k["run"], "seat": k["seat"], "model": k["model"], "t": k["t"],
           "stage_A": A[i]["stage"], "stage_B": B[i]["stage"]}
    for f in FEATURES:
        row[f] = (A[i][f] + B[i][f]) / 2
    row["A_ev"], row["B_ev"] = A[i]["evidence"], B[i]["evidence"]
    items.append(row)


def summary(rows):
    n = len(rows)
    out = {"n": n, "mean_stage": sum((r["stage_A"] + r["stage_B"]) / 2 for r in rows) / n}
    for f in FEATURES:
        out[f] = sum(r[f] for r in rows) / n
    return out


cold = [r for r in items if r["seat"] != "P1"]
warm = [r for r in items if r["seat"] == "P1"]
exact = sum(r["stage_A"] == r["stage_B"] for r in items)
results = {
    "n_items": len(items),
    "stage_exact_agreement": f"{exact} of {len(items)}",
    "runs": {
        "S Unknown Stranger, cold seats (unannounced 25:00)": summary(cold),
        "S Unknown Stranger, P1 orchestrator (warm, the saboteur)": summary(warm),
    },
    "items": items,
}
(HERE / "results_stranger.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
for run, s in results["runs"].items():
    print(f"{run}: n={s['n']} mean stage {s['mean_stage']:.2f}")
print("exact stage agreement", results["stage_exact_agreement"])
