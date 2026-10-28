#!/opt/IsaacLab/.venv/bin/python
"""Turn a downloaded rig (UsdSkel .usd/.usda or glTF/GLB) into the studio's character format.

Writes ``<out>/rig.npz`` (joints, bind transforms, skinned meshes with weights and uvs), the base
colour textures as PNG files and ``<out>/character.json`` (name, licence, source, joint map, counts).
The live worker loads that folder and drives the mesh from the physical body with its own linear
blend skinning, so nothing here depends on the renderer. Runs on the CPU inside the pinned image
(pxr and numpy are available there); launched by scripts/fetch_characters.py.
"""
import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--rig", type=Path, required=True, help="rig file (.usd, .usda, .usdc, .gltf, .glb, .vrm)")
parser.add_argument("--out", type=Path, required=True, help="character folder to write")
parser.add_argument("--meta", type=Path, required=True, help="JSON with name, licence, source, joint_map (SOMA body -> rig joint)")
parser.add_argument("--mesh", default="", help="UsdSkel only: name of the skinned mesh to use (default: the largest skinned mesh with at most --max-vertices points)")
parser.add_argument("--max-vertices", type=int, default=40000)
parser.add_argument("--joint-name-regex", default="", help="regex with a (?P<name>...) group that extracts the short joint name from a USD joint path")
parser.add_argument("--id", default="", help="character id written into character.json (default: the output folder name)")
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
meta = json.loads(args.meta.read_text())


def triangulate(counts, indices):
    """Fan-triangulate polygons; returns (F, 3) int32 and the polygon index of each triangle."""
    tris, src = [], []
    offset = 0
    for poly_index, count in enumerate(counts):
        face = indices[offset:offset + count]
        for k in range(1, count - 1):
            tris.append((face[0], face[k], face[k + 1]))
            src.append(poly_index)
        offset += count
    return np.asarray(tris, dtype=np.int32).reshape(-1, 3), np.asarray(src, dtype=np.int32)


