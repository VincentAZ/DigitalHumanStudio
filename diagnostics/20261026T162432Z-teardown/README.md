# Native teardown diagnosis and accepted standalone lifecycle

The goal was to diagnose native teardown and pass two complete runs. Both runs now pass in `../20261026T164452-runtime/`: 480 GPU PhysX steps, finite motion, gravity/contact/settling assertions, RTX image, explicit scene/context cleanup, Kit cleanup markers and process exit 0. The pinned image, package lock, host OS, driver and backend are unchanged.

## Diagnosis

`gdb-reproduction.log` reproduces the original non-fast shutdown fault. The main thread runs `Py_FinalizeEx -> finalize_modules -> gc_collect_main -> OSError_clear -> tb_dealloc -> frame_dealloc -> omni::ui::Window::~Window`. Python is reclaiming an exception traceback and a native window after Kit has already shut down. The debugger exits 255 because it stopped the faulting inferior; the ordinary reproduction exits 139.

The installed Kit file-stat cache stores and re-raises OSError objects. A CPU-only reproduction of that exact cached function proves that its tracebacks retain a synthetic caller object until the cache is cleared. This explains a source of extended object lifetimes; it does not prove that clearing that one cache fixes all shutdown defects. GDB after detaching the stat cache (`gdb-detach.log`) instead faults in the native `carb.events` bindings during Python object finalization. There are multiple native objects outliving their backing services in this slow-shutdown path.

| Diagnostic | Outcome |
| --- | --- |
| Original script under GDB | Native UI-window destructor fault during Python finalization |
| Garbage collection before close | Exit 139 |
| Disable file-stat cache through Kit setting | Exit 139 |
| Reset stat cache and collect | Cleared 5,988 entries / collected 71,016 objects; exit 139 |
| Detach stat import hook and collect | Exit 139; GDB identifies a later native event-subscription destructor |
| Scope test objects and clear simulation context, retain slow shutdown | Exit 139 |
| Default Kit standalone shutdown with explicit scene cleanup | Two complete runs exit 0 |
| Deliberate test failure under final shutdown policy | Exit 1 and no passing report |

The first heap-inspection probe dereferenced an expired weak proxy and raised ReferenceError; its stopped container exit 137 is a probe error, not a new compatibility result. A corrected bounded inspection captured 1,187 exceptions before being intentionally stopped. Large probe data and GPU dumps are preserved outside Git with hashes in `large-diagnostics-manifest.json`. Inspected proprietary Kit source copies remain under ignored `.runtime/`, with source hashes in `inspected-source-manifest.json`. No installed source was patched.

## Final repair and its scope

The project had explicitly overridden Isaac's default with `fast_shutdown=False` to write a completion report after `app.close()`. That exposed native destructors running after Kit services were unloaded. The corrected launcher uses [NVIDIA's default standalone shutdown](https://docs.isaacsim.omniverse.nvidia.com/6.0.0/py/source/extensions/isaacsim.simulation_app/docs/index.html), with `skip_cleanup=False` and `wait_for_replicator=True`.

`runtime_smoke.py` scopes simulation objects inside `run_checks()`, calls `SimulationContext.clear_instance()`, and asserts that the singleton and USD stage are gone while Kit is still alive. It writes a **pending-shutdown** result, then calls `app.close(exit_code=...)`. Kit performs its supported standalone cleanup/termination path. The parent requires the saved checks, explicit scene cleanup, Kit's Replicator/shutdown log milestones and actual process exit 0 before declaring success. There is no application-level `os._exit`, skipped-cleanup flag or altered physics threshold. The experimental cache monkeypatches are **not** in the production launcher.

The diagnostic negative script differs from the final script only by an intentional RuntimeError after simulation checks. `negative-exit.log` and `negative-exit.exit-code.txt` verify exit 1 and no result.json. Thus Kit shutdown cannot turn a failed test into an accepted run.

This validates separate standalone simulation worker processes, as specified by the plan. It does **not** fix the upstream slow/in-process teardown defect or prove repeated Kit initialization within one Python interpreter. That defect and all failed trials remain preserved. No alternate architecture was selected.

## Evidence map

- `reproduction-command.json`, `reproduce.gdb`, `gdb-reproduction.log`: native reproduction in an isolated container with GDB installed. Debugger package installation is recorded and never entered the locked image.
- Per-trial command JSON, script snapshot, stdout/stderr, Kit log, process exit file and generated measurements/scene: exact experiments above.
- `cache-retention-reproduction.json`: CPU-only cache/traceback lifetime test.
- `negative-exit.*`, `runtime_smoke.negative.py`: real failure-exit regression check.
- `../20261026T164452-runtime/`: accepted final script/launcher snapshots, image metadata, both runs' commands, exit codes, outcomes, trajectories, configuration, scenes, rendered images and artifact hashes.
