"""Run within Mixar; verify a saved primitive scene in separate processes."""
import json
from pathlib import Path
import sys

import bpy

mode, output_dir = sys.argv[sys.argv.index("--") + 1:]
output = Path(output_dir)
project = output / "milestone0.blend"
scene = bpy.context.scene

if mode == "create":
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    cube = bpy.data.objects["Cube"]
    cube.name = "Milestone0Cube"
    cube.location = (0, 0, 1)
    scene["studio_milestone"] = 0
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(output / "mixar-preview.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(project))
    # This CPU render checks the saved authoring scene, not Isaac GPU rendering.
    bpy.ops.render.render(write_still=True)
    assert (output / "mixar-preview.png").stat().st_size > 1000
    report = {"status": "passed", "version": bpy.app.version_string,
              "project": str(project), "render_device": "CPU"}
elif mode in {"reopen", "desktop"}:
    assert Path(bpy.data.filepath).resolve() == project.resolve()
    assert scene["studio_milestone"] == 0
    cube = bpy.data.objects["Milestone0Cube"]
    assert tuple(cube.location) == (0.0, 0.0, 1.0)
    assert scene.unit_settings.system == "METRIC"
    report = {"status": "passed", "version": bpy.app.version_string,
              "project": str(project), "cube_location": list(cube.location)}
    if mode == "desktop":
        import gpu
        assert not bpy.app.background
        assert len(bpy.context.window_manager.windows) > 0
        report["gpu_backend"] = gpu.platform.backend_type_get()
        report["gpu_renderer"] = gpu.platform.renderer_get()
        bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=5)
else:
    raise ValueError(mode)

(output / f"{mode}.json").write_text(json.dumps(report, indent=2) + "\n")
print(f"STUDIO_MIXAR_{mode.upper()}_PASSED")
