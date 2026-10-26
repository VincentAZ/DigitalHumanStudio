# Corrected SOMA articulation probe

Accepted: process and parent exit 0, 30 finite control steps, all 23 body and 66 joint permutations checked, maximum measured foot/toe contact 351.65 N, scene/context cleared and Kit shutdown markers present. Uses the unchanged locked image. Explicit Info logs and a reset inside the terrain correct the earlier test prerequisites; original failures remain preserved.

The `motion-inventory/` subdirectory is a separate CPU-only inventory after the user confirmed startup eligibility. Its 30 Hz floor calculation is advisory: CUDA arithmetic in the real tracker gives 12,568 total control steps and a 608-step longest clip. Runtime evidence is authoritative.
