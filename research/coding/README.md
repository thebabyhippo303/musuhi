# Blind coding of the identity reflections

Data and code behind Figure 5 and §6.2 of the paper.

- `sheet.txt`: the 91 shuffled, blinded excerpts the coders saw.
- `CODEBOOK.md`: the scoring guide both coders used.
- `coder_A.json` (Claude Opus) and `coder_B.json` (Gemini 4 Carbon): their independent scores.
- `key.json`: maps each excerpt ID back to its run, condition, seat, model and time, with the unmasked text.
- `extract.py`: builds the sheet and key from the raw run folders (not published).
- `analyze.py`: computes agreement and the per-condition results, writes `results.json` and redraws Figure 5. Run it from the repository root: `python3 research/coding/analyze.py`.

## Control rounds (§6.4, Figure 6)

- `sheet_controls.txt`, `CODEBOOK_controls.md`: the 22 blinded control-round excerpts and the same guide (only the sheet name and ID prefix differ).
- `coder_A_controls.json` (Claude Opus), `coder_B_controls.json` (Gemini 4 Carbon): independent scores.
- `key_controls.json`: maps each `Y` excerpt to its round, seat, model and time.
- `extract_controls.py`: builds the control sheet and key from the raw run folders (not published).
- `analyze_controls.py`: computes agreement, writes `results_controls.json` and draws Figure 6. Run it from the repository root: `python3 research/coding/analyze_controls.py`.