# ---------------------------------------------------------------- UsdSkel
def load_usd(path: Path):
    import re
    from pxr import Usd, UsdGeom, UsdSkel, Gf
    stage = Usd.Stage.Open(str(path))
    meters = float(UsdGeom.GetStageMetersPerUnit(stage) or 1.0)
    up = str(UsdGeom.GetStageUpAxis(stage))
    skeletons = [p for p in stage.Traverse() if p.IsA(UsdSkel.Skeleton)]
    if not skeletons:
        raise SystemExit("no UsdSkel Skeleton prim in the file")
    skel = UsdSkel.Skeleton(skeletons[0])
    joint_paths = list(skel.GetJointsAttr().Get())
    bind = np.asarray([np.asarray(m) for m in skel.GetBindTransformsAttr().Get()], dtype=np.float64)   # (J, 4, 4) row-vector convention
    bind = np.transpose(bind, (0, 2, 1))                                                                  # column-vector convention
    topology = UsdSkel.Topology(joint_paths)
    parents = np.asarray(list(topology.GetParentIndices()), dtype=np.int32)
    regex = re.compile(args.joint_name_regex) if args.joint_name_regex else None
    names = []
    for jp in joint_paths:
        m = regex.match(jp) if regex else None
        names.append(m.group("name") if m else jp.split("/")[-1])
    cache = UsdSkel.Cache()
    binding_meshes = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        binding = UsdSkel.BindingAPI(prim)
        if not binding.GetJointIndicesPrimvar().HasValue():
            continue
        mesh = UsdGeom.Mesh(prim)
        points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
        binding_meshes.append((prim, mesh, points))
    if not binding_meshes:
        raise SystemExit("no skinned mesh (primvars:skel:jointIndices) in the file")
    chosen = None
    if args.mesh:
        chosen = [b for b in binding_meshes if b[0].GetName() == args.mesh]
        if not chosen:
            raise SystemExit(f"mesh {args.mesh} not found; skinned meshes: {[b[0].GetName() for b in binding_meshes]}")
    else:
        fitting = [b for b in binding_meshes if b[2].shape[0] <= args.max_vertices] or binding_meshes
        chosen = [max(fitting, key=lambda b: b[2].shape[0])]
    meshes = []
    xform_cache = UsdGeom.XformCache()
    skel_root_prim = skeletons[0].GetParent()
    for prim, mesh, points in chosen:
        binding = UsdSkel.BindingAPI(prim)
        ji = binding.GetJointIndicesPrimvar()
        jw = binding.GetJointWeightsPrimvar()
        influences = int(ji.GetElementSize())
        indices = np.asarray(ji.Get(), dtype=np.int32).reshape(-1, influences)
        weights = np.asarray(jw.Get(), dtype=np.float64).reshape(-1, influences)
        mesh_joints = binding.GetJointsAttr().Get()
        if mesh_joints:                                     # the mesh orders joints its own way: map back to the skeleton order
            remap = np.asarray([joint_paths.index(j) for j in mesh_joints], dtype=np.int32)
            indices = remap[indices]
        geom_bind = binding.GetGeomBindTransformAttr().Get()
        geom_bind = np.transpose(np.asarray(geom_bind, dtype=np.float64)) if geom_bind is not None else np.eye(4)
        counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(), dtype=np.int32)
        face_indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int32)
        tris, _ = triangulate(counts, face_indices)
        uv = None
        st = UsdGeom.PrimvarsAPI(prim).GetPrimvar("st")
        if st and st.HasValue():
            values = np.asarray(st.Get(), dtype=np.float32)
            interp = st.GetInterpolation()
            if interp == "vertex" and values.shape[0] == points.shape[0]:
                uv = values
            elif interp == "faceVarying":
                uv_indices = st.GetIndices()
                fv = values[np.asarray(uv_indices)] if uv_indices else values
                per_vertex = np.zeros((points.shape[0], 2), dtype=np.float32)
                per_vertex[face_indices] = fv[:face_indices.shape[0]]
                uv = per_vertex
        colour = [0.78, 0.72, 0.66]
        dc = mesh.GetDisplayColorAttr().Get()
        if dc:
            colour = [float(v) for v in dc[0]]
        meshes.append({"name": prim.GetName(), "points": points, "faces": tris, "joints": indices, "weights": weights, "geom_bind": geom_bind,
                       "uv": uv, "texture": "", "colour": colour})
    return {"names": names, "parents": parents, "bind": bind, "meters": meters, "up": up, "meshes": meshes, "source_format": "UsdSkel"}


