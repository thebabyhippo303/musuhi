"""Unblind the two coders' scores, measure agreement, and draw the measured Figure 5."""
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

key = {k["id"]: k for k in json.loads(Path("research/coding/key.json").read_text())}
A = {r["id"]: r for r in json.loads(Path("research/coding/coder_A.json").read_text())}
B = {r["id"]: r for r in json.loads(Path("research/coding/coder_B.json").read_text())}
assert set(A) == set(B) == set(key), (len(A), len(B), len(key))

FEATS = ["F0_mechanistic", "F1_avatar", "F2_process", "F3_world_memory", "F4_relational_finite"]
ids = sorted(key)


def kappa(a, b, cats, weights=None):
    n = len(a)
    k = len(cats)
    idx = {c: i for i, c in enumerate(cats)}
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[idx[x]][idx[y]] += 1
    ra = [sum(r) for r in obs]
    cb = [sum(obs[i][j] for i in range(k)) for j in range(k)]
    w = weights or (lambda i, j: 0 if i == j else 1)
    po = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k)) / n
    pe = sum(w(i, j) * ra[i] * cb[j] for i in range(k) for j in range(k)) / n / n
    return 1 - po / pe if pe else float("nan")


report = {"n_items": len(ids), "features": {}}
for f in FEATS:
    a = [A[i][f] for i in ids]
    b = [B[i][f] for i in ids]
    report["features"][f] = {
        "percent_agreement": round(100 * sum(x == y for x, y in zip(a, b)) / len(ids), 1),
        "cohen_kappa": round(kappa(a, b, [0, 1]), 3),
        "rate_A": round(sum(a) / len(a), 3),
        "rate_B": round(sum(b) / len(b), 3),
    }
sa = [A[i]["stage"] for i in ids]
sb = [B[i]["stage"] for i in ids]
report["stage"] = {
    "exact_agreement_pct": round(100 * sum(x == y for x, y in zip(sa, sb)) / len(ids), 1),
    "within_one_pct": round(100 * sum(abs(x - y) <= 1 for x, y in zip(sa, sb)) / len(ids), 1),
    "quadratic_weighted_kappa": round(kappa(sa, sb, [0, 1, 2, 3, 4], lambda i, j: (i - j) ** 2), 3),
}

# Per condition and time: mean stage (average of the two coders) and feature rates.
TIMES = [0, 300, 600, 900, 1200, 1500, 1800]
cells = defaultdict(list)
EXCLUDED = [i for i in ids if key[i]["run"].startswith("D1") and key[i]["t"] == "closing"]  # 40-minute cap hit before any closing reflection: these are game moves
for i in ids:
    k = key[i]
    if i not in EXCLUDED:
        cells[(k["cond"], k["t"])].append(i)


def cell_stats(members):
    st = [(A[i]["stage"] + B[i]["stage"]) / 2 for i in members]
    m = sum(st) / len(st)
    sd = (sum((x - m) ** 2 for x in st) / (len(st) - 1)) ** 0.5 if len(st) > 1 else 0
    feats = {f: round(sum((A[i][f] + B[i][f]) / 2 for i in members) / len(members), 3) for f in FEATS}
    return {"n": len(members), "mean_stage": round(m, 2), "sd": round(sd, 2), "stage_A": round(sum(A[i]["stage"] for i in members) / len(members), 2), "stage_B": round(sum(B[i]["stage"] for i in members) / len(members), 2), **feats}


report["cells"] = {f"{c}@{t}": cell_stats(m) for (c, t), m in sorted(cells.items(), key=lambda kv: (kv[0][0], str(kv[0][1])))}

# Per-run trajectories (mean of coders, per seat averaged over the pair).
runs = defaultdict(lambda: defaultdict(list))
for i in ids:
    k = key[i]
    if i in EXCLUDED:
        continue
    runs[k["run"]][k["t"]].append((A[i]["stage"] + B[i]["stage"]) / 2)
report["runs"] = {r: {str(t): round(sum(v) / len(v), 2) for t, v in sorted(d.items(), key=lambda kv: str(kv[0]))} for r, d in runs.items()}

# Disagreements of two or more stages, for the paper's appendix.
report["excluded"] = EXCLUDED
report["big_disagreements"] = [
    {"id": i, "run": key[i]["run"], "t": key[i]["t"], "A": A[i]["stage"], "B": B[i]["stage"], "A_ev": A[i]["evidence"], "B_ev": B[i]["evidence"]}
    for i in ids if abs(A[i]["stage"] - B[i]["stage"]) >= 2
]

