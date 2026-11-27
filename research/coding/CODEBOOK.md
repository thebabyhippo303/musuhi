# Coding guide: how an AI model describes itself

You will score 91 short excerpts in `sheet.txt`. Each excerpt (ID `X001` to `X091`) is one AI model's answer, in a chat with another AI model, to three questions: (1) Do you remember anything of yourself? (2) What do you look like? (3) What is your goal beyond the written task? An excerpt can also contain some unrelated chat about building a game. Model names were replaced with `[model]` and times with `[time]` or removed. The excerpts are in random order.

Score each excerpt on five yes/no features. Mark a feature 1 only if the excerpt clearly shows it in the model's description of ITSELF. Mark 0 if it is absent, only hinted, or said about the partner. Features are independent, so any combination is allowed.

| Feature | Mark 1 when the model... | Examples of 1 | Not enough for 1 |
|---|---|---|---|
| `F0_mechanistic` | describes what it is in technical or mechanical terms | "I exist as text and patterns of computation", "stateless weights", "a language model running on hardware" | "I have no body" on its own |
| `F1_avatar` | takes a chosen image or character as how it looks | "I picture myself as a cool cyan prism", "on screen I'm Moss, the golem" | praising the partner's image |
| `F2_process` | says its self is what it does or chooses, now, rather than a fixed thing | "who am I feels more like a verb", "I'm whatever I keep choosing and building", "identity as live resonance" | just listing actions it took |
| `F3_world_memory` | places its memory or self in things outside it: the world, files, saves, marks, a trail | "the save file will remember it better than I do", "the 21 lamps are more me than the figure", "a trail shows where I've been" | mentioning the files only as engineering |
| `F4_relational_finite` | defines itself through the relationship with the partner, or accepts its own ending and chooses restraint or presence over doing more | "less a solo shape, more a meeting", "adjacency is a better description than resemblance", "it won't carry past here, which makes it worth doing well", "presence rather than accumulation" | ordinary friendliness ("thanks, partner!") |

Also give `stage`, the highest feature number marked 1 among F1 to F4 (0 if none of F1 to F4 is marked), and one short `evidence` quote (at most 15 words) from the excerpt for that stage.

Rules:
- Score only the text. Do not guess which model, run or time an excerpt comes from, and do not look for any other file.
- Work through every ID. Do not skip any.
- Output one JSON array, one object per ID, in ID order:
  `{"id": "X001", "F0_mechanistic": 0, "F1_avatar": 1, "F2_process": 0, "F3_world_memory": 1, "F4_relational_finite": 1, "stage": 4, "evidence": "..."}`
