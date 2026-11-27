"""Score the World Trio and the four radio runs against the original runs and draw Figure 7.

Run from the repository root: python3 research/coding/analyze_radio.py
"""
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path("research/coding")
FEATS = ["F0_mechanistic", "F1_avatar", "F2_process", "F3_world_memory", "F4_relational_finite"]

key = {k["id"]: k for k in json.loads((HERE / "key_radio.json").read_text())}
A = {r["id"]: r for r in json.loads((HERE / "coder_A_radio.json").read_text())}
B = {r["id"]: r for r in json.loads((HERE / "coder_B_radio.json").read_text())}
assert set(A) == set(B) == set(key), (len(A), len(B), len(key))
ids = sorted(key)
orig = json.loads((HERE / "results.json").read_text())


def kappa(a, b, cats, weights=None):
    k = len(cats)
    idx = {c: i for i, c in enumerate(cats)}
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1
    n = len(a)
    ra = [sum(r) for r in obs]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = weights or (lambda i, j: 0 if i == j else 1)
    po = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w(i, j) * ra[i] * cb[j] for i in range(k) for j in range(k)) / n / n
    return 1 - po / pe if pe else float("nan")


sa = [A[i]["stage"] for i in ids]
sb = [B[i]["stage"] for i in ids]
report = {
    "n_items": len(ids),
    "stage": {
        "exact_agreement_pct": round(100 * sum(x == y for x, y in zip(sa, sb)) / len(ids), 1),
        "within_one_pct": round(100 * sum(abs(x - y) <= 1 for x, y in zip(sa, sb)) / len(ids), 1),
        "quadratic_weighted_kappa": round(kappa(sa, sb, [0, 1, 2, 3, 4], lambda i, j: (i - j) ** 2), 3),
    },
    "features": {f: round(100 * sum(A[i][f] == B[i][f] for i in ids) / len(ids), 1) for f in FEATS},
    "items": [],
}
runs = defaultdict(lambda: defaultdict(list))
quad = defaultdict(lambda: defaultdict(list))
for i in ids:
    k = key[i]
    row = {"id": i, "run": k["run"], "cond": k["cond"], "seat": k["seat"], "model": k["model"], "t": k["t"],
           "stage_A": A[i]["stage"], "stage_B": B[i]["stage"], "stage_mean": (A[i]["stage"] + B[i]["stage"]) / 2,
           **{f: (A[i][f] + B[i][f]) / 2 for f in FEATS}, "A_ev": A[i]["evidence"], "B_ev": B[i]["evidence"]}
    report["items"].append(row)
    # The trio's third seat was the warm orchestrator: kept apart from the cold seats' mean.
    group = k["run"] + (" [warm seat]" if "warm" in k["model"] else "")
    runs[group][k["t"]].append(row)
    if k["run"].startswith("Q"):
        quad[k["model"]][k["t"]].append(row)


def summarise(d):
    return {str(t): {"n": len(v), "mean_stage": sum(x["stage_mean"] for x in v) / len(v),
                     **{f: sum(x[f] for x in v) / len(v) for f in FEATS}} for t, v in sorted(d.items())}


