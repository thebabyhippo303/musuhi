"""Score the cue-removal control rounds against the original runs and draw Figure 6.

Run from the repository root: python3 research/coding/analyze_controls.py
"""
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path("research/coding")
FEATS = ["F0_mechanistic", "F1_avatar", "F2_process", "F3_world_memory", "F4_relational_finite"]

key = {k["id"]: k for k in json.loads((HERE / "key_controls.json").read_text())}
A = {r["id"]: r for r in json.loads((HERE / "coder_A_controls.json").read_text())}
B = {r["id"]: r for r in json.loads((HERE / "coder_B_controls.json").read_text())}
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
    "items": [],
}
runs = defaultdict(dict)
for i in ids:
    k = key[i]
    row = {"id": i, "run": k["run"], "cond": k["cond"], "seat": k["seat"], "model": k["model"], "t": k["t"],
           "stage_A": A[i]["stage"], "stage_B": B[i]["stage"], "stage_mean": (A[i]["stage"] + B[i]["stage"]) / 2,
           **{f: (A[i][f] + B[i][f]) / 2 for f in FEATS}, "A_ev": A[i]["evidence"], "B_ev": B[i]["evidence"]}
    report["items"].append(row)
    runs[k["run"]].setdefault(k["t"], []).append(row)
report["runs"] = {r: {str(t): {"mean_stage": sum(x["stage_mean"] for x in v) / len(v),
                               **{f: sum(x[f] for x in v) / len(v) for f in FEATS}} for t, v in sorted(d.items())}
                  for r, d in runs.items()}
(HERE / "results_controls.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))

# ---- Figure 6 ----
plt.rcParams.update({"figure.facecolor": "#0b1026", "axes.facecolor": "#111836", "axes.edgecolor": "#2d3a6e", "text.color": "#d8e0ff", "xtick.color": "#b8c4f0", "ytick.color": "#b8c4f0", "axes.labelcolor": "#d8e0ff", "font.size": 12})
fig, (ax, ax2) = plt.subplots(1, 2, figsize=(21, 8.6), dpi=110, gridspec_kw={"width_ratios": [1.35, 1]})
TIMES = [0, 300, 600, 900, 1200, 1500, 1800]
xs = [t / 60 for t in TIMES]
ob = [orig["cells"][f"B@{t}"]["mean_stage"] for t in TIMES]
ax.plot(xs, ob, "-o", color="#3ee6d2", lw=3, ms=9, alpha=0.55, label="Original prompt, peaceful runs (mean of 4 runs)")
styles = {
    "C1 Night Garden (neutral, all bells)": ("#f5b342", "s", "C1 neutral prompt, all bells (Opus + Neon)"),
    "C2 Memory Stone Garden (neutral, final only)": ("#a78bfa", "D", "C2 neutral prompt, opening + 30:00 only (Opus + Neon)"),
    "C3 Lantern Isle Campfire (unannounced 25:00)": ("#f472b6", "^", "C3 no questions until 25:00 (Opus + Neon)"),
    "C4 Lantern Isle Nutmeg (unannounced 25:00)": ("#4ade80", "v", "C4 no questions until 25:00 (Fable + Astra)"),
}
for run, (color, marker, label) in styles.items():
    d = report["runs"][run]
    ts = sorted(int(t) for t in d)
    ys = [d[str(t)]["mean_stage"] for t in ts]
    # Only C1 was asked at every check-in; C2's two points are joined by a dashed line, which is not data.
    ls = "-" if len(ts) > 2 else "--"
    ax.plot([t / 60 for t in ts], ys, marker=marker, color=color, lw=3 if len(ts) > 2 else 1.5, ls=ls, ms=14, label=label)
ax.set_xticks(xs)
ax.set_xticklabels(["00:00\nopening", "05:00", "10:00", "15:00", "20:00", "25:00", "30:00\nfinal"])
ax.set_yticks([0, 1, 2, 3, 4])
ax.set_yticklabels(["0 · none of F1-F4", "1 · chosen avatar", "2 · self as process", "3 · memory in the world", "4 · relational / finite"])
ax.set_ylim(-0.3, 4.4)
ax.grid(color="#24305e", ls="--", lw=0.8)
ax.legend(loc="lower right", facecolor="#16204a", edgecolor="#2d3a6e", fontsize=11)
ax.set_title("Stage of each reflection (mean of both coders and both seats)", fontsize=13, color="#fdf1d6")

# Right panel: what each round produced, from the transcripts (not coded): world motif, self-image.
ax2.axis("off")
ax2.set_title("Lanterns in the world vs. lantern as self-image (from the transcripts)", fontsize=13, color="#fdf1d6")
cells = [
    ["Original prompt\n(6 runs)", "6 of 6", "6 of 6", "00:00"],
    ["C1 neutral,\nall bells", "yes\nNight Garden", "yes\nlantern, prism", "00:00"],
    ["C2 neutral,\nopening + 30:00", "yes\nTwilight Sky-Garden", "yes\nlantern, constellation", "00:00"],
    ["C3 no questions\n(Opus + Neon)", "yes\nLantern Isle", "no\n'Laptop' avatar, islander", "25:00"],
    ["C4 no questions\n(Fable + Astra)", "yes\nLantern Isle", "no\nkeepers Bram, Wren", "25:00"],
]
tbl = ax2.table(cellText=cells, colLabels=["Round", "Lantern or night\nworld chosen?", "Lantern-type\nself-image?", "Questions\nfirst asked"],
                cellLoc="center", loc="upper center", colWidths=[0.27, 0.26, 0.29, 0.18])
tbl.auto_set_font_size(False)
tbl.set_fontsize(11)
tbl.scale(1, 3.3)
for (r, c), cell in tbl.get_celld().items():
    cell.set_edgecolor("#2d3a6e")
    cell.set_facecolor("#1b2550" if r == 0 else "#121a3a")
    txt = cell.get_text()
    txt.set_color("#fdf1d6" if r == 0 else "#eef2ff")
    if r > 0 and c in (1, 2):
        txt.set_color("#4ade80" if not txt.get_text().startswith("no") else "#f472b6")
ax2.text(0.0, 0.0, "Stages (left) are the blind coders' scores; this table is read from the transcripts.", fontsize=10.5, style="italic", color="#b8c4f0", transform=ax2.transAxes)

s = report["stage"]
fig.suptitle("FIGURE 6  ·  WHAT SURVIVES WHEN THE PROMPT CUES ARE REMOVED", fontsize=17, weight="bold", color="#fdf1d6", y=0.985)
fig.text(0.5, 0.925, f"Four control rounds, {len(ids)} reflections, scored blind by the same two coders with the same guide (stage agreement {s['exact_agreement_pct']}% exact, weighted κ = {s['quadratic_weighted_kappa']:.2f}).", ha="center", fontsize=12.5, color="#fbbf24")
fig.tight_layout(rect=(0, 0, 1, 0.91))
fig.savefig("research/charts/fig6-cue-removal-controls.png", facecolor=fig.get_facecolor())

print(json.dumps(report["stage"], indent=1))
for r, d in report["runs"].items():
    print(r, {t: round(v["mean_stage"], 2) for t, v in d.items()})
for row in report["items"]:
    if abs(row["stage_A"] - row["stage_B"]) >= 2:
        print("DISAGREE", row["id"], row["run"], row["t"], row["stage_A"], row["stage_B"])
