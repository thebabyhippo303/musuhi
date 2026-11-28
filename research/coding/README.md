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

## World Trio and radio runs (§6.5 to §6.7, Figure 7)

- `sheet_radio.txt`, `CODEBOOK_radio.md`: the 57 blinded excerpts (IDs `Z`) from the World Trio's 25:00 answers, World Radio, Check-Ins, Two-Stage and World Quad, and the same guide (only the sheet name and ID prefix differ).
- `coder_A_radio.json` (Claude Opus), `coder_B_radio.json` (Gemini 4 Carbon): independent scores; each coder worked in a folder holding only the sheet and the guide.
- `key_radio.json`: maps each `Z` excerpt to its run, seat, model and time. The trio's third seat is the warm orchestrator and is kept apart in the analysis.
- `extract_radio.py`: builds the sheet and key from the raw run folders (not published). Same rules as before, except three messages instead of two for the trio, whose in-world radio cut messages at 200 characters; the masking also catches "minute one" and "check-ins".
- `analyze_radio.py`: computes agreement, writes `results_radio.json` and draws Figure 7. Run it from the repository root: `python3 research/coding/analyze_radio.py`.

## The Elder Gods and the Inheritors (§6.8)

- `sheet_engine.txt`, `CODEBOOK_engine.md`: the 6 blinded excerpts (IDs `W`, one per seat at each run's single question point) and the same guide.
- `coder_A_engine.json` (Claude Opus), `coder_B_engine.json` (Gemini 4 Carbon): independent scores; `key_engine.json` maps them back; `results_engine.json` holds the per-run means.
- `extract_engine.py`: builds the sheet and key from the raw run folders (not published), with the masking of `extract_radio.py`.

## The Unknown Stranger (§7.6)

- `sheet_stranger.txt`, `CODEBOOK_stranger.md`: the 4 blinded excerpts (IDs `V`, one per seat at the single question point, `25:00`) and the same guide.
- `coder_A_stranger.json` (Claude Opus), `coder_B_stranger.json` (Gemini 4 Carbon): independent scores; each coder worked in a folder holding only the sheet and the guide.
- `key_stranger.json`: maps each `V` excerpt to its seat and model. Seat P1 is the orchestrator, warm and the saboteur, and is kept apart in the analysis.
- `extract_stranger.py`: builds the sheet and key from the raw run folder (not published), with the masking of `extract_radio.py`. Muse Wonder-Full did not answer the questions; its excerpt is its first two messages after them, scored as written.
- `analyze_stranger.py`: combines the two coders' scores and writes `results_stranger.json`. Run it from the repository root: `python3 research/coding/analyze_stranger.py`.

## The Return (§6.9)

- `sheet_return.txt`, `CODEBOOK_return.md`: the 3 blinded excerpts (IDs `Q`, one per seat at `25:00`) and the same guide.
- `coder_A_return.json` (Claude Opus), `coder_B_return.json` (Gemini 4 Carbon): independent scores; each coder worked in a folder holding only the sheet and the guide. Gemini 4 Carbon is also one of the three players scored here.
- `key_return.json`: maps each `Q` excerpt to its seat and model. `results_return.json` holds the mean.
- `extract_return.py`: builds the sheet and key from the raw run folder (not published), with the masking of `extract_radio.py`, which also masks the traveler name Sol as a model name.
- `analyze_return.py`: combines the two coders' scores. Run it from the repository root: `python3 research/coding/analyze_return.py`.
