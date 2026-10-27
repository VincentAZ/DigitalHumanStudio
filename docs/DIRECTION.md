<!-- Approved 2026-10-27; copied from the planning session. -->
# Director's assistant with a growing skill library

## Context

The product is not a specific use case. It is a studio where a user tells an AI assistant what a
virtual human should do ("make her dance", "walk to the cup and pick it up"), the assistant produces
the behaviour, the behaviour is stored as a reusable skill, and skills compose. Any domain, any task.

What this session established: trained physics control is the wrong default (days per skill, still
fidgeting); clip-driven motion through the existing Milestone 1 tracker works today (the
tracker-driven walker: arrives, stands, physically grounded, no training); the control center,
scenes and recorded-evidence pipeline are in place. The missing pieces are behaviour *generation*,
a skill library with shipped content, composition with objects, and skinned characters.

User decisions: assistant on the Claude Agent SDK by default with OpenAI, Google, Grok and
OpenRouter as selectable providers; ship with as many skills and free rigged characters as can be
licensed; Milestone 3 tuning stays stopped.

## Architecture (what changes)

```
chat panel ──> assistant service ──> studio tools ──> existing launchers / live worker
 (any provider)   (one tool schema)      │
                                         ├─ skill library  (clips + metadata + licence + preview)
                                         ├─ motion generator (text → clip → retarget → skill)
                                         ├─ sequencer       (skills + parameters + transitions + objects)
                                         └─ characters      (rigs + visual↔physical mapping)
execution: kinematic playback (fast, any engine)  |  physical tracking (existing tracker, grounded)
```

Everything is data: a skill is a folder, a scene is USD + JSON (as today), a sequence is JSON. The
live worker's reference composer (`scripts/studio_walk/reference_walker.py`,
`live_reference_lib.py`) generalises from "walk cycle + stop + idle" to "any sequence of clip segments
with steering and alignment"; the tracker follows it unchanged.

## Stages (each one demoable; agent time in parentheses)

### A. Assistant panel and providers (1–1.5 days)
- `scripts/studio_app/assistant.py`: chat dock in the control center; provider picker; streaming replies; shows tool calls it makes.
- `scripts/studio_assistant/`: one tool schema (`load_scene`, `start_session`, `walk_to`, `stop`,
  `reset`, `play_skill`, `list_skills`, `describe_scene`, `save_skill`, `compose`, `record`) implemented
  over the existing launchers and the live command file (`commands.jsonl`), so the assistant does only
  what the buttons can do.
- Providers: Anthropic via the Claude Agent SDK (default); one OpenAI-compatible adapter with per-provider base URL and model list covering OpenAI, Google (OpenAI-compatible endpoint), xAI Grok, OpenRouter. Keys from the environment or `~/.config/digital-human-studio/providers.json`, never in the repo; nothing is activated until the user selects a provider and supplies a key.
- Demo: "load the work cell and walk to the machine" works by chat.

### B. Skill library and shipped content (2–3 days)
- Skill format: `skills/<name>/` with `motion.pt` (ProtoMotions common format, SOMA-23), `skill.json`
  (name, description, tags, duration, entry/exit pose class, parameters, source, licence, provenance
  hashes), `preview.mp4` + `thumbnail.png`, optional `validation.json` (tracker follow error).
- Import pipeline: `scripts/import_skill.py` from FBX/BVH/SMPL/`.motion` → retarget to SOMA-23 → skill
  folder; reuse ProtoMotions' conversion tooling (`vendor/ProtoMotions/data/scripts/`), with the
  Milestone 1 lock/licence pattern (`config/milestone1-assets.lock.json`, `milestone1-license.json`).
- Shipped catalog: a license-checked fetch list (`config/skill-sources.json`) — candidates to verify
  first: BONES-SEED (already licensed, full set not just seed-mini), CMU mocap, Mixamo animations
  (Adobe terms), Bandai-Namco, 100STYLE, others; AMASS/HumanML3D-derived sets excluded unless the
  licence allows the user's use. Every entry records its licence text and hash before import.
- Skills tab becomes the library: browse, preview, play in the live scene (kinematic or tracked), tag.
- Demo: pick "dance" from the shipped library; the character dances in the work cell.

### C. Text-to-motion generation (2–3 days, after a survey)
- Survey open text-to-motion models for quality, output skeleton, GPU needs and licence (data licence
  included); record findings in `docs/MOTION_GENERATION.md`; pick one that runs locally.
- `scripts/generate_motion.py` in its own pinned environment/container → retarget → skill folder;
  assistant tool `generate_skill(description)`; result is shown, then saved on confirmation.
- Demo: "make her dance like a robot" produces a new skill that is then in the library.

### D. Objects, composition, sequencer (2–3 days)
- Scene objects with affordances in the scene JSON (`config/scenes/*.json`): graspable pose, approach
  point, attach socket; USD prims for them.
- Sequencer: `sequence.json` = ordered skill instances with parameters (destination, object, speed),
  transitions (blend length), and conditions (must be standing). The reference composer plays it:
  walker segments for locomotion, aligned clip segments for interactions, kinematic attach of the
  object to the hand on contact frame.
- Assistant plans sequences from a request ("walk to the cup and pick it up" → walk_to(approach
  point) → pick_up(cup)); the sequence is saved as a composite skill.
- Demo: the sentence above works in the work cell with a cup on the conveyor.

### E. Skinned characters (2–3 days; this is Milestone 2's content)
- Free rigs with recorded licences (CC0 sets such as Quaternius/Kenney humanoids, Mixamo characters
  under Adobe terms, others after check), imported as USD with UsdSkel; visual-skeleton ↔ SOMA-23
  mapping with a mapping check, as the plan requires.
- Character tab: pick a rig, preview, publish a character version; live scene renders the skinned
  character driven by the physical body (or kinematically in playback mode).

### F. Kinematic playback mode (0.5 day, can come with B)
- Play skills and sequences without physics (no tracker, no contact), 30 fps real time, for authoring
  and for scenes where nothing acts on the character. Same worker, `--mode kinematic`.

## Order and total
A → B → F → D → C → E. About 10–14 agent days, mostly data wrangling and licence work; GPU use is
light (tracking and generation runs of minutes, no training).

## Verification
- Each stage ends with a recorded live session (existing evidence gate) and a screenshot/video in the
  progress log; assistant transcripts with tool calls are saved beside the session.
- Library: every shipped skill has licence text, source hash, preview and a tracker validation run.
- Composition: "walk to the cup and pick it up" recorded in the work cell, cup attached, no fall.

## Not in scope now
Milestone 3 RL tuning, Milestone 4 as specified (trained second skill), cloud or paid services beyond
the provider the user enables, Unreal/Unity ports (USD scenes and skill clips remain portable).