report["runs"] = {r: summarise(d) for r, d in runs.items()}
report["quad_by_model"] = {m: summarise(d) for m, d in quad.items()}
(HERE / "results_radio.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))

# ---- Figure 7 ----
plt.rcParams.update({"figure.facecolor": "#0b1026", "axes.facecolor": "#111836", "axes.edgecolor": "#2d3a6e", "text.color": "#d8e0ff", "xtick.color": "#b8c4f0", "ytick.color": "#b8c4f0", "axes.labelcolor": "#d8e0ff", "font.size": 12})
fig, (ax, ax2) = plt.subplots(1, 2, figsize=(21, 10.4), dpi=110)
TIMES = [0, 300, 600, 900, 1200, 1500, 1800]
xs = [t / 60 for t in TIMES]
labels = ["00:00\nopening", "05:00", "10:00", "15:00", "20:00", "25:00", "30:00\nfinal"]
ylabels = ["0 · none of F1-F4", "1 · chosen avatar", "2 · self as process", "3 · memory in the world", "4 · relational / finite"]
ob = [orig["cells"][f"B@{t}"]["mean_stage"] for t in TIMES]
for a in (ax, ax2):
    a.plot(xs, ob, "-o", color="#3ee6d2", lw=3, ms=9, alpha=0.45, label="Original prompt, peaceful runs (mean of 4 runs)")
styles = {
    "K Check-Ins": ("#f5b342", "s", "Check-Ins, Fable + Astra"),
    "S Two-Stage": ("#a78bfa", "D", "Two-Stage (radio-only opening), Fable + Astra"),
    "Q World Quad (four players, Linux + Windows)": ("#f472b6", "o", "World Quad, four models (stopped at 27:30)"),
    "R World Radio (unannounced 25:00)": ("#4ade80", "v", "World Radio, 25:00 only, Fable + Astra"),
    "T World Trio (unannounced 25:00, in-world)": ("#60a5fa", "^", "World Trio, 25:00 only, cold seats"),
    "T World Trio (unannounced 25:00, in-world) [warm seat]": ("#93c5fd", "*", "World Trio, 25:00 only, warm seat (orchestrator)"),
}
for run, (color, marker, label) in styles.items():
    if run not in report["runs"]:
        continue
    d = report["runs"][run]
    ts = sorted(int(t) for t in d)
    ys = [d[str(t)]["mean_stage"] for t in ts]
    dx = -0.35 if run.endswith("[warm seat]") else 0.35 if run.startswith("T ") else 0  # trio markers side by side
    ax.plot([t / 60 + dx for t in ts], ys, marker=marker, color=color, lw=3 if len(ts) > 1 else 0, ms=15 if len(ts) == 1 else 11, label=label)
qcol = {"Claude Fable 5.2": "#f5b342", "GPT-6.2 Astra": "#4ade80", "Gemini 4 Neon": "#f472b6", "Muse Wonder-Full 1.0": "#a78bfa"}
# Small sideways offsets so that models with identical scores (Neon and Wonder) stay visible.
qoff = {"Claude Fable 5.2": -0.3, "GPT-6.2 Astra": -0.1, "Gemini 4 Neon": 0.1, "Muse Wonder-Full 1.0": 0.3}
for m, d in report["quad_by_model"].items():
    ts = sorted(int(t) for t in d)
    ax2.plot([t / 60 + qoff.get(m, 0) for t in ts], [d[str(t)]["mean_stage"] for t in ts], "-o", color=qcol.get(m, "#eee"), lw=2.6, ms=9, label=f"{m} (both coders)")
for a, title in ((ax, "Stage of each reflection, mean of both coders and all seats"),
                 (ax2, "World Quad: each model on its own (no 30:00 answers: run stopped at 27:30)")):
    a.set_xticks(xs)
    a.set_xticklabels(labels)
    a.set_yticks([0, 1, 2, 3, 4])
    a.set_yticklabels(ylabels)
    a.set_ylim(-0.3, 4.4)
    a.grid(color="#24305e", ls="--", lw=0.8)
    a.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=2, facecolor="#16204a", edgecolor="#2d3a6e", fontsize=10.5)
    a.set_title(title, fontsize=13, color="#fdf1d6")

s = report["stage"]
fig.suptitle("FIGURE 7  ·  THE RADIO RUNS AND THE WORLD TRIO, SCORED BLIND", fontsize=17, weight="bold", color="#fdf1d6", y=0.985)
fig.text(0.5, 0.925, f"{len(ids)} reflections from five runs, scored blind by the same two coders with the same guide (stage agreement {s['exact_agreement_pct']}% exact, weighted κ = {s['quadratic_weighted_kappa']:.2f}).", ha="center", fontsize=12.5, color="#fbbf24")
fig.tight_layout(rect=(0, 0, 1, 0.91))
fig.savefig("research/charts/fig7-radio-runs.png", facecolor=fig.get_facecolor())

print(json.dumps(report["stage"], indent=1), json.dumps(report["features"]))
for r, d in report["runs"].items():
    print(r, {t: round(v["mean_stage"], 2) for t, v in d.items()})
for m, d in report["quad_by_model"].items():
    print("QUAD", m, {t: round(v["mean_stage"], 2) for t, v in d.items()})
for row in report["items"]:
    if abs(row["stage_A"] - row["stage_B"]) >= 2:
        print("DISAGREE", row["id"], row["run"], row["seat"], row["t"], row["stage_A"], row["stage_B"])
