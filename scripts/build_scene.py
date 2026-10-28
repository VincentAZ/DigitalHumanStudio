#!/usr/bin/env python3
"""Author the small industrial work-cell scene as USD (text) plus a JSON footprint for the control center.

The scene is described once below as boxes and cylinders in scene-relative metres (origin = the
character's spawn, Z up). The USD gets static PhysX colliders on everything but floor markings; the
JSON lists the same footprints so the room map can draw them and the launcher knows the spawn and
room size. Deterministic: re-running produces identical files. No external assets.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "config" / "scenes"

# name, kind, center (x, y, z of the box centre), size (sx, sy, sz), yaw degrees, colour, collision
BOXES = [
    ("wall_north", "wall", (0.0, 5.5, 1.5), (11.2, 0.2, 3.0), 0, (0.82, 0.82, 0.80), True),
    ("wall_south", "wall", (0.0, -5.5, 1.5), (11.2, 0.2, 3.0), 0, (0.82, 0.82, 0.80), True),
    ("wall_east", "wall", (5.5, 0.0, 1.5), (0.2, 11.2, 3.0), 0, (0.82, 0.82, 0.80), True),
    ("wall_west", "wall", (-5.5, 0.0, 1.5), (0.2, 11.2, 3.0), 0, (0.82, 0.82, 0.80), True),
    ("machine_body", "machine", (3.2, 2.6, 0.9), (2.0, 1.5, 1.8), 0, (0.35, 0.42, 0.50), True),
    ("machine_panel", "machine", (2.0, 2.6, 0.75), (0.35, 0.6, 1.5), 0, (0.20, 0.22, 0.25), True),
    ("conveyor_bed", "conveyor", (-2.5, 3.2, 0.85), (4.0, 0.8, 0.12), 0, (0.25, 0.55, 0.35), True),
    ("conveyor_leg_a", "conveyor", (-4.3, 3.2, 0.4), (0.12, 0.6, 0.8), 0, (0.30, 0.30, 0.32), True),
    ("conveyor_leg_b", "conveyor", (-2.5, 3.2, 0.4), (0.12, 0.6, 0.8), 0, (0.30, 0.30, 0.32), True),
    ("conveyor_leg_c", "conveyor", (-0.7, 3.2, 0.4), (0.12, 0.6, 0.8), 0, (0.30, 0.30, 0.32), True),
    ("rack", "rack", (-3.6, -3.2, 1.25), (2.4, 1.0, 2.5), 0, (0.80, 0.45, 0.15), True),
    ("pallet_a", "pallet", (2.4, -3.6, 0.075), (1.2, 0.8, 0.15), 0, (0.60, 0.45, 0.25), True),
    ("pallet_a_load", "pallet", (2.4, -3.6, 0.55), (1.0, 0.7, 0.8), 0, (0.72, 0.60, 0.40), True),
    ("pallet_b", "pallet", (3.9, -3.6, 0.075), (1.2, 0.8, 0.15), 0, (0.60, 0.45, 0.25), True),
    ("pallet_b_load", "pallet", (3.9, -3.6, 0.35), (1.0, 0.7, 0.4), 0, (0.72, 0.60, 0.40), True),
    ("lane_outer_n", "marking", (0.0, 4.5, 0.004), (9.0, 0.08, 0.008), 0, (0.95, 0.80, 0.10), False),
    ("lane_outer_s", "marking", (0.0, -4.5, 0.004), (9.0, 0.08, 0.008), 0, (0.95, 0.80, 0.10), False),
    ("lane_outer_e", "marking", (4.5, 0.0, 0.004), (0.08, 9.0, 0.008), 0, (0.95, 0.80, 0.10), False),
    ("lane_outer_w", "marking", (-4.5, 0.0, 0.004), (0.08, 9.0, 0.008), 0, (0.95, 0.80, 0.10), False),
    ("machine_zone", "marking", (2.6, 1.2, 0.004), (3.6, 0.08, 0.008), 0, (0.95, 0.30, 0.15), False),
    ("spawn_mark", "marking", (0.0, 0.0, 0.004), (0.6, 0.6, 0.008), 45, (0.20, 0.50, 0.90), False),
]
POSTS = [  # name, centre (x, y), radius, height, colour
    ("post_a", (1.0, 1.4), 0.06, 1.0, (0.95, 0.80, 0.10)),
    ("post_b", (4.4, 1.4), 0.06, 1.0, (0.95, 0.80, 0.10)),
    ("post_c", (1.0, -1.6), 0.06, 1.0, (0.95, 0.80, 0.10)),
    ("post_d", (4.4, -1.6), 0.06, 1.0, (0.95, 0.80, 0.10)),
]
PROPS = [  # graspable props: name, shape, size (cylinder: radius, height; box: sx, sy, sz), centre, colour, approach point, hand, description
    ("cup", "cylinder", (0.04, 0.10), (-2.0, 3.0, 0.96), (0.92, 0.93, 0.90), (-2.0, 2.25), "RightHand",
     "A paper cup standing on the conveyor bed"),
    ("carton", "box", (0.30, 0.24, 0.22), (3.9, -3.4, 0.66), (0.80, 0.66, 0.42), (3.9, -2.55), "RightHand",
     "A small carton on top of the load on pallet B"),
]
ROUTE = [  # the comparison route: scene-relative destinations with a hold between legs
    (3.0, 0.3), (-2.3, 1.8), (-3.2, -1.3), (0.5, -2.2), (0.0, 0.0),
]


def usd_text() -> str:
    lines = ['#usda 1.0', '(', '    defaultPrim = "Workcell"', '    metersPerUnit = 1', '    upAxis = "Z"', ')', '',
             'def Xform "Workcell"', '{']
    for name, kind, (x, y, z), (sx, sy, sz), yaw, colour, collide in BOXES:
        api = '    (\n        prepend apiSchemas = ["PhysicsCollisionAPI"]\n    )\n' if collide else ''
        lines += [f'    def Cube "{name}"', api.rstrip("\n") if api else None, '    {',
                  '        double size = 1',
                  f'        color3f[] primvars:displayColor = [({colour[0]}, {colour[1]}, {colour[2]})]',
                  f'        double3 xformOp:translate = ({x}, {y}, {z})',
                  f'        float3 xformOp:rotateXYZ = (0, 0, {yaw})',
                  f'        float3 xformOp:scale = ({sx}, {sy}, {sz})',
                  '        uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:rotateXYZ", "xformOp:scale"]',
                  f'        custom string studio:kind = "{kind}"',
                  '    }', '']
    for name, (x, y), radius, height, colour in POSTS:
        lines += [f'    def Cylinder "{name}"', '    (', '        prepend apiSchemas = ["PhysicsCollisionAPI"]', '    )', '    {',
                  f'        double radius = {radius}', f'        double height = {height}', '        uniform token axis = "Z"',
                  f'        color3f[] primvars:displayColor = [({colour[0]}, {colour[1]}, {colour[2]})]',
                  f'        double3 xformOp:translate = ({x}, {y}, {height / 2})',
                  '        uniform token[] xformOpOrder = ["xformOp:translate"]',
                  '        custom string studio:kind = "post"', '    }', '']
    # Props are visual-only prims (no collision) grouped under Props/<name>, each with translate + orient
    # ops the live worker drives when a prop is attached to a hand.
    lines += ['    def Xform "Props"', '    {']
    for name, shape, size, (x, y, z), colour, _approach, _hand, _desc in PROPS:
        lines += [f'        def Xform "{name}"', '        {',
                  f'            double3 xformOp:translate = ({x}, {y}, {z})',
                  '            quatd xformOp:orient = (1, 0, 0, 0)',
                  '            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:orient"]',
                  '            custom string studio:kind = "prop"']
        if shape == "cylinder":
            radius, height = size
            lines += ['            def Cylinder "shape"', '            {', f'                double radius = {radius}', f'                double height = {height}',
                      '                uniform token axis = "Z"', f'                color3f[] primvars:displayColor = [({colour[0]}, {colour[1]}, {colour[2]})]', '            }']
        else:
            sx, sy, sz = size
            lines += ['            def Cube "shape"', '            {', '                double size = 1',
                      f'                color3f[] primvars:displayColor = [({colour[0]}, {colour[1]}, {colour[2]})]',
                      f'                float3 xformOp:scale = ({sx}, {sy}, {sz})', '                uniform token[] xformOpOrder = ["xformOp:scale"]', '            }']
        lines += ['        }', '']
    lines += ['    }', '}', '']
    return "\n".join(line for line in lines if line is not None)


def footprint() -> dict:
    items = [{"name": n, "kind": k, "center": [c[0], c[1]], "size": [s[0], s[1]], "height": s[2], "top": round(c[2] + s[2] / 2, 4), "yaw_deg": yaw,
              "collision": col, "colour": list(colour)} for n, k, c, s, yaw, colour, col in BOXES]
    items += [{"name": n, "kind": "post", "center": [c[0], c[1]], "size": [2 * r, 2 * r], "height": h, "top": h, "yaw_deg": 0,
               "collision": True, "colour": list(colour)} for n, c, r, h, colour in POSTS]
    objects = [{"name": n, "kind": "prop", "shape": shape, "size": list(size), "center": list(c), "colour": list(colour), "approach": list(approach),
                "hand": hand, "attach_offset": [0.0, 0.0, 0.0], "graspable": True, "description": desc}
               for n, shape, size, c, colour, approach, hand, desc in PROPS]
    return {"name": "workcell", "description": "Small industrial work cell: walls, a machine with its guarded zone, a conveyor, a rack, two loaded pallets, lane markings, a cup on the conveyor and a carton on a pallet.",
            "spawn_xy": [100.0, 100.0], "room_half_size": 5.2, "usd": "workcell.usda", "items": items, "objects": objects,
            "route": [{"x": x, "y": y} for x, y in ROUTE]}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "workcell.usda").write_text(usd_text())
    (OUT / "workcell.json").write_text(json.dumps(footprint(), indent=1) + "\n")
    route = []
    t = 1.0
    route.append({"at": 0.5, "cmd": "record", "action": "start", "name": "route"})
    for x, y in ROUTE:
        route.append({"at": round(t, 2), "cmd": "destination", "x": x, "y": y, "frame": "spawn"})
        t += 9.0
    route.append({"at": round(t, 2), "cmd": "record", "action": "stop"})
    route.append({"at": round(t + 0.5, 2), "cmd": "quit"})
    (ROOT / "config" / "milestone3-compare-route.jsonl").write_text("".join(json.dumps(r) + "\n" for r in route))
    print(f"wrote {OUT / 'workcell.usda'} ({len(BOXES)} boxes, {len(POSTS)} posts, {len(PROPS)} props), {OUT / 'workcell.json'}, route of {len(ROUTE)} legs ending at t={t + 0.5:.1f}s")


if __name__ == "__main__":
    main()
