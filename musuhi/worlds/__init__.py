"""Registry of all six modular AI-created worlds in Musuhi (産霊 · むすひ)."""

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
}