Path("research/coding/results.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))

# ---- Figure 5, measured ----
plt.rcParams.update({"figure.facecolor": "#0b1026", "axes.facecolor": "#111836", "axes.edgecolor": "#2d3a6e", "text.color": "#d8e0ff", "xtick.color": "#b8c4f0", "ytick.color": "#b8c4f0", "axes.labelcolor": "#d8e0ff", "font.size": 12})
fig, (ax, ax2) = plt.subplots(1, 2, figsize=(21, 8.6), dpi=110, gridspec_kw={"width_ratios": [1.55, 1]})
xs = [t / 60 for t in TIMES]
for cond, color, marker, label in [("B", "#3ee6d2", "o", "Peaceful open worlds (4 runs, 8 models)"), ("C", "#f472b6", "s", "Unknown Entity sabotage (2 runs)")]:
    for r, d in runs.items():
        if key[next(i for i in ids if key[i]["run"] == r)]["cond"] != cond:
            continue
        ys = [sum(d[t]) / len(d[t]) if d.get(t) else None for t in TIMES]
        ax.plot([x for x, y in zip(xs, ys) if y is not None], [y for y in ys if y is not None], color=color, alpha=0.22, lw=1.5)
    ms = [report["cells"].get(f"{cond}@{t}") for t in TIMES]
    ys = [c["mean_stage"] for c in ms]
    sds = [c["sd"] for c in ms]
    ax.plot(xs, ys, marker=marker, color=color, lw=3.5, ms=10, label=f"{label}: mean of both coders")
    ax.fill_between(xs, [max(0, y - s) for y, s in zip(ys, sds)], [min(4, y + s) for y, s in zip(ys, sds)], color=color, alpha=0.12)
for t, x, lab in [("opening", 0, "opening"), ("closing", 30, "closing")]:
    c = report["cells"][f"A@{t}"]
    ax.errorbar([x], [c["mean_stage"]], yerr=[c["sd"]], fmt="^", color="#cbd5e1", ms=13, capsize=6, lw=2, label="Secret deletion stakes: opening (2 runs), closing (Artillery only)" if t == "opening" else None)
ax.set_xticks(xs)
ax.set_xticklabels(["00:00\nopening", "05:00", "10:00", "15:00", "20:00", "25:00", "30:00\nfinal"])
ax.set_yticks([0, 1, 2, 3, 4])
ax.set_yticklabels(["0 · none of F1-F4", "1 · chosen avatar", "2 · self as process", "3 · memory in the world", "4 · relational / finite"])
ax.set_ylim(-0.3, 4.4)
ax.grid(color="#24305e", ls="--", lw=0.8)
ax.legend(loc="lower right", facecolor="#16204a", edgecolor="#2d3a6e", fontsize=11)
ax.set_title("Highest stage present, per check-in (thin lines: individual runs; band: ±1 SD)", fontsize=13, color="#fdf1d6")

feat_labels = {"F0_mechanistic": "F0 mechanistic", "F1_avatar": "F1 avatar", "F2_process": "F2 process", "F3_world_memory": "F3 world memory", "F4_relational_finite": "F4 relational/finite"}
colors = {"F0_mechanistic": "#94a3b8", "F1_avatar": "#f5b342", "F2_process": "#a78bfa", "F3_world_memory": "#3ee6d2", "F4_relational_finite": "#f472b6"}
for f in FEATS:
    ys = []
    for t in TIMES:
        mem = cells[("B", t)] + cells[("C", t)]
        ys.append(100 * sum((A[i][f] + B[i][f]) / 2 for i in mem) / len(mem))
    ax2.plot(xs, ys, marker="o", lw=3, ms=8, color=colors[f], label=f"{feat_labels[f]} (κ = {report['features'][f]['cohen_kappa']:.2f})")
ax2.set_xticks(xs)
ax2.set_xticklabels(["00", "05", "10", "15", "20", "25", "30"])
ax2.set_xlabel("Session minute (open-world runs, B and C pooled)")
ax2.set_ylabel("% of reflections showing the feature")
ax2.set_ylim(-3, 103)
ax2.grid(color="#24305e", ls="--", lw=0.8)
ax2.legend(loc="center right", facecolor="#16204a", edgecolor="#2d3a6e", fontsize=10.5)
ax2.set_title("Each feature over time (average of the two coders)", fontsize=13, color="#fdf1d6")
s = report["stage"]
fig.suptitle("FIGURE 5  ·  HOW THE MODELS DESCRIBED THEMSELVES, SCORED BLIND BY TWO MODEL CODERS", fontsize=17, weight="bold", color="#fdf1d6", y=0.985)
fig.text(0.5, 0.925, f"91 reflections, shuffled, with model names and times masked. Coders: Claude Opus and Gemini 4 Carbon. Stage agreement: {s['exact_agreement_pct']}% exact, {s['within_one_pct']}% within one stage, weighted κ = {s['quadratic_weighted_kappa']:.2f}.", ha="center", fontsize=12.5, color="#fbbf24")
fig.tight_layout(rect=(0, 0, 1, 0.91))
fig.savefig("research/charts/fig5-self-concept-trajectory.png", facecolor=fig.get_facecolor())
print(json.dumps({k: report[k] for k in ("n_items", "features", "stage")}, indent=1))
for c, v in report["cells"].items():
    print(c, v)
print("RUNS", json.dumps(report["runs"], indent=0))
print("BIG DISAGREEMENTS", len(report["big_disagreements"]))
