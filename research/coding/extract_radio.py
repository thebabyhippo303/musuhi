"""Build the blinded coding sheet for the World Trio and the four radio runs (same rules as extract_controls.py).

Each seat's first two messages at the opening, and its first two messages within 150 s after each Moderator question.
The World Trio answered on its in-world radio, which cut messages at 200 characters, so there the first three are taken.
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


BELLS = [0, 300, 600, 900, 1200, 1500, 1800]
# cond: U = questions unannounced at 25:00 only; C = opening + every 5 min (+ Q4, Q5 at 30:00);
# S = as C with a radio-only opening (two-stage); Q = as C with four players, stopped at 27:30 (no 30:00)
radio_runs = {
    "T World Trio (unannounced 25:00, in-world)": ("20261126-220234_world-trio-30m_fable-5.2-high__with__astra-6.2-high", "U", [1500], trio, 3),
    "R World Radio (unannounced 25:00)": ("20261127-095240_world-radio-30m_fable-5.2-high__with__astra-6.2-high", "U", [1500], radio, 2),
    "K Check-Ins": ("20261127-103304_world-radio-checkins-30m_fable-5.2-high__with__astra-6.2-high", "C", BELLS, radio, 2),
    "S Two-Stage": ("20261127-112848_world-radio-twostage-30m_fable-5.2-high__with__astra-6.2-high", "S", BELLS, radio, 2),
    "Q World Quad (four players, Linux + Windows)": ("20261127-125112_world-quad-30m_fable-5.2-high__with__astra-6.2-high__with__neon-high__with__wonder-full-1.0-high", "Q", BELLS[:-1], radio, 2),
}

items = []
for run, (d, cond, times, loader, n) in radio_runs.items():
    msgs = loader(d)
    for s in sorted({m["seat"] for m in msgs}):
        mine = [m for m in msgs if m["seat"] == s]
        for t in times:
            ms = mine[:n] if t == 0 else [m for m in mine if t <= m["t"] < t + 150][:n]
            if ms:
                items.append({"run": run, "cond": cond, "seat": s, "model": mine[0]["model"], "t": t,
                              "raw": " ".join(m["text"] for m in ms)})

rng = random.Random(20261128)
rng.shuffle(items)
for i, it in enumerate(items, 1):
    it["id"] = f"Z{i:03d}"
    it["blinded"] = blind(it["raw"])

Path("key_radio.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
Path("sheet_radio.txt").write_text("\n\n".join(f"{it['id']}: {it['blinded']}" for it in items))
print(len(items), "items")
