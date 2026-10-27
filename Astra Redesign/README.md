# Astra UI mockup

A standalone, interactive design study for Digital Human Studio, based on the supplied October 27, 2026 UI brief. All source, illustrations, documentation, and verification artifacts for this mockup live in this folder.

Open `index.html` directly in a modern browser. No installation, build, dependencies, network, or backend is required.

For a local HTTP preview, run from any directory:

```bash
bash "/home/vincent/Repos/DigitalHumanStudio/Astra Redesign/preview.sh"
```

Then visit http://localhost:8787. The server only serves this folder and binds to localhost.

The design includes Live scene, Skill library, Project, an always-visible desktop assistant, provider settings, command acknowledgements, job output, and persistent status indicators. It adapts to smaller screens; the assistant moves below the workspace on phones.

Try clicking the room map, pausing, resetting, recording, or giving the scripted assistant a direction. Enter a push of 3 m/s to trigger a fall and require a reset. End the demo session to switch scenes; starting again previews progress. The assistant can be interrupted, or given another message, while waiting for the character. Skills support search, category filters, and concept previews.

Keyboard shortcuts: Space pauses/resumes; R resets; Shift+R toggles recording; / opens skill search; Ctrl+Enter sends a message. The room map supports arrow keys followed by Enter. Escape closes a dialog or expanded preview.

## Scope

- Every session, command, recording, assistant reply, GPU metric, and runtime status in the UI is illustrative browser state.
- The scene and skill thumbnails are original SVG illustrations made for this mockup, not simulation output or third-party assets.
- Only the existing tracker is marked available. Future motion clips are explicitly marked as concepts with licences not yet sourced.
- No API calls, provider SDKs, backend imports, project reads, launchers, real recordings, or persistent storage are used.
- Credential inputs are disabled. No keys are accepted or stored.
- Project facts are a historical design snapshot from the supplied project documentation, not a live environment probe.
- No existing project source or configuration was changed. No commit was made.

Implementation: plain HTML, CSS, and JavaScript. To discard the design, remove this folder; it has no external integration points.

## Verification

Browser checks passed in Chrome 156.0.8078.47 on October 27, 2026. All three views were checked for horizontal overflow at 320, 390, 600, 768, 1024, 1280, 1440, 1600, and 1920 pixels. Interaction checks covered map clicks and arrival, pause, reset, recording, fall rejection, out-of-bounds destinations, session lifecycle, assistant interruption with manual controls, providers, skills, dialogs, and the output drawer. No browser JavaScript exceptions, duplicate IDs, or external requests were detected in the final pass.

- [Machine-readable verification report](verification/report.json)
- [Live scene screenshot](verification/live-desktop.png)
- [Skill library screenshot](verification/skills-desktop.png)
- [Project screenshot](verification/project-desktop.png)
- [Mobile screenshot](verification/live-mobile.png)

`verify.mjs` is a standalone browser check with no package dependencies. Start the local preview server and a disposable headless Chrome instance with remote debugging on port 9224, then run `node "/home/vincent/Repos/DigitalHumanStudio/Astra Redesign/verify.mjs"`. Set `ASTRA_CDP_PORT` if needed. It writes only to this folder's `verification/` directory. Screenshots and temporary browser profiles are locally ignored by Git. Node syntax and launcher shell syntax were also checked.

These checks validate the design prototype only. No backend, provider, Isaac, or motion-quality validation was performed.
