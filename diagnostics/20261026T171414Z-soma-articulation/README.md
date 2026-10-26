# SOMA articulation probe — acceptance stopped

The writable-working-directory repair cleared the earlier launcher prerequisite. The pinned ProtoMotions Isaac Lab adapter converted and loaded SOMA with 23 bodies and 66 DOFs. Its semantic/body permutations passed the script's checks. Four configured foot/toe contact sensors were present. Thirty zero-action control steps at 30 Hz (120 Hz physics) produced finite sampled states. The child recorded cleared scene/context and exited 0.

**The wrapper returned 4, not a pass.** It requires Kit shutdown log markers. The selected headless experience (`vendor/IsaacLab/apps/isaaclab.python.headless.kit`, lines 19–20) sets both log levels to `Warn`, so the Info-level lifecycle records are absent. The existing M0 rendering experience is different. The outcome has not been rewritten to a pass or its log requirement removed.

The synthetic reset was at (0, 0, 0.95), while the configured flat terrain spans x=[0,279.9], y=[0,309.9]. The robot's feet extend beyond that corner and move into negative coordinates during the probe. All measured foot contact forces were zero. This trace does not validate contact behavior or balancing; no pretrained policy or dataset motions were run. The probe's finite-state checks alone are insufficient for M1 acceptance.

`analysis.json` records the trace summary, source logging defaults and generated USD asset hashes. The complete scene, one-second trace and copied conversion assets are under `artifacts/milestone1/articulation-20261026T171414Z/`. Full logs, source scripts, serialized request configuration, actual mappings, process exit code, wrapper result and retained-container inspection are in this evidence directory.

Next proposed corrections: explicitly request Info-level Kit logging and place the synthetic reset inside the flat terrain with initial clearance; require nonzero contact-force evidence. These changes have not been executed. Further Isaac runs stopped at this gate under AGENTS.md. The trace is not evidence that the host OS or driver is incompatible; no backend, source revision, threshold, image, OS or driver was changed.