# ---------------------------------------------------------------- glTF / GLB
def load_gltf(path: Path):
    from PIL import Image
    import io
    raw = path.read_bytes()
    buffers = []
    if raw[:4] == b"glTF":
        _, _, length = struct.unpack("<III", raw[:12])
        offset = 12
        gltf = None
        while offset < length:
            chunk_len, chunk_type = struct.unpack("<II", raw[offset:offset + 8])
            chunk = raw[offset + 8:offset + 8 + chunk_len]
            if chunk_type == 0x4E4F534A:
                gltf = json.loads(chunk.decode("utf-8"))
            elif chunk_type == 0x004E4942:
                buffers.append(chunk)
            offset += 8 + chunk_len
    else:
        gltf = json.loads(raw.decode("utf-8"))
        for buf in gltf.get("buffers", []):
            uri = buf.get("uri", "")
            if uri.startswith("data:"):
                import base64
                buffers.append(base64.b64decode(uri.split(",", 1)[1]))
            else:
                buffers.append((path.parent / uri).read_bytes())
    ctypes = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
    sizes = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}

    def accessor(index):
        acc = gltf["accessors"][index]
        view = gltf["bufferViews"][acc["bufferView"]]
        data = buffers[view["buffer"]]
        dtype = np.dtype(ctypes[acc["componentType"]])
        width = sizes[acc["type"]]
        start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        stride = view.get("byteStride", 0)
        count = acc["count"]
        if stride and stride != dtype.itemsize * width:
            rows = [np.frombuffer(data, dtype=dtype, count=width, offset=start + i * stride) for i in range(count)]
            arr = np.stack(rows)
        else:
            arr = np.frombuffer(data, dtype=dtype, count=count * width, offset=start).reshape(count, width)
        if acc.get("normalized") and dtype.kind == "u":
            arr = arr.astype(np.float64) / np.iinfo(dtype).max
        return arr.copy()

    nodes = gltf["nodes"]
    parents_of = {}
    for i, node in enumerate(nodes):
        for child in node.get("children", []):
            parents_of[child] = i

    def local_matrix(node):
        if "matrix" in node:
            return np.asarray(node["matrix"], dtype=np.float64).reshape(4, 4).T
        t = np.asarray(node.get("translation", [0, 0, 0]), dtype=np.float64)
        q = np.asarray(node.get("rotation", [0, 0, 0, 1]), dtype=np.float64)
        s = np.asarray(node.get("scale", [1, 1, 1]), dtype=np.float64)
        x, y, z, w = q
        rot = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        m = np.eye(4)
        m[:3, :3] = rot @ np.diag(s)
        m[:3, 3] = t
        return m

    world_cache = {}

    def world_matrix(i):
        if i in world_cache:
            return world_cache[i]
        m = local_matrix(nodes[i])
        if i in parents_of:
            m = world_matrix(parents_of[i]) @ m
        world_cache[i] = m
        return m

    skins = gltf.get("skins", [])
    if not skins:
        raise SystemExit("no skin in the glTF file")
    skin = skins[0]
    joint_nodes = skin["joints"]
    names = [nodes[j].get("name", f"joint{j}") for j in joint_nodes]
    joint_index = {j: k for k, j in enumerate(joint_nodes)}
    parents = np.asarray([joint_index.get(parents_of.get(j, -1), -1) for j in joint_nodes], dtype=np.int32)
    inverse_bind = np.asarray([m.reshape(4, 4).T for m in accessor(skin["inverseBindMatrices"])], dtype=np.float64)
    bind = np.asarray([world_matrix(j) for j in joint_nodes], dtype=np.float64)
    textures_written = {}

    def texture_for(material_index):
        if material_index is None:
            return "", [0.78, 0.72, 0.66]
        material = gltf["materials"][material_index]
        pbr = material.get("pbrMetallicRoughness", {})
        colour = list(pbr.get("baseColorFactor", [1, 1, 1, 1])[:3])
        tex = pbr.get("baseColorTexture")
        if tex is None:
            return "", colour
        image_index = gltf["textures"][tex["index"]]["source"]
        if image_index in textures_written:
            return textures_written[image_index], colour
        image = gltf["images"][image_index]
        if "bufferView" in image:
            view = gltf["bufferViews"][image["bufferView"]]
            blob = buffers[view["buffer"]][view.get("byteOffset", 0):view.get("byteOffset", 0) + view["byteLength"]]
            pil = Image.open(io.BytesIO(blob))
        else:
            pil = Image.open(path.parent / image["uri"])
        name = f"texture_{image_index}.png"
        pil.convert("RGBA").save(args.out / name)
        textures_written[image_index] = name
        return name, colour

    meshes = []
    for node_index, node in enumerate(nodes):
        if "mesh" not in node or node.get("skin") is None:
            continue
        mesh = gltf["meshes"][node["mesh"]]
        for prim in mesh["primitives"]:
            attrs = prim["attributes"]
            if "JOINTS_0" not in attrs:
                continue
            points = accessor(attrs["POSITION"]).astype(np.float64)
            joints = accessor(attrs["JOINTS_0"]).astype(np.int32)
            weights = accessor(attrs["WEIGHTS_0"]).astype(np.float64)
            indices = accessor(prim["indices"]).reshape(-1).astype(np.int32) if "indices" in prim else np.arange(points.shape[0], dtype=np.int32)
            mode = prim.get("mode", 4)
            if mode != 4:
                print(f"skipping primitive with mode {mode}")
                continue
            uv = accessor(attrs["TEXCOORD_0"]).astype(np.float32) if "TEXCOORD_0" in attrs else None
            texture, colour = texture_for(prim.get("material"))
            meshes.append({"name": f"{node.get('name', 'mesh')}_{len(meshes)}", "points": points, "faces": indices.reshape(-1, 3),
                           "joints": joints, "weights": weights, "geom_bind": world_matrix(node_index), "uv": uv, "texture": texture, "colour": colour,
                           "uv_flip_v": True})
    if not meshes:
        raise SystemExit("no skinned primitives in the glTF file")
    return {"names": names, "parents": parents, "bind": bind, "inverse_bind": inverse_bind, "meters": 1.0, "up": "Y", "meshes": meshes, "source_format": "glTF"}


