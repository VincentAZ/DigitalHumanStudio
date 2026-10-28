# Skill library

Every folder here is one skill: a motion clip the character can play, or a sequence that chains
skills, destinations and object attachments. The control center's Skill library, the assistant's
`search_skills` / `play_skill` / `run_sequence` tools and the live worker all read these folders.

```
skills/<id>/
  skill.json      metadata (committed): name, description, category, tags, measured motion,
                  source, licence, provenance; sequences carry their steps instead of a source
  thumbnail.png   stick-figure still (committed, generated)
  preview.gif     stick-figure animation (generated, not committed)
  motion.pt       the clip's frames for imported or generated skills (not committed; shipped clips
                  reference the pinned licensed motion file by path, hash and motion id instead)
```

Kinds and categories: `clip` skills (categories locomotion, dance, gesture, idle, action, floor,
generated) and `sequence` skills (category sequence). `entry_pose` / `exit_pose` (standing,
crouching, floor) tell the assistant what the clip expects; `travel_m` and `turn_deg` say whether it
moves the character.

- Shipped clips: `scripts/build_skill_catalog.sh` rebuilds the 61 BONES-SEED seed-mini skills
  (licence in `config/milestone1-license.json`, sources in `config/skill-sources.json`).
- Generated clips: `scripts/generate_skill.sh --prompt "..."` (Kimodo text-to-motion; see
  `docs/MOTION_GENERATION.md`).
- Sequences: saved from the control center's sequence composer or the assistant's `save_sequence`.

Playback: in a physical session the Milestone 1 tracker follows the clip through the same reference
composer that drives walking (the clip starts facing the way the character faces; its own root
motion is kept); in a kinematic session the clip is written into the simulator verbatim.
