"""Render preserved traces only; does not import or launch Isaac."""
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
root = Path("/workspace")
out = Path(__file__).parent
fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), constrained_layout=True)
for folder, label, color in [("20261026T160211-runtime", "60 Hz (contact threshold failed)", "#b54530"), ("20261026T160349-runtime", "120 Hz (physics passed; exit 139)", "#2679a4")]:
    d = json.loads((root / "diagnostics" / folder / "run-1.trajectory.json").read_text())
    t = [s["time"] for s in d["samples"]]
    z = [s["position"][2] for s in d["samples"]]
    for ax in axes:
        ax.plot(t, z, label=label, color=color, linewidth=1.7, marker=".", markersize=3)
for ax in axes:
    ax.axhline(.25, color="#666666", linestyle=":", label="Resting center: 0.25 m")
    ax.axhline(.20, color="#b54530", linestyle="--", label="Acceptance boundary: 0.20 m")
    ax.set_xlabel("Time since measured loop began (s)")
    ax.set_ylabel("Cube center height (m)")
    ax.grid(alpha=.2)
axes[0].set(xlim=(0, 1), ylim=(.1, 2.05), title="Drop and settling")
axes[1].set(xlim=(.48, .68), ylim=(.17, .40), title="Contact detail (raw PhysX = asset readback)")
axes[0].legend(fontsize=8)
fig.suptitle("Same scene and thresholds; only physics timestep changed", fontsize=12)
fig.savefig(out / "contact-comparison.png", dpi=160)
fig.savefig(out / "contact-comparison.svg")
