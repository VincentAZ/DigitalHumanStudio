# Corrected GPC prior smoke test

Accepted: 600 finite control frames over 20 simulated seconds, complete 640×480/30 fps video, maximum measured foot/toe contact 1,486.49 N, child/parent exit 0 and checked shutdown. Independent trace/controller audit passed.

The recorded overlay adds four measurement sensors to the source configuration, which disables them. `observe_contacts=false` keeps policy inputs unchanged. The earlier and corrected runs have exactly equal actions, joint positions and body positions at all 600 steps (`sensor-change-comparison.json`). This establishes loaded-prior inference, not learned crouching, destination walking or task acceptance.
