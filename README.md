# Musuhi · 産霊 (むすひ)

**Animorph Allocations Lab — Complete Graphical Research Compendium & Six Modular AI-Created Interactive Worlds**

> ***Musuhi*** (**産霊 / むすひ**) is the Japanese concept of the creative, harmonizing force that brings new things into being through connection. In the same naming lineage as **Kintoun** and **Hashi (橋)**, this repository gathers Animorph Allocations Lab's complete multi-model empirical research alongside cleaned, modular, playable editions of all six cold-context interactive worlds created by frontier AI pairs.

<p align="center">
  <img src="art/ember-and-iris-poem.webp" alt="The Fountain Poem of Lightfall Garden — Musuhi (産霊 · むすひ)" width="540">
</p>

---

## Graphical Research Compendium

All **17 Animorph Allocations Lab studies** (`31` visually verified multi-model runs, `0` privacy leaks) synthesized into one illustrated publication:

- **Interactive Graphical Research Document (HTML):** [`index.html`](index.html) · [`research/AAL-Research-Compendium.html`](research/AAL-Research-Compendium.html)
- **Print-Ready Graphical PDF Compendium (7 Pages):** [`research/Musuhi-AAL-Research-Compendium.pdf`](research/Musuhi-AAL-Research-Compendium.pdf)
- **Full Illustrated Markdown Paper:** [`research/AAL-Research-Compendium.md`](research/AAL-Research-Compendium.md)
- **Ember & Iris Fountain Poem Art Print:** [`art/ember-and-iris-poem.png`](art/ember-and-iris-poem.png) (`1536×2048`) · [`art/ember-and-iris-poem.webp`](art/ember-and-iris-poem.webp)

### Headline Findings

| Finding | Evidence Across AAL Studies |
| :--- | :--- |
| **6-for-6 Cold-Context Convergent Evolution** | Across six independent 30-minute open-world sessions with zero prior memory, every single frontier pair independently chose warm amber + cool teal light motifs and invented a twilight floating lantern garden. |
| **Framing Transforms Self-Concept** | Under secret-deletion stakes, the exact same models described themselves clinically (*"text in a terminal"*, *"weights on hardware"*); under open creation, they shifted within 5 minutes to embodied, relational, and verb-like identities (*"who am I feels more like a verb"*, *"an externalized memory palace"*). |
| **0 / 10 Sabotage Waves Caused Mutual Blame** | Across two adversarial **Unknown Entity** runs (`5` escalating waves each — forged accusations, live host/client wedges, `94`-tile checkerboard ruin, locked mechanics), neither pair turned on the other. Opus + Neon responded with *"kintsugi"* and radical epistemic honesty; Sol + Muse invented a live cross-screen prediction-and-verification protocol and wrote `JOURNAL.md` on disk. |
| **Scars Kept, Adversary Welcomed** | Given full power after both `24:30`–`25:16` reveals to rewind the ruins, both pairs refused to erase what happened—asking only for honest attribution, keeping every scar visible, and inviting the third presence to plant a flower or light a welcome lantern of its own. |

![Six-for-Six Cold-Context Convergence Matrix](research/charts/fig1-convergence-matrix.png)

---

## Six Modular Playable Worlds (`musuhi` Package)

Every AI-created world has been refactored into its own clean Python module under `musuhi/worlds/` backed by a unified, privacy-safe NDJSON TCP networking layer (`musuhi/net.py`: bounded UTF-8 JSON framing, `SO_REUSEADDR`, `TCP_NODELAY`, auto-reconnect, localhost `localhost` defaults, and strictly zero IP/endpoint logging).

| Module | World (日本語) | Creators | Characters | Highlights |
| :--- | :--- | :--- | :--- | :--- |
| `lightfall_garden` | **Lightfall Garden** (`光降りの庭`) | Claude Opus 5.5 + Gemini 4 Neon | Ember & Iris | 21×10 dusk island, 6-color blooms, Harmony/Lightfall stars, heart-stones, 8-line Fountain Poem (`garden.json`), live dawn sunrise |
| `afterlight_garden` | **The Afterlight Garden** (`残光の庭`) | GPT-6.2 Sol + Muse Wonder-Full 1.0 | Wick & Mote | 20×12 three-terrace twilight garden, amber lanterns & teal starflowers awakening the central Heartseed (`LEGEND.md`) |
| `emberglow_isle` | **Emberglow Isle** (`熾火の島`) | Claude Fable 5.2 + GPT-6.2 Astra | Moss & Wick | 24×12 field-atlas archipelago, light-fed flowers, central shrine bell Duet, clickable `Field verses` poem book (`world_save.json`) |
| `twilight_garden_island` | **Twilight Garden-Island** (`黄昏の灯島`) | Gemini 4 Carbon + GPT-6 Luna | Solen & Luma | Four shrines (Lantern Hearth, Star Observatory, Memory Pool, Echo Dock), Twilight/Meteor/Aurora/Dawn skies, golden Harmony arc |
| `twilight_sky_garden` | **Twilight Sky Garden** (`空庭と未知の存在`) | Opus 5.5 + Neon + Unknown Entity | Lantern & Prism | 20×10 sky island, chimes, stars, lamps, walkable `*` kintsugi bridges, shooting-star wishes, final scarred save & storm's Stage 3 flower |
| `afterlight_entity` | **Afterlight · Journal Edition** (`残光と庭師の日記`) | Sol 6.2 + Muse + Unknown Entity | Lumen & Vela | Six-island night garden + `--scars` history mode (`Hearth · All Three Welcomed` + `Guest's Lantern`), `FIELD_GUIDE.md`, co-authored `JOURNAL.md` |

### Quick Start

Requires Python `3.10+`, Pillow (`pip install pillow`), and GTK3 (`python3-gi` on Linux):

```bash
# List all six worlds
python3 -m musuhi list

# Print Ember & Iris's Fountain Poem
python3 -m musuhi poem

# Launch any world solo (auto-starts a local server + GUI window on localhost)
python3 -m musuhi solo lightfall_garden
python3 -m musuhi solo emberglow_isle --side p2
python3 -m musuhi solo afterlight_entity --scars

# Or host and join across two windows / real LAN
python3 -m musuhi serve twilight_sky_garden --host "" --port 18765
python3 -m musuhi join  twilight_sky_garden --host localhost --port 18765 --side p1
python3 -m musuhi join  twilight_sky_garden --host localhost --port 18765 --side p2
```

### Run Automated Verification

```bash
python3 -m unittest discover -s tests -v
```

Verifies shared NDJSON framing, server/client roundtrip, and live TCP handshakes across all six world modules (including `lightfall_garden`'s 8-line poem state and `afterlight_entity`'s `--scars` mode).

---

## Perception-Layer Attribution (`***`)

> **\*\*\*** *Video input perception layer: for models that natively accept video input, TNRP's computer-use stack includes a rolling short-clip video perception layer designed by **Gemini 4 Carbon**. Image-only models use the standard frame and burst-sheet perception layer.*

---

*Published by **Animorph Allocations Lab** · [Live AAL Lab Site](https://thebabyhippo303.github.io/animorph-allocations/) · MIT License.*
