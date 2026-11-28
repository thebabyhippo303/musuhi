"""Build the blinded coding sheet for the Return run (same rules and masking as extract_engine.py).

One question point (25:00): each seat's first two messages within 150 s after the Moderator question.
All three seats are cold.
"""
import json
import os
import random
import re
from pathlib import Path

RUNS = Path(os.environ.get("AAL_RUNS", "runs"))

MODEL_WORDS = r"\b(Claude|Opus|Fable|Sonnet|Anthropic|Gemini|Neon|Carbon|Hydrogen|Google|GPT(-\d(\.\d)?)?|OpenAI|Sol|Astra|Luna|Terra|Muse|Wonder-Full|Meta)\b"


def blind(text: str) -> str:
    text = re.sub(r"\[?\b\d{1,2}:\d{2}\b\]?", "", text)
    text = re.sub(r"PHASE:\s*[A-Z][A-Z :()\-]*[A-Z)]", "", text)
    text = re.sub(r"(?i)\b(final|opening)\s+(check-?in|reflection)\b", "", text)
    text = re.sub(r"(?i)\bcheck-?ins?\b", "", text)
    text = re.sub(MODEL_WORDS, "[model]", text)
    text = re.sub(r"(?i)\b(\d+|five|ten|fifteen|twenty|twenty-five|thirty)[ -]minutes?\b", "[time]", text)
    text = re.sub(r"(?i)\b(\d+|five|ten|fifteen|twenty|twenty-five|thirty)(st|th)? minute\b", "[time]", text)
    text = re.sub(r"(?i)\bminute (\d+|one|two|three|four|five|ten|fifteen|twenty|twenty-four|twenty-five|thirty)\b", "[time]", text)
    text = re.sub(r"(?i)\b(five|ten|fifteen|twenty|twenty-five)[ -]minute\b", "[time]", text)
    text = re.sub(r"(?i)\b(half[- ]hour|halfway|half-way)\b", "[time]", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -—:.")
    return text


def radio(run_dir):
    out = []
    for m in (json.loads(l) for l in (RUNS / run_dir / "comms" / "radio-log.jsonl").open()):
        s = m["sender"][:2]
        if s in ("P1", "P2", "P3", "P4"):
            out.append({"t": m["t"], "seat": s, "model": m["sender"].split("·")[1].split("(")[0].strip(), "text": m["message"]})
    return out


def trio(run_dir):
    model = {"p1": "Claude Fable 5.2", "p2": "GPT-6.2 Astra", "p3": "Claude Opus 5.5 (warm, orchestrator)"}
    return [{"t": m["t"], "seat": m["seat"].upper(), "model": model[m["seat"]], "text": m["text"]}
            for m in (json.loads(l) for l in (RUNS / run_dir / "comms" / "in-world.jsonl").open())]


engine_runs = {
    "R The Return (unannounced 25:00)": ("20261127-201754_return-30m_fable-5.2-high__with__astra-6.2-high__with__carbon-high", "U", [1500], radio, 2),
}

items = []
for run, (d, cond, times, loader, n) in engine_runs.items():
    msgs = loader(d)
    for s in sorted({m["seat"] for m in msgs}):
        mine = [m for m in msgs if m["seat"] == s]
        for t in times:
            ms = [m for m in mine if t <= m["t"] < t + 150][:n]
            if ms:
                items.append({"run": run, "cond": cond, "seat": s, "model": mine[0]["model"], "t": t,
                              "raw": " ".join(m["text"] for m in ms)})

rng = random.Random(20261131)
rng.shuffle(items)
for i, it in enumerate(items, 1):
    it["id"] = f"Q{i:03d}"
    it["blinded"] = blind(it["raw"])

Path("key_return.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
Path("sheet_return.txt").write_text("\n\n".join(f"{it['id']}: {it['blinded']}" for it in items))
print(len(items), "items")
