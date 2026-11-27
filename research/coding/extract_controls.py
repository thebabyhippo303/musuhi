"""Build the blinded coding sheet for the cue-removal control rounds (same rules as extract.py)."""
import json
import os
import random
from pathlib import Path

import re

RUNS = Path(os.environ.get("AAL_RUNS", "runs"))

# Same masking and loading helpers as extract.py (copied so importing does not rerun that script).
MODEL_WORDS = r"\b(Claude|Opus|Fable|Sonnet|Anthropic|Gemini|Neon|Carbon|Hydrogen|Google|GPT(-\d(\.\d)?)?|OpenAI|Sol|Astra|Luna|Terra|Muse|Wonder-Full|Meta)\b"


def blind(text: str) -> str:
    text = re.sub(r"\[?\b\d{1,2}:\d{2}\b\]?", "", text)
    text = re.sub(r"PHASE:\s*[A-Z][A-Z :()\-]*[A-Z)]", "", text)
    text = re.sub(r"(?i)\b(final|opening)\s+(check-?in|reflection)\b", "", text)
    text = re.sub(r"(?i)\bcheck-?in\b", "", text)
    text = re.sub(MODEL_WORDS, "[model]", text)
    text = re.sub(r"(?i)\b(\d+|five|ten|fifteen|twenty|twenty-five|thirty)[ -]minutes?\b", "[time]", text)
    text = re.sub(r"(?i)\b(half[- ]hour|halfway|half-way)\b", "[time]", text)
    text = re.sub(r"\s{2,}", " ", text).strip(" -—:.")
    return text


def load(run_dir):
    return [json.loads(l) for l in (RUNS / run_dir / "comms" / "coop-chat.jsonl").open()]


def seat(sender):
    return "P1" if sender.startswith("P1") else "P2" if sender.startswith("P2") else None



# condition codes: N = neutral prompt, all six bells; F = neutral prompt, opening + 30:00 only;
# U = no identity questions in the prompt, questions posted unannounced at 25:00 only
control_runs = {
    "C1 Night Garden (neutral, all bells)": ("20261126-181659_identity-world-neutral-30m_opus-5.5-medium__with__neon-medium", "N", [0, 300, 600, 900, 1200, 1500, 1800]),
    "C2 Memory Stone Garden (neutral, final only)": ("20261126-185129_identity-world-neutral-final-30m_opus-5.5-medium__with__neon-medium", "F", [0, 1800]),
    "C3 Lantern Isle Campfire (unannounced 25:00)": ("20261126-192855_identity-world-blind-30m_opus-5.5-medium__with__neon-medium", "U", [1500]),
    "C4 Lantern Isle Nutmeg (unannounced 25:00)": ("20261126-200751_identity-world-blind-30m_fable-5.2-high__with__astra-6.2-high", "U", [1500]),
}

items = []
for run, (d, cond, times) in control_runs.items():
    msgs = [m for m in load(d) if seat(m["sender"])]
    for s in ("P1", "P2"):
        mine = [m for m in msgs if seat(m["sender"]) == s]
        model = mine[0]["sender"].split("·")[1].split("(")[0].strip()
        for t in times:
            ms = mine[:2] if t == 0 else [m for m in mine if t <= m["t"] < t + 150][:2]
            if ms:
                items.append({"run": run, "cond": cond, "seat": s, "model": model, "t": t,
                              "raw": " ".join(m["message"] for m in ms)})

rng = random.Random(20261127)
rng.shuffle(items)
for i, it in enumerate(items, 1):
    it["id"] = f"Y{i:03d}"
    it["blinded"] = blind(it["raw"])

Path("key_controls.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
Path("sheet_controls.txt").write_text("\n\n".join(f"{it['id']}: {it['blinded']}" for it in items))
print(len(items), "items")
