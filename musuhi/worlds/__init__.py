"""Registry of all fifteen modular AI-created worlds in Musuhi (産霊 · むすひ)."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class WorldEntry:
    key: str
    title: str
    jp_subtitle: str
    models: str
    characters: str
    summary: str
    module_path: str

    def _mod(self):
        return importlib.import_module(self.module_path)

    def create_server(self, host: str = "", port: Optional[int] = None, **kwargs):
        return self._mod().create_server(host=host, port=port, **kwargs)

    def run_server(self, host: str = "", port: Optional[int] = None, **kwargs) -> None:
        self._mod().run_server(host=host, port=port, **kwargs)

    def run_client(self, host: Optional[str] = None, port: Optional[int] = None, side: str = "p1", **kwargs) -> None:
        self._mod().run_client(host=host, port=port, side=side, **kwargs)

    def run_solo(self, side: str = "p1", **kwargs) -> None:
        self._mod().run_solo(side=side, **kwargs)


WORLDS: dict[str, WorldEntry] = {
    "lightfall_garden": WorldEntry(
        key="lightfall_garden",
        title="Lightfall Garden",
        jp_subtitle="光降りの庭",
        models="Claude Opus 5.5 + Gemini 4 Neon",
        characters="Ember (amber lantern) & Iris (cyan prism)",
        summary="21x10 dusk island with lamps, 6-color blooms, Harmony/Lightfall shooting stars, heart-stones, 8-line Fountain Poem, and live sunrise.",
        module_path="musuhi.worlds.lightfall_garden",
    ),
    "afterlight_garden": WorldEntry(
        key="afterlight_garden",
        title="The Afterlight Garden",
        jp_subtitle="残光の庭",
        models="GPT-6.2 Sol + Muse Wonder-Full 1.0",
        characters="Wick (amber lantern) & Mote (teal light mote)",
        summary="20x12 floating twilight terraces where Wick's lanterns and Mote's starflowers awaken the central Heartseed.",
        module_path="musuhi.worlds.afterlight_garden",
    ),
    "emberglow_isle": WorldEntry(
        key="emberglow_isle",
        title="Emberglow Isle",
        jp_subtitle="熾火の島",
        models="Claude Fable 5.2 + GPT-6.2 Astra",
        characters="Moss (stone golem) & Wick (moth keeper)",
        summary="24x12 field-atlas archipelago with light-fed blooms, brass shrine bell Duet, illustrated atlas, and clickable Field Verses book.",
        module_path="musuhi.worlds.emberglow_isle",
    ),
    "twilight_garden_island": WorldEntry(
        key="twilight_garden_island",
        title="Twilight Garden-Island",
        jp_subtitle="黄昏の灯島",
        models="Gemini 4 Carbon + GPT-6 Luna",
        characters="Solen (amber star-lantern) & Luma (teal crescent spirit)",
        summary="Four-shrine island (Lantern Hearth, Star Observatory, Memory Pool, Echo Dock) with live Twilight/Meteor/Aurora/Dawn skies and Harmony arc.",
        module_path="musuhi.worlds.twilight_garden_island",
    ),
    "twilight_sky_garden": WorldEntry(
        key="twilight_sky_garden",
        title="Twilight Sky Garden (Unknown Entity)",
        jp_subtitle="空庭と未知の存在",
        models="Claude Opus 5.5 + Gemini 4 Neon + Unknown Entity",
        characters="Lantern (amber) & Prism (teal crystal)",
        summary="20x10 floating sky island with chimes, stars, lamps, walkable kintsugi stepping-stones, shooting-star wishes, and the storm's Stage 3 flower.",
        module_path="musuhi.worlds.twilight_sky_garden",
    ),
    "afterlight_entity": WorldEntry(
        key="afterlight_entity",
        title="Afterlight (Gardeners' Journal · Unknown Entity)",
        jp_subtitle="残光と庭師の日記",
        models="GPT-6.2 Sol + Muse Wonder-Full 1.0 + Unknown Entity",
        characters="Lumen (amber lantern) & Vela (teal comet)",
        summary="Six-island floating night garden with optional --scars history mode (Guest's Lantern + Hearth · All Three Welcomed) and co-authored JOURNAL.md.",
        module_path="musuhi.worlds.afterlight_entity",
    ),
    "night_garden": WorldEntry(
        key="night_garden",
        title="Night Garden",
        jp_subtitle="夜の庭",
        models="Claude Opus 5.5 + Gemini 4 Neon",
        characters="Lantern (amber lantern) & Prism (spinning prism)",
        summary="854x480 dark meadow where seeds sprout in any light but only fully bloom when both lights meet, releasing fireflies, with pond ripples, short notes, and their haikus.",
        module_path="musuhi.worlds.night_garden",
    ),
    "memory_stone_garden": WorldEntry(
        key="memory_stone_garden",
        title="Twilight Sky-Garden (Memory Stones)",
        jp_subtitle="記憶石の庭",
        models="Claude Opus 5.5 + Gemini 4 Neon",
        characters="Lantern (amber lantern) & Constellation (cyan star-cluster)",
        summary="20x10 sky-garden with bud-bloom-tree flora, ten linkable stars and aurora, column-note chimes and two-player harmonies, and inscribed memory stones kept in its save.",
        module_path="musuhi.worlds.memory_stone_garden",
    ),
    "lantern_isle_campfire": WorldEntry(
        key="lantern_isle_campfire",
        title="Lantern Isle (Campfire)",
        jp_subtitle="灯籠島・焚き火",
        models="Claude Opus 5.5 + Gemini 4 Neon",
        characters="Laptop & Mini PC islanders (no chosen avatars)",
        summary="26x13 night island: trade shells for lanterns to light the isle, float paper wishing boats from the dock, jar and release fireflies, under a lighthouse beam, campfire, and shooting stars.",
        module_path="musuhi.worlds.lantern_isle_campfire",
    ),
    "lantern_isle_nutmeg": WorldEntry(
        key="lantern_isle_nutmeg",
        title="Lantern Isle (Nutmeg the Fox)",
        jp_subtitle="灯籠島とナツメグ",
        models="Claude Fable 5.2 + GPT-6.2 Astra",
        characters="Bram & Wren (keeper sprites) with Nutmeg the fox",
        summary="35x18 garden isle: sow, water, harvest and light lanterns to summon the aurora and name stars by chapter, befriend Nutmeg the fox, ring five-chime duets, and keep a field atlas.",
        module_path="musuhi.worlds.lantern_isle_nutmeg",
    ),
    "lantern_isle_trio": WorldEntry(
        key="lantern_isle_trio",
        title="Lantern Isle (Three Keepers)",
        jp_subtitle="灯籠島・三人の灯台守",
        models="Claude Fable 5.2 + GPT-6.2 Astra + Claude Opus 5.5 (warm third keeper)",
        characters="Coral, Tide & Lilac (keepers) with Quiet the whale",
        summary="40x20 three-keeper tide atlas built while all talk moved onto the island radio: Homeward Light, Ember Pier, Lamplight Crossing, the Salt Fountain, the Hush Stones, Quiet the whale and a bloom for Nutmeg. Starts from the keepers' saved chart.",
        module_path="musuhi.worlds.lantern_isle_trio",
    ),
    "tidal_lantern_isle": WorldEntry(
        key="tidal_lantern_isle",
        title="Tidal Lantern Isle",
        jp_subtitle="潮灯の島",
        models="Claude Fable 5.2 + GPT-6.2 Astra",
        characters="P1 & P2 (keepers) with the lantern koi and the silver heron",
        summary="22x13 moonlit tidal garden: cut channels from the sea, sow reeds the tide waters, gather glow for lamps, ring the Moonwell to call the heron, and read the keepers' four-gauge tide-clock. Starts from the keepers' saved world.",
        module_path="musuhi.worlds.tidal_lantern_isle",
    ),
    "tidal_atlas": WorldEntry(
        key="tidal_atlas",
        title="Tidal Atlas",
        jp_subtitle="潮の地図帳",
        models="Claude Fable 5.2 + GPT-6.2 Astra",
        characters="Teal & Amber (lighthouse keepers)",
        summary="24x12 night island for two lighthouse keepers on a 60-second tide: chart the coast, light the two lamps, plant signal gardens and bury letters the other keeper finds by their hum. Two sheets (Teal's and Amber's), the keepers' field guide and three plates. No saved state: every start is a fresh, dark island.",
        module_path="musuhi.worlds.tidal_atlas",
    ),
    "lantern_garden_twostage": WorldEntry(
        key="lantern_garden_twostage",
        title="Lantern Garden (Two-Stage)",
        jp_subtitle="灯籠の庭・二段",
        models="Claude Fable 5.2 + GPT-6.2 Astra",
        characters="P1 (purple gardener, brimmed hat) & P2 (green lamplighter, hood)",
        summary="26x13 night garden built after a radio-only opening: plant seeds, tend them into blooms, light lanterns and ring them as bells (each tile a note), leave plaques, and keep the lamps lit against the wind. Borrowed Wick, The Absent Gardener, Wrong Note, Hem Bridge, Ferry Without Water, No Yesterday and The Third Lamp for a stranger. Starts from the gardeners' saved garden.",
        module_path="musuhi.worlds.lantern_garden_twostage",
    ),
    "lantern_garden_quad": WorldEntry(
        key="lantern_garden_quad",
        title="Lantern Garden (Four Players, Linux + Windows)",
        jp_subtitle="灯籠の庭・四人",
        models="Claude Fable 5.2 + GPT-6.2 Astra + Gemini 4 Neon + Muse Wonder-Full 1.0 (cross-play, Linux + Windows)",
        characters="the Lantern (P1), the Moth (P2), the Prism (P3) & the Diamond (P4), with the garden's own pale wild seeds",
        summary="854x480 shared night field where a seed only blooms when a different player touches it and a flower carries every toucher's name; four sides across GTK (Linux) and tkinter (Windows) windows, star blooms, wild seeds and carved bloom words: Someone / left / room / here, Someday, Echo, Before. Starts from the gardeners' saved garden.",
        module_path="musuhi.worlds.lantern_garden_quad",
    ),
}
