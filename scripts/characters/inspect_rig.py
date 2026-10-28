#!/usr/bin/env python3
"""Inspect rigged character files and report skeleton facts for the SOMA-23 mapping work.

Supported inputs: glTF/GLB (including VRM 0.x/1.0), USDA (text USD with UsdSkel), binary FBX.
Writes one JSON report per input. Nothing here needs a GPU, Blender or Isaac.

Usage:
    inspect_rig.py --out REPORT_DIR FILE [FILE ...]

The project root is derived from this file's location, not the caller's working directory.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOMA23 = [
    "Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
    "RightLeg", "RightShin", "RightFoot", "RightToeBase",
    "LeftLeg", "LeftShin", "LeftFoot", "LeftToeBase",
]


# ----------------------------------------------------------------------------- math helpers
def quat_to_mat(q):
    x, y, z, w = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def trs_to_mat(t, r, s):
    m = np.eye(4)
    m[:3, :3] = quat_to_mat(r) @ np.diag(s)
    m[:3, 3] = t
    return m


def euler_xyz_deg_to_mat(rx, ry, rz):
    cx, sx = math.cos(math.radians(rx)), math.sin(math.radians(rx))
    cy, sy = math.cos(math.radians(ry)), math.sin(math.radians(ry))
    cz, sz = math.cos(math.radians(rz)), math.sin(math.radians(rz))
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return mz @ my @ mx  # FBX eEulerXYZ: R = Rz * Ry * Rx


def rounded(v, nd=4):
    return [round(float(x), nd) for x in v]


# ----------------------------------------------------------------------------- glTF
def inspect_gltf(path: Path) -> dict:
    from pygltflib import GLTF2

    is_binary = path.suffix.lower() in (".glb", ".vrm")
    g = GLTF2().load_binary(str(path)) if is_binary else GLTF2().load(str(path))
    blob = g.binary_blob() if is_binary else None

    def read_accessor(idx):
        acc = g.accessors[idx]
        bv = g.bufferViews[acc.bufferView]
        buf = g.buffers[bv.buffer]
        if blob is not None and buf.uri is None:
            data = blob
        else:
            data = (path.parent / buf.uri).read_bytes()
        ctype = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}[acc.componentType]
        ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc.type]
        itemsize = struct.calcsize(ctype) * ncomp
        start = (bv.byteOffset or 0) + (acc.byteOffset or 0)
        stride = bv.byteStride or itemsize
        out = np.empty((acc.count, ncomp), dtype=np.float64)
        for i in range(acc.count):
            o = start + i * stride
            out[i] = struct.unpack_from("<" + ctype * ncomp, data, o)
        return out

    nodes = g.nodes
    parent = {}
    for i, n in enumerate(nodes):
        for c in (n.children or []):
            parent[c] = i

    def local(n):
        if n.matrix:
            return np.array(n.matrix, dtype=np.float64).reshape(4, 4).T
        t = n.translation or [0, 0, 0]
        r = n.rotation or [0, 0, 0, 1]
        s = n.scale or [1, 1, 1]
        return trs_to_mat(t, r, s)

    world = {}

    def world_of(i):
        if i in world:
            return world[i]
        m = local(nodes[i])
        if i in parent:
            m = world_of(parent[i]) @ m
        world[i] = m
        return m

    vertex_count = 0
    has_weights = False
    textured = False
    for mesh in g.meshes:
        for p in mesh.primitives:
            if p.attributes.POSITION is not None:
                vertex_count += g.accessors[p.attributes.POSITION].count
            if p.attributes.JOINTS_0 is not None and p.attributes.WEIGHTS_0 is not None:
                has_weights = True
    textured = bool(g.images)

    skins = []
    for si, skin in enumerate(g.skins or []):
        ibm = read_accessor(skin.inverseBindMatrices) if skin.inverseBindMatrices is not None else None
        joints = []
        for k, ni in enumerate(skin.joints):
            n = nodes[ni]
            wm = world_of(ni)
            entry = {
                "index": ni,
                "name": n.name or f"node{ni}",
                "parent": (nodes[parent[ni]].name if ni in parent else None),
                "parent_in_skin": (parent[ni] in skin.joints) if ni in parent else False,
                "rest_world_pos": rounded(wm[:3, 3]),
            }
            if ibm is not None:
                bind = np.linalg.inv(ibm[k].reshape(4, 4).T)  # column-major in glTF
                entry["bind_world_pos"] = rounded(bind[:3, 3])
            joints.append(entry)
        skins.append({"skin_index": si, "name": skin.name, "joint_count": len(joints), "joints": joints})

    if not skins:
        # No skin: report the node hierarchy instead (rigid-part "rigs" such as Kenney Blocky Characters).
        joints = []
        for ni, n in enumerate(nodes):
            wm = world_of(ni)
            joints.append({
                "index": ni,
                "name": n.name or f"node{ni}",
                "parent": (nodes[parent[ni]].name if ni in parent else None),
                "parent_in_skin": ni in parent,
                "rest_world_pos": rounded(wm[:3, 3]),
                "has_mesh": n.mesh is not None,
            })
        skins.append({"skin_index": None, "name": "node hierarchy (no skin)", "joint_count": len(joints), "joints": joints})

    ext = g.extensions or {}
    vrm = None
    if "VRM" in ext:
        hb = ext["VRM"].get("humanoid", {}).get("humanBones", [])
        vrm = {"version": "0.x", "humanBones": {b["bone"]: nodes[b["node"]].name for b in hb}}
    elif "VRMC_vrm" in ext:
        hb = ext["VRMC_vrm"].get("humanoid", {}).get("humanBones", {})
        vrm = {"version": "1.0", "humanBones": {k: nodes[v["node"]].name for k, v in hb.items()}}

    anims = [a.name for a in (g.animations or [])]
    return {
        "format": "VRM" if vrm else ("GLB" if path.suffix.lower() == ".glb" else "glTF"),
        "generator": (g.asset.generator if g.asset else None),
        "up_axis": "Y (glTF specification)",
        "units": "metres (glTF specification)",
        "mesh_vertex_count": int(vertex_count),
        "mesh_count": len(g.meshes),
        "has_skin_weights": bool(has_weights),
        "has_textures": textured,
        "image_count": len(g.images or []),
        "animation_count": len(anims),
        "animations": anims[:80],
        "skins": skins,
        "vrm": vrm,
    }


# ----------------------------------------------------------------------------- USDA
def _parse_matrix_list(text: str):
    nums = re.findall(r"-?\d+(?:\.\d+)?(?:e[-+]?\d+)?", text)
    arr = np.array([float(x) for x in nums], dtype=np.float64)
    return arr.reshape(-1, 4, 4)


def inspect_usda(path: Path) -> dict:
    txt = path.read_text(errors="replace")
    mpu = re.search(r"metersPerUnit\s*=\s*([\d.]+)", txt)
    up = re.search(r'upAxis\s*=\s*"(\w)"', txt)
    skel_m = re.search(r'def Skeleton "(\w+)"', txt)
    joints_m = re.search(r"uniform token\[\] joints = \[(.*?)\]", txt, re.S)
    bind_m = re.search(r"uniform matrix4d\[\] bindTransforms = \[(.*?)\]\n", txt, re.S)
    rest_m = re.search(r"uniform matrix4d\[\] restTransforms = \[(.*?)\]\n", txt, re.S)
    joint_paths = re.findall(r'"([^"]+)"', joints_m.group(1)) if joints_m else []
    bind = _parse_matrix_list(bind_m.group(1)) if bind_m else None
    rest = _parse_matrix_list(rest_m.group(1)) if rest_m else None
    scale = float(mpu.group(1)) if mpu else 1.0

    # USD matrices are row-vector convention: p' = p @ M, translation in the last row.
    joints = []
    world = {}
    for i, jp in enumerate(joint_paths):
        parent_path = jp.rsplit("/", 1)[0] if "/" in jp else None
        pm = world.get(parent_path, np.eye(4))
        wm = (rest[i] @ pm) if rest is not None else np.eye(4)
        world[jp] = wm
        entry = {
            "index": i,
            "name": jp.rsplit("/", 1)[-1],
            "path": jp,
            "parent": parent_path.rsplit("/", 1)[-1] if parent_path else None,
            "rest_world_pos_m": rounded(wm[3, :3] * scale),
        }
        if bind is not None:
            entry["bind_world_pos_m"] = rounded(bind[i][3, :3] * scale)
        joints.append(entry)

    meshes = []
    for m in re.finditer(r'def Mesh "(\w+)"(.*?)(?=\n\s*def |\Z)', txt, re.S):
        body = m.group(2)
        pts = re.search(r"point3f\[\] points = \[(.*?)\]\n", body, re.S)
        n = len(re.findall(r"\(", pts.group(1))) if pts else 0
        meshes.append({
            "name": m.group(1),
            "vertex_count": n,
            "has_skin_weights": "primvars:skel:jointWeights" in body,
        })
    return {
        "format": "USDA (UsdSkel)",
        "up_axis": up.group(1) if up else None,
        "units": f"metersPerUnit={scale}",
        "skeleton": skel_m.group(1) if skel_m else None,
        "mesh_vertex_count": int(sum(x["vertex_count"] for x in meshes)),
        "meshes": meshes,
        "has_skin_weights": any(x["has_skin_weights"] for x in meshes),
        "has_textures": bool(re.search(r"\.(png|jpg|jpeg|exr|tif)", txt)),
        "skins": [{"skin_index": 0, "name": skel_m.group(1) if skel_m else None, "joint_count": len(joints), "joints": joints}],
    }


# ----------------------------------------------------------------------------- FBX (binary)
def _read_fbx(path: Path):
    data = path.read_bytes()
    if not data.startswith(b"Kaydara FBX Binary"):
        raise ValueError("not a binary FBX")
    version = struct.unpack_from("<I", data, 23)[0]
    wide = version >= 7500
    pos = 27

    def read_prop(p):
        t = data[p:p + 1]
        p += 1
        if t == b"Y":
            return struct.unpack_from("<h", data, p)[0], p + 2
        if t == b"C":
            return bool(data[p]), p + 1
        if t == b"I":
            return struct.unpack_from("<i", data, p)[0], p + 4
        if t == b"F":
            return struct.unpack_from("<f", data, p)[0], p + 4
        if t == b"D":
            return struct.unpack_from("<d", data, p)[0], p + 8
        if t == b"L":
            return struct.unpack_from("<q", data, p)[0], p + 8
        if t in (b"S", b"R"):
            n = struct.unpack_from("<I", data, p)[0]
            raw = data[p + 4:p + 4 + n]
            return (raw.decode("utf-8", "replace") if t == b"S" else raw), p + 4 + n
        if t in (b"f", b"d", b"l", b"i", b"b"):
            n, enc, clen = struct.unpack_from("<III", data, p)
            p += 12
            raw = data[p:p + clen]
            if enc == 1:
                raw = zlib.decompress(raw)
            fmt = {b"f": "f", b"d": "d", b"l": "q", b"i": "i", b"b": "?"}[t]
            return np.frombuffer(raw, dtype=np.dtype("<" + fmt), count=n), p + clen
        raise ValueError(f"unknown property type {t!r} at {p}")

    def read_node(p):
        if wide:
            end, nprops, plen = struct.unpack_from("<QQQ", data, p)
            p += 24
        else:
            end, nprops, plen = struct.unpack_from("<III", data, p)
            p += 12
        nlen = data[p]
        p += 1
        if end == 0:
            return None, p
        name = data[p:p + nlen].decode("ascii", "replace")
        p += nlen
        props = []
        for _ in range(nprops):
            v, p = read_prop(p)
            props.append(v)
        children = []
        while p < end:
            child, p = read_node(p)
            if child is None:
                break
            children.append(child)
        return (name, props, children), end

    root = []
    while pos < len(data):
        node, pos = read_node(pos)
        if node is None:
            break
        root.append(node)
    return version, root


def inspect_fbx(path: Path) -> dict:
    version, root = _read_fbx(path)
    top = {n[0]: n for n in root}

    def find(node, name):
        return [c for c in node[2] if c[0] == name]

    unit_scale, up_axis = None, None
    gs = top.get("GlobalSettings")
    if gs:
        for p70 in find(gs, "Properties70"):
            for pr in p70[2]:
                if pr[1][0] == "UnitScaleFactor":
                    unit_scale = pr[1][4]
                if pr[1][0] == "UpAxis":
                    up_axis = pr[1][4]

    objects = top["Objects"]
    models, geoms, has_skin = {}, {}, False
    for o in objects[2]:
        if o[0] == "Model":
            oid, name, kind = o[1][0], o[1][1].split("\x00")[0], o[1][2]
            props = {"t": np.zeros(3), "r": np.zeros(3), "pre": np.zeros(3), "s": np.ones(3)}
            for p70 in find(o, "Properties70"):
                for pr in p70[2]:
                    key = pr[1][0]
                    if key == "Lcl Translation":
                        props["t"] = np.array(pr[1][4:7], dtype=float)
                    elif key == "Lcl Rotation":
                        props["r"] = np.array(pr[1][4:7], dtype=float)
                    elif key == "PreRotation":
                        props["pre"] = np.array(pr[1][4:7], dtype=float)
                    elif key == "Lcl Scaling":
                        props["s"] = np.array(pr[1][4:7], dtype=float)
            models[oid] = {"name": name, "kind": kind, **props}
        elif o[0] == "Geometry":
            v = find(o, "Vertices")
            geoms[o[1][0]] = int(len(v[0][1][0]) // 3) if v else 0
        elif o[0] == "Deformer" and o[1][2] in ("Skin", "Cluster"):
            has_skin = True

    parent = {}
    for c in top["Connections"][2]:
        if c[1][0] == "OO" and c[1][1] in models and c[1][2] in models:
            parent[c[1][1]] = c[1][2]

    world = {}

    def world_of(oid):
        if oid in world:
            return world[oid]
        m = models[oid]
        loc = np.eye(4)
        loc[:3, :3] = euler_xyz_deg_to_mat(*m["pre"]) @ euler_xyz_deg_to_mat(*m["r"]) @ np.diag(m["s"])
        loc[:3, 3] = m["t"]
        wm = (world_of(parent[oid]) @ loc) if oid in parent else loc
        world[oid] = wm
        return wm

    scale = (unit_scale or 1.0) / 100.0  # FBX UnitScaleFactor is in centimetres
    joints = []
    for oid, m in models.items():
        if m["kind"] not in ("LimbNode", "Root", "Null"):
            continue
        wm = world_of(oid)
        joints.append({
            "index": len(joints),
            "name": m["name"],
            "kind": m["kind"],
            "parent": models[parent[oid]]["name"] if oid in parent else None,
            "rest_world_pos_m": rounded(wm[:3, 3] * scale),
        })
    textures = any(o[0] == "Texture" for o in objects[2])
    return {
        "format": f"FBX binary {version}",
        "up_axis": {0: "X", 1: "Y", 2: "Z"}.get(up_axis, str(up_axis)),
        "units": f"UnitScaleFactor={unit_scale} (cm-based; positions converted to metres)",
        "mesh_vertex_count": int(sum(geoms.values())),
        "mesh_count": len(geoms),
        "has_skin_weights": has_skin,
        "has_textures": textures,
        "note": "rest-pose positions use Lcl Translation/Rotation/PreRotation with eEulerXYZ; rotation order and pivots are not evaluated",
        "skins": [{"skin_index": 0, "name": "FBX LimbNode tree", "joint_count": len(joints), "joints": joints}],
    }


# ----------------------------------------------------------------------------- main
def inspect(path: Path) -> dict:
    suf = path.suffix.lower()
    if suf in (".glb", ".gltf", ".vrm"):
        rep = inspect_gltf(path)
    elif suf in (".usda",):
        rep = inspect_usda(path)
    elif suf == ".fbx":
        rep = inspect_fbx(path)
    else:
        raise SystemExit(f"unsupported file type: {path}")
    rep["file"] = str(path.relative_to(PROJECT_ROOT)) if PROJECT_ROOT in path.parents else str(path)
    rep["bytes"] = path.stat().st_size
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="directory for JSON reports")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for f in args.files:
        p = Path(f).resolve()
        rep = inspect(p)
        dest = out / (p.name.replace(" ", "_").replace(".", "_") + ".json")
        dest.write_text(json.dumps(rep, indent=1))
        names = [j["name"] for j in rep["skins"][0]["joints"]] if rep["skins"] else []
        print(f"{p.name}: {rep['format']}, verts={rep['mesh_vertex_count']}, skin={rep['has_skin_weights']}, "
              f"joints={len(names)}, textures={rep['has_textures']} -> {dest}")
        print("   joints:", ", ".join(names[:70]) + (" ..." if len(names) > 70 else ""))


if __name__ == "__main__":
    main()
