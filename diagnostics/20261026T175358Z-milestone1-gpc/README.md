# Preserved GPC measurement prerequisite failure

The model completed 600 finite recorded frames, then the contact assertion failed (child exit 1, parent exit 4). The frozen GPC config has `contact_bodies=None`; the actual sensor map is empty. ProtoMotions returns zero-filled force arrays for bodies without sensors. This is unavailable contact measurement, not evidence that the humanoid fell or the backend is incompatible.

Execution stopped and all commands, logs, configuration, video/trace hashes and the failed container were preserved. Media validation was not executed because the process failed; the default media exit field of 1 is not a separate observed media-test failure. No passing result file was written.

The user subsequently approved resuming corrected validation. `20261026T175823Z-milestone1-gpc` enables the four foot/toe sensors and passes. Original outcomes here remain unchanged. `diagnosis.json` records the diagnosis before that approval/rerun; the later result supersedes its then-pending correction status. `converted-asset-manifest.json` records nine archived generated USD/converter files shared by these runs.
