# First complete pretrained tracker run

Accepted: 61/61 motions successful, 12,568 video frames at 640×480/30 fps, finite traces, exact joint/controller audit, process and parent exit 0, checked cleanup. See `measurements.json`, `media-validation.json`, `trace-audit.json`, `outcome.json` and `artifact-manifest.json`. `milestone1_complete: false` in the per-run outcome means this run alone does not establish the complete milestone; aggregate acceptance is recorded separately.

This first snapshot serialized MDP component objects as Python representations. The pinned sidecar hash preserves their exact source. Later runs serialize their full compute function/bindings/parameters without changing evaluation behavior.
