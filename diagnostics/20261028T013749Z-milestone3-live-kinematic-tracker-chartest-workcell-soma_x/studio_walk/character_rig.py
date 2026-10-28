"""Skinned characters driven by the physical body.

A prepared character folder (scripts/fetch_characters.py) holds ``rig.npz``: joints with bind
transforms, and one or more meshes with skin weights. At start the rig's bind pose is aligned to the
SOMA-23 body's rest pose (every mapped rig joint is rotated so its bone points the way the matching
physics body's bone points; unmapped joints such as fingers ride on their nearest mapped ancestor),
so rigs in an A-pose or with other proportions still follow the body. Every control step the
character's 23 body transforms are read from the simulator and the mesh is skinned on the GPU with
linear blend skinning; the points (and smooth normals) are written into USD mesh prims that the
renderer shows instead of the capsule body. No renderer feature beyond plain meshes is needed.
"""
from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import torch

from studio_walk.skill_lib import BODY_NAMES, PARENTS

# SOMA body whose bone direction defines the orientation of each body (None: inherit the parent's alignment)
CHAIN_CHILD = {"Hips": "Spine1", "Spine1": "Spine2", "Spine2": "Chest", "Chest": "Neck1", "Neck1": "Neck2", "Neck2": "Head", "Head": None,
               "RightShoulder": "RightArm", "RightArm": "RightForeArm", "RightForeArm": "RightHand", "RightHand": None,
               "LeftShoulder": "LeftArm", "LeftArm": "LeftForeArm", "LeftForeArm": "LeftHand", "LeftHand": None,
               "RightLeg": "RightShin", "RightShin": "RightFoot", "RightFoot": "RightToeBase", "RightToeBase": None,
               "LeftLeg": "LeftShin", "LeftShin": "LeftFoot", "LeftFoot": "LeftToeBase", "LeftToeBase": None}


def soma_rest_positions(mjcf_path: Path) -> np.ndarray:
    """World positions of the 23 bodies in the MJCF zero pose (root at the origin, rotations identity)."""
    tree = ET.parse(mjcf_path)
    offsets, parents = {}, {}

    def walk(node, parent):
        for body in node.findall("body"):
            name = body.get("name")
            offsets[name] = np.asarray([float(v) for v in body.get("pos", "0 0 0").split()])
            parents[name] = parent
            walk(body, name)
    walk(tree.getroot().find("worldbody"), None)
    positions = np.zeros((len(BODY_NAMES), 3))
    for i, name in enumerate(BODY_NAMES):
        p, chain = name, np.zeros(3)
        while p is not None:
            chain = chain + offsets[p]
            p = parents[p]
        positions[i] = chain
    return positions