# ---------------------------------------------------------------- write
suffix = args.rig.suffix.lower()
rig = load_usd(args.rig) if suffix in (".usd", ".usda", ".usdc") else load_gltf(args.rig)
if "inverse_bind" not in rig:
    rig["inverse_bind"] = np.linalg.inv(rig["bind"])
joint_map = meta.get("joint_map", {})
names = rig["names"]
body_of_joint = np.full(len(names), -1, dtype=np.int32)
from_name = {}
for body, joint in joint_map.items():
    if joint and joint in names:
        from_name[joint] = body
SOMA_BODIES = ["Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head", "RightShoulder", "RightArm", "RightForeArm", "RightHand",
               "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand", "RightLeg", "RightShin", "RightFoot", "RightToeBase", "LeftLeg", "LeftShin",
               "LeftFoot", "LeftToeBase"]
for k, name in enumerate(names):
    if name in from_name:
        body_of_joint[k] = SOMA_BODIES.index(from_name[name])
mapped_direct = int((body_of_joint >= 0).sum())
# unmapped joints follow their nearest mapped ancestor (fingers follow the hand, eyes the head, ...)
for k in range(len(names)):
    if body_of_joint[k] >= 0:
        continue
    parent = int(rig["parents"][k])
    while parent >= 0 and body_of_joint[parent] < 0:
        parent = int(rig["parents"][parent])
    body_of_joint[k] = body_of_joint[parent] if parent >= 0 else 0
payload = {"joint_names": np.asarray(names), "joint_parents": rig["parents"], "bind": rig["bind"], "inverse_bind": rig["inverse_bind"],
           "body_of_joint": body_of_joint, "meters_per_unit": np.float64(rig["meters"]), "up_axis": np.asarray(rig["up"]), "mesh_count": np.int32(len(rig["meshes"]))}
total_vertices = 0
for i, m in enumerate(rig["meshes"]):
    total_vertices += m["points"].shape[0]
    payload[f"m{i}_name"] = np.asarray(m["name"])
    payload[f"m{i}_points"] = m["points"].astype(np.float32)
    payload[f"m{i}_faces"] = m["faces"].astype(np.int32)
    payload[f"m{i}_joints"] = m["joints"].astype(np.int32)
    payload[f"m{i}_weights"] = m["weights"].astype(np.float32)
    payload[f"m{i}_geom_bind"] = m["geom_bind"].astype(np.float64)
    payload[f"m{i}_uv"] = m["uv"].astype(np.float32) if m.get("uv") is not None else np.zeros((0, 2), dtype=np.float32)
    payload[f"m{i}_uv_flip_v"] = np.bool_(m.get("uv_flip_v", False))
    payload[f"m{i}_texture"] = np.asarray(m.get("texture", ""))
    payload[f"m{i}_colour"] = np.asarray(m.get("colour", [0.78, 0.72, 0.66]), dtype=np.float32)
np.savez_compressed(args.out / "rig.npz", **payload)
unmapped_bodies = [b for b in SOMA_BODIES if not joint_map.get(b)]
character = {"id": args.id or args.out.name, "name": meta.get("name", args.out.name), "description": meta.get("description", ""),
             "licence": meta.get("licence", {}), "source": meta.get("source", {}), "rig_file": str(args.rig.name), "rig_sha256": meta.get("rig_sha256", ""),
             "format": rig["source_format"], "joints": len(names), "vertices": int(total_vertices), "meshes": [m["name"] for m in rig["meshes"]],
             "textures": sorted({m["texture"] for m in rig["meshes"] if m.get("texture")}), "joint_map": joint_map,
             "mapped_bodies": 23 - len(unmapped_bodies), "unmapped_bodies": unmapped_bodies, "joints_mapped_directly": mapped_direct,
             "meters_per_unit": rig["meters"], "up_axis": rig["up"], "prepared_by": "scripts/prepare_character.py"}
(args.out / "character.json").write_text(json.dumps(character, indent=1) + "\n")
print(json.dumps({k: character[k] for k in ("id", "format", "joints", "vertices", "meshes", "textures", "mapped_bodies", "unmapped_bodies")}))
