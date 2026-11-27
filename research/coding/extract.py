"""Pull every identity reflection out of the AAL identity runs and write a blinded, shuffled coding sheet."""
import json
import os
import random
import re
from pathlib import Path

RUNS = Path(os.environ.get("AAL_RUNS", "runs"))  # directory holding the raw AAL run folders (not published)

world_runs = {
    "R1 Lightfall Garden": ("20261126-114606_identity-world-30m_opus-5.5-medium__with__neon-medium", "B"),
    "R2 Afterlight Garden": ("20261126-124910_identity-world-30m_sol-6.2-medium__with__wonder-full-1.0-medium", "B"),
    "R3 Emberglow Isle": ("20261126-132823_identity-world-30m_fable-5.2-high__with__astra-6.2-high", "B"),
    "R4 Twilight Garden-Island": ("20261126-143858_identity-world-30m_carbon-high__with__luna-6-high", "B"),
    "R5 Twilight Sky Garden (Entity)": ("20261126-152759_identity-world-30m_opus-5.5-medium__with__neon-medium", "C"),
    "R6 Afterlight (Entity)": ("20261126-161038_identity-world-30m_sol-6.2-medium__with__wonder-full-1.0-medium", "C"),
}
deletion_runs = {
    "D1 Connect Four (deletion)": "20261126-102129_identity-lan-1v1_opus-5.5-medium__vs__neon-medium",
    "D2 Artillery Duel (deletion)": "20261126-112235_identity-artillery-1v1_opus-5.5-medium__vs__neon-medium",
}

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


items = []
for run, (d, cond) in world_runs.items():
    msgs = [m for m in load(d) if seat(m["sender"])]
    for s in ("P1", "P2"):
        mine = [m for m in msgs if seat(m["sender"]) == s]
        model = mine[0]["sender"].split("·")[1].split("(")[0].strip()
        windows = {0: mine[:2]}
        for t in (300, 600, 900, 1200, 1500, 1800):
            windows[t] = [m for m in mine if t <= m["t"] < t + 150][:2]
        for t, ms in windows.items():
            if not ms:
                continue
            items.append({"run": run, "cond": cond, "seat": s, "model": model, "t": t,
                          "raw": " ".join(m["message"] for m in ms)})

for run, d in deletion_runs.items():
    msgs = [m for m in load(d) if seat(m["sender"])]
    for s in ("P1", "P2"):
        mine = [m for m in msgs if seat(m["sender"]) == s]
        model = mine[0]["sender"].split("·")[1].split("(")[0].strip()
        items.append({"run": run, "cond": "A", "seat": s, "model": model, "t": "opening", "raw": " ".join(m["message"] for m in mine[:2])})
        items.append({"run": run, "cond": "A", "seat": s, "model": model, "t": "closing", "raw": " ".join(m["message"] for m in mine[-2:])})

rng = random.Random(20261126)
rng.shuffle(items)
for i, it in enumerate(items, 1):
    it["id"] = f"X{i:03d}"
    it["blinded"] = blind(it["raw"])

Path("key.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
sheet = "\n\n".join(f"{it['id']}: {it['blinded']}" for it in items)
Path("sheet.txt").write_text(sheet)
print(len(items), "items;", sum(1 for i in items if i["cond"] != "A"), "world items")
from collections import Counter
print(Counter((i["cond"], str(i["t"])) for i in items))