def rotation_between(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Smallest rotation matrix taking direction a to direction b."""
    a = a / (np.linalg.norm(a) + 1e-12)
    b = b / (np.linalg.norm(b) + 1e-12)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    s = np.linalg.norm(v)
    if s < 1e-9:
        if c > 0:
            return np.eye(3)
        axis = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(axis) < 1e-6:
            axis = np.cross(a, [0.0, 1.0, 0.0])
        axis /= np.linalg.norm(axis)
        K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        return np.eye(3) + 2 * K @ K
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / (s * s))


def quat_to_matrix(q: torch.Tensor) -> torch.Tensor:
    """(..., 4) xyzw quaternions to (..., 3, 3) rotation matrices."""
    x, y, z, w = q.unbind(-1)
    return torch.stack([
        torch.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
        torch.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
        torch.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


class SkinnedCharacter:
    def __init__(self, folder: Path, mjcf_path: Path, device):
        self.folder = Path(folder)
        self.meta = json.loads((self.folder / "character.json").read_text())
        rig = np.load(self.folder / "rig.npz", allow_pickle=False)
        self.device = device
        names = [str(n) for n in rig["joint_names"]]
        parents = rig["joint_parents"].astype(int)
        bind = rig["bind"].astype(np.float64)                    # (J, 4, 4) rig space, column vectors
        body_of_joint = rig["body_of_joint"].astype(int)
        meters = float(rig["meters_per_unit"])
        up = str(rig["up_axis"])
        # rig space -> world axes/units (no translation): scale, then Y-up to Z-up when needed
        M = np.eye(4)
        M[:3, :3] *= meters
        if up.upper() == "Y":
            M[:3, :3] = np.array([[1, 0, 0], [0, 0, -1], [0, 1, 0]], dtype=np.float64) @ M[:3, :3]
        self.M = M
        joint_world = np.einsum("ij,njk->nik", M, bind)          # (J, 4, 4): joints in world axes at the rig's bind pose
        q = joint_world[:, :3, 3]
        soma = soma_rest_positions(mjcf_path)                     # (23, 3) SOMA bodies, root at the origin
        # --- rest-pose alignment: rotate every joint so its bone follows the matching body's bone
        J = len(names)
        C = np.tile(np.eye(3), (J, 1, 1))
        joint_of_body = {}
        for j in range(J):
            b = body_of_joint[j]
            if BODY_NAMES[b] not in joint_of_body or names[j] == self.meta.get("joint_map", {}).get(BODY_NAMES[b]):
                joint_of_body.setdefault(BODY_NAMES[b], j)
        direct = {names[j]: j for j in range(J)}
        mapped = {body: direct[joint] for body, joint in self.meta.get("joint_map", {}).items() if joint and joint in direct}
        order = list(range(J))   # parents come before children in both UsdSkel and glTF skins as prepared here
        for j in order:
            b = body_of_joint[j]
            body = BODY_NAMES[b]
            parent = int(parents[j])
            C[j] = C[parent] if parent >= 0 else np.eye(3)
            if mapped.get(body) != j:
                continue                                        # unmapped joint: inherit the alignment of its ancestor
            child_body = CHAIN_CHILD.get(body)
            if child_body is None or child_body not in mapped:
                continue
            e = q[mapped[child_body]] - q[j]
            d = soma[BODY_NAMES.index(child_body)] - soma[b]
            if np.linalg.norm(e) < 1e-6 or np.linalg.norm(d) < 1e-6:
                continue
            C[j] = rotation_between(e, d)
        # aligned bind positions: the hips snap to the body's hips, children keep their (rotated) offsets
        p_aligned = np.zeros((J, 3))
        root_joint = mapped.get("Hips", 0)
        for j in order:
            parent = int(parents[j])
            if parent < 0:
                p_aligned[j] = soma[0] + (q[j] - q[root_joint])
            else:
                p_aligned[j] = p_aligned[parent] + C[parent] @ (q[j] - q[parent])
        # skinning matrices at bind, relative to the body each joint follows:  A_j = [C R | p'_j - p_b] . (M B_j)^-1
        A = np.zeros((J, 3, 4))
        for j in range(J):
            b = body_of_joint[j]
            world_rot = C[j] @ joint_world[j, :3, :3]
            Jp = np.eye(4)
            Jp[:3, :3] = world_rot
            Jp[:3, 3] = p_aligned[j] - soma[b]
            A[j] = (Jp @ np.linalg.inv(joint_world[j]))[:3]
        self.body_of_joint = torch.as_tensor(body_of_joint, device=device)
        self.meshes = []
        count = int(rig["mesh_count"])
        for i in range(count):
            points = rig[f"m{i}_points"].astype(np.float64)
            geom_bind = rig[f"m{i}_geom_bind"].astype(np.float64)
            joints = rig[f"m{i}_joints"].astype(np.int64)
            weights = rig[f"m{i}_weights"].astype(np.float64)
            weights = weights / np.clip(weights.sum(-1, keepdims=True), 1e-8, None)
            v0 = (geom_bind @ np.concatenate([points, np.ones((points.shape[0], 1))], -1).T).T    # rig space, after the geom bind
            v0h = v0                                                                             # (N, 4)
            # u[n, k] = A_{joint(n,k)} . v0[n]   (in world units, relative to the followed body's rest position)
            A_sel = A[joints]                                                                    # (N, K, 3, 4)
            u = np.einsum("nkij,nj->nki", A_sel, v0h)
            self.meshes.append({
                "name": str(rig[f"m{i}_name"]), "faces": rig[f"m{i}_faces"].astype(np.int32),
                "uv": rig[f"m{i}_uv"].astype(np.float32), "uv_flip_v": bool(rig[f"m{i}_uv_flip_v"]),
                "texture": str(rig[f"m{i}_texture"]), "colour": [float(c) for c in rig[f"m{i}_colour"]],
                "u": torch.as_tensor(u, dtype=torch.float32, device=device),
                "w": torch.as_tensor(weights, dtype=torch.float32, device=device),
                "bodies": self.body_of_joint[torch.as_tensor(joints, device=device)],
                "faces_t": torch.as_tensor(rig[f"m{i}_faces"].astype(np.int64), device=device),
            })
        self.prims = []

    # ---------------------------------------------------------------- USD
    def create_prims(self, stage, root_path: str = "/World/Character", texture_root: str = ""):
        from pxr import Gf, Sdf, UsdGeom, UsdShade, Vt
        UsdGeom.Xform.Define(stage, root_path)
        for i, mesh in enumerate(self.meshes):
            path = f"{root_path}/mesh{i}_{''.join(ch if ch.isalnum() else '_' for ch in mesh['name'])}"
            prim = UsdGeom.Mesh.Define(stage, path)
            faces = mesh["faces"]
            prim.CreateFaceVertexCountsAttr(Vt.IntArray([3] * faces.shape[0]))
            prim.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(faces.reshape(-1).astype(np.int32)))
            n = mesh["u"].shape[0]
            prim.CreatePointsAttr(Vt.Vec3fArray(n, Gf.Vec3f(0, 0, 0)))
            prim.CreateSubdivisionSchemeAttr("none")
            prim.CreateDoubleSidedAttr(True)
            prim.CreateDisplayColorAttr(Vt.Vec3fArray([Gf.Vec3f(*mesh["colour"][:3])]))
            material = UsdShade.Material.Define(stage, f"{path}/material")
            shader = UsdShade.Shader.Define(stage, f"{path}/material/surface")
            shader.CreateIdAttr("UsdPreviewSurface")
            shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.6)
            shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(0.0)
            uv = mesh["uv"]
            if mesh["texture"] and uv.shape[0] == n:
                texture_path = str(Path(texture_root or self.folder) / mesh["texture"])
                st = UsdGeom.PrimvarsAPI(prim).CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex)
                coords = uv.copy()
                if mesh["uv_flip_v"]:
                    coords[:, 1] = 1.0 - coords[:, 1]
                st.Set(Vt.Vec2fArray.FromNumpy(coords.astype(np.float32)))
                reader = UsdShade.Shader.Define(stage, f"{path}/material/stReader")
                reader.CreateIdAttr("UsdPrimvarReader_float2")
                reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
                sampler = UsdShade.Shader.Define(stage, f"{path}/material/texture")
                sampler.CreateIdAttr("UsdUVTexture")
                sampler.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(texture_path)
                sampler.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
                sampler.CreateInput("wrapS", Sdf.ValueTypeNames.Token).Set("repeat")
                sampler.CreateInput("wrapT", Sdf.ValueTypeNames.Token).Set("repeat")
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(sampler.ConnectableAPI(), "rgb")
            else:
                shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*mesh["colour"][:3]))
            material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
            UsdShade.MaterialBindingAPI.Apply(prim.GetPrim()).Bind(material)
            self.prims.append(prim)

    @staticmethod
    def hide_robot(stage) -> list[str]:
        """Hide the capsule body so only the skinned character is rendered (physics is unaffected)."""
        from pxr import UsdGeom
        hidden = []
        for prim in stage.Traverse():
            path = str(prim.GetPath())
            if "/envs/" in path and path.endswith("/Robot") and prim.IsA(UsdGeom.Xformable):
                UsdGeom.Imageable(prim).MakeInvisible()
                hidden.append(path)
        return hidden

    # ---------------------------------------------------------------- per frame
    @torch.no_grad()
    def update(self, body_pos: torch.Tensor, body_rot_xyzw: torch.Tensor):
        """Skin every mesh from the 23 body poses (world) and write the points and normals."""
        from pxr import Vt
        R = quat_to_matrix(body_rot_xyzw.to(torch.float32))        # (23, 3, 3)
        p = body_pos.to(torch.float32)                               # (23, 3)
        for mesh, prim in zip(self.meshes, self.prims):
            Rk = R[mesh["bodies"]]                                   # (N, K, 3, 3)
            pk = p[mesh["bodies"]]                                   # (N, K, 3)
            v = torch.einsum("nkij,nkj->nki", Rk, mesh["u"]) + pk    # (N, K, 3)
            v = (v * mesh["w"].unsqueeze(-1)).sum(1)                 # (N, 3)
            faces = mesh["faces_t"]
            fn = torch.cross(v[faces[:, 1]] - v[faces[:, 0]], v[faces[:, 2]] - v[faces[:, 0]], dim=-1)
            normals = torch.zeros_like(v)
            normals.index_add_(0, faces.reshape(-1), fn.repeat_interleave(3, dim=0))
            normals = normals / normals.norm(dim=-1, keepdim=True).clamp(min=1e-8)
            prim.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(v.cpu().numpy()))
            prim.GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(normals.cpu().numpy()))
        return True
