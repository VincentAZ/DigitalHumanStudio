#!/usr/bin/env python3
"""Build config/character-sources.json from the downloaded character files and the rig reports.

- Hashes every recorded file under .runtime/downloads/characters/ (binaries stay out of Git).
- Hashes each saved licence text.
- Validates each proposed SOMA-23 joint map against the parsed rig report
  (.runtime/characters/reports/*.json written by inspect_rig.py).
- Compares limb segment lengths with the SOMA-23 MJCF rest offsets.

Writes: config/character-sources.json and .runtime/characters/reports/mapping-check.json.
Paths are derived from this file's location; the caller's working directory is irrelevant.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DOWNLOADS = ROOT / ".runtime" / "downloads"
CHAR_DL = DOWNLOADS / "characters"
REPORTS = ROOT / ".runtime" / "characters" / "reports"
MJCF = ROOT / "vendor/ProtoMotions/protomotions/data/assets/mjcf/soma23_humanoid.xml"
OUT = ROOT / "config" / "character-sources.json"

SOMA23 = [
    "Hips", "Spine1", "Spine2", "Chest", "Neck1", "Neck2", "Head",
    "RightShoulder", "RightArm", "RightForeArm", "RightHand",
    "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
    "RightLeg", "RightShin", "RightFoot", "RightToeBase",
    "LeftLeg", "LeftShin", "LeftFoot", "LeftToeBase",
]

# Segments used for the bone-length comparison (SOMA body -> child SOMA body).
SEGMENTS = {
    "upper_arm": ("RightArm", "RightForeArm"),
    "forearm": ("RightForeArm", "RightHand"),
    "thigh": ("RightLeg", "RightShin"),
    "shin": ("RightShin", "RightFoot"),
    "foot_to_toe": ("RightFoot", "RightToeBase"),
    "hips_to_head": ("Hips", "Head"),
    "shoulder_width": ("LeftArm", "RightArm"),
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_entry(rel: str) -> dict:
    p = DOWNLOADS / rel
    return {"path": rel, "sha256": sha256(p), "bytes": p.stat().st_size}


def mixamo_map(prefix: str = "mixamorig:") -> dict:
    m = {
        "Hips": "Hips", "Spine1": "Spine", "Spine2": "Spine1", "Chest": "Spine2",
        "Neck1": "Neck", "Neck2": None, "Head": "Head",
        "RightShoulder": "RightShoulder", "RightArm": "RightArm", "RightForeArm": "RightForeArm", "RightHand": "RightHand",
        "LeftShoulder": "LeftShoulder", "LeftArm": "LeftArm", "LeftForeArm": "LeftForeArm", "LeftHand": "LeftHand",
        "RightLeg": "RightUpLeg", "RightShin": "RightLeg", "RightFoot": "RightFoot", "RightToeBase": "RightToeBase",
        "LeftLeg": "LeftUpLeg", "LeftShin": "LeftLeg", "LeftFoot": "LeftFoot", "LeftToeBase": "LeftToeBase",
    }
    return {k: (prefix + v if v else None) for k, v in m.items()}


UE_MANNEQUIN_MAP = {
    "Hips": "pelvis", "Spine1": "spine_01", "Spine2": "spine_02", "Chest": "spine_03",
    "Neck1": "neck_01", "Neck2": None, "Head": "Head",
    "RightShoulder": "clavicle_r", "RightArm": "upperarm_r", "RightForeArm": "lowerarm_r", "RightHand": "hand_r",
    "LeftShoulder": "clavicle_l", "LeftArm": "upperarm_l", "LeftForeArm": "lowerarm_l", "LeftHand": "hand_l",
    "RightLeg": "thigh_r", "RightShin": "calf_r", "RightFoot": "foot_r", "RightToeBase": "ball_r",
    "LeftLeg": "thigh_l", "LeftShin": "calf_l", "LeftFoot": "foot_l", "LeftToeBase": "ball_l",
}

KAYKIT_MAP = {
    "Hips": "hips", "Spine1": "spine", "Spine2": None, "Chest": "chest",
    "Neck1": None, "Neck2": None, "Head": "head",
    "RightShoulder": None, "RightArm": "upperarm.r", "RightForeArm": "lowerarm.r", "RightHand": "wrist.r",
    "LeftShoulder": None, "LeftArm": "upperarm.l", "LeftForeArm": "lowerarm.l", "LeftHand": "wrist.l",
    "RightLeg": "upperleg.r", "RightShin": "lowerleg.r", "RightFoot": "foot.r", "RightToeBase": "toes.r",
    "LeftLeg": "upperleg.l", "LeftShin": "lowerleg.l", "LeftFoot": "foot.l", "LeftToeBase": "toes.l",
}

CESIUMMAN_MAP = {
    "Hips": "Skeleton_torso_joint_1", "Spine1": "Skeleton_torso_joint_2", "Spine2": None, "Chest": "torso_joint_3",
    "Neck1": "Skeleton_neck_joint_1", "Neck2": None, "Head": "Skeleton_neck_joint_2",
    "RightShoulder": None, "RightArm": "Skeleton_arm_joint_R", "RightForeArm": "Skeleton_arm_joint_R__2_", "RightHand": "Skeleton_arm_joint_R__3_",
    "LeftShoulder": None, "LeftArm": "Skeleton_arm_joint_L__4_", "LeftForeArm": "Skeleton_arm_joint_L__3_", "LeftHand": "Skeleton_arm_joint_L__2_",
    "RightLeg": "leg_joint_R_1", "RightShin": "leg_joint_R_2", "RightFoot": "leg_joint_R_3", "RightToeBase": "leg_joint_R_5",
    "LeftLeg": "leg_joint_L_1", "LeftShin": "leg_joint_L_2", "LeftFoot": "leg_joint_L_3", "LeftToeBase": "leg_joint_L_5",
}

RIGGEDFIGURE_MAP = {
    "Hips": "torso_joint_1", "Spine1": "torso_joint_2", "Spine2": None, "Chest": "torso_joint_3",
    "Neck1": "neck_joint_1", "Neck2": None, "Head": "neck_joint_2",
    "RightShoulder": None, "RightArm": "arm_joint_R_1", "RightForeArm": "arm_joint_R_2", "RightHand": "arm_joint_R_3",
    "LeftShoulder": None, "LeftArm": "arm_joint_L_1", "LeftForeArm": "arm_joint_L_2", "LeftHand": "arm_joint_L_3",
    "RightLeg": "leg_joint_R_1", "RightShin": "leg_joint_R_2", "RightFoot": "leg_joint_R_3", "RightToeBase": "leg_joint_R_5",
    "LeftLeg": "leg_joint_L_1", "LeftShin": "leg_joint_L_2", "LeftFoot": "leg_joint_L_3", "LeftToeBase": "leg_joint_L_5",
}

ROCKETBOX_MAP = {
    "Hips": "Bip01 Pelvis", "Spine1": "Bip01 Spine", "Spine2": "Bip01 Spine1", "Chest": "Bip01 Spine2",
    "Neck1": "Bip01 Neck", "Neck2": None, "Head": "Bip01 Head",
    "RightShoulder": "Bip01 R Clavicle", "RightArm": "Bip01 R UpperArm", "RightForeArm": "Bip01 R Forearm", "RightHand": "Bip01 R Hand",
    "LeftShoulder": "Bip01 L Clavicle", "LeftArm": "Bip01 L UpperArm", "LeftForeArm": "Bip01 L Forearm", "LeftHand": "Bip01 L Hand",
    "RightLeg": "Bip01 R Thigh", "RightShin": "Bip01 R Calf", "RightFoot": "Bip01 R Foot", "RightToeBase": "Bip01 R Toe0",
    "LeftLeg": "Bip01 L Thigh", "LeftShin": "Bip01 L Calf", "LeftFoot": "Bip01 L Foot", "LeftToeBase": "Bip01 L Toe0",
}

KENNEY_BLOCKY_MAP = {
    "Hips": "root", "Spine1": None, "Spine2": None, "Chest": "torso", "Neck1": None, "Neck2": None, "Head": "head",
    "RightShoulder": None, "RightArm": "arm-right", "RightForeArm": None, "RightHand": None,
    "LeftShoulder": None, "LeftArm": "arm-left", "LeftForeArm": None, "LeftHand": None,
    "RightLeg": "leg-right", "RightShin": None, "RightFoot": None, "RightToeBase": None,
    "LeftLeg": "leg-left", "LeftShin": None, "LeftFoot": None, "LeftToeBase": None,
}

CC0 = {"name": "CC0 1.0 Universal", "spdx": "CC0-1.0", "url": "https://creativecommons.org/publicdomain/zero/1.0/"}
CCBY4 = {"name": "Creative Commons Attribution 4.0 International", "spdx": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/legalcode"}
APACHE2 = {"name": "Apache License 2.0", "spdx": "Apache-2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"}
MIT = {"name": "MIT License", "spdx": "MIT", "url": "https://opensource.org/license/mit"}

SURVEY_DATE = "2026-10-27"

SOURCES = [
    {
        "id": "soma-x",
        "name": "NVIDIA SOMA-X template rig (SOMA neutral body)",
        "status": "downloaded",
        "url": "https://huggingface.co/nvidia/SOMA-X",
        "source_urls": [
            "https://github.com/NVlabs/SOMA-X",
            "https://github.com/NVlabs/SOMA-X/releases/tag/v0.3.4",
        ],
        "pinned": {"huggingface_revision": "f81a01796f652260ff930d5318d6c6b845a505ed", "github_release": "v0.3.4",
                   "github_commit": "56a3d957a549c66425b500fddf7f3183bc6fbdff"},
        "licence": {**APACHE2, "text_file": "characters/soma-x/LICENSE",
                    "attribution_required": "Retain the Apache-2.0 LICENSE and copyright notices (NVIDIA Corporation). Model card: 'ready for commercial use'. Optional SMPL/SMPL-X/MANO/MHR/Anny backends are NOT included and keep their own terms."},
        "files": ["characters/soma-x/LICENSE", "characters/soma-x/README.md", "characters/soma-x/SOMA-X-HF-MANIFEST.json",
                  "characters/soma-x/SOMA_procedural_transforms.json", "characters/soma-x/SOMA_template_rig.usda",
                  "characters/soma-x/SOMA_neutral.npz", "characters/soma-x/example_animation.usd"],
        "rig_file": "characters/soma-x/SOMA_template_rig.usda",
        "report": "SOMA_template_rig_usda.json",
        "format": "USDA (UsdSkel), Y-up, centimetres (metersPerUnit=0.01)",
        "joint_map": {b: b for b in SOMA23},
        "joint_name_regex": r"^Root/(?:[^/]+/)*(?P<name>[^/]+)$",
        "notes": "The USD joints are paths under Root/Hips/...; the leaf names equal the SOMA-23 body names, so the map is the identity. 110 joints (fingers, twist bones, eyes, jaw) and 136,739 vertices (hi-res body + eye meshes); no textures. File hashes match SOMA-X-HF-MANIFEST.json.",
    },
    {
        "id": "quaternius-universal-base-characters",
        "name": "Quaternius Universal Base Characters (Standard/free tier)",
        "status": "downloaded",
        "url": "https://quaternius.com/packs/universalbasecharacters.html",
        "source_urls": ["https://quaternius.itch.io/universal-base-characters"],
        "pinned": {"itch_upload_id": "15861669", "file_name": "Universal Base Characters[Standard].zip", "itch_listed_size": "122 MB"},
        "licence": {**CC0, "text_file": "characters/quaternius-universal-base-characters/extracted/Universal Base Characters[Standard]/License_Standard.txt",
                    "attribution_required": "None (CC0). Credit 'Models by Quaternius' is optional."},
        "files": ["characters/quaternius-universal-base-characters/Universal_Base_Characters_Standard.zip"],
        "rig_file": "characters/quaternius-universal-base-characters/extracted/Universal Base Characters[Standard]/Base Characters/Godot - UE/Superhero_Male_FullBody.gltf",
        "report": "Superhero_Male_FullBody_gltf.json",
        "format": "glTF 2.0 (.gltf + .bin + PNG textures); FBX duplicates for Unity; Y-up metres",
        "joint_map": UE_MANNEQUIN_MAP,
        "notes": "Free tier contains only the two Superhero bodies (male/female) plus hairstyles; Regular/Teen bodies are in the paid Source tier. Rig uses Unreal-mannequin names (pelvis, spine_01..03, neck_01, clavicle/upperarm/lowerarm/hand, thigh/calf/foot/ball) plus full fingers; 65 joints. The itch.io download was obtained with the free 'no thanks' flow (POST download_url, then POST file/<upload_id>).",
    },
    {
        "id": "kaykit-adventurers",
        "name": "KayKit Character Pack: Adventurers 1.0 (GitHub mirror of the free tier)",
        "status": "downloaded",
        "url": "https://github.com/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0",
        "source_urls": ["https://kaylousberg.itch.io/kaykit-adventurers"],
        "pinned": {"github_commit": "672074b73ba276876a19e8816ecdc5241817ab47"},
        "licence": {**CC0, "text_file": "characters/kaykit-adventurers/LICENSE.txt",
                    "attribution_required": "None (CC0); the pack asks not to resell unmodified copies. Credit 'Kay Lousberg, www.kaylousberg.com' is optional."},
        "files": ["characters/kaykit-adventurers/LICENSE.txt", "characters/kaykit-adventurers/README.md"]
                 + [f"characters/kaykit-adventurers/Characters/gltf/{f}" for f in
                    ["Barbarian.glb", "Knight.glb", "Mage.glb", "Rogue.glb", "Rogue_Hooded.glb",
                     "barbarian_texture.png", "knight_texture.png", "mage_texture.png", "rogue_texture.png"]],
        "rig_file": "characters/kaykit-adventurers/Characters/gltf/Knight.glb",
        "report": "Knight_glb.json",
        "format": "GLB (textures embedded), Y-up metres; 1.0 release (itch.io now lists 2.0)",
        "joint_map": KAYKIT_MAP,
        "notes": "41 joints: 23 deform bones plus IK/control bones (kneeIK, heelIK, handIK, control-*-roll). No clavicles, single spine+chest, no neck. Low-poly (5-7k vertices), gradient atlas texture. Includes 75 animations in the GLB.",
    },
    {
        "id": "kenney-blocky-characters",
        "name": "Kenney Blocky Characters 2.0 (OpenGameArt mirror)",
        "status": "downloaded",
        "url": "https://kenney.nl/assets/blocky-characters",
        "source_urls": ["https://opengameart.org/content/blocky-characters"],
        "pinned": {"mirror_file": "https://opengameart.org/sites/default/files/kenney_blocky-characters_2.0.zip"},
        "licence": {**CC0, "text_file": "characters/kenney-blocky-characters/extracted/License.txt",
                    "attribution_required": "None (CC0). Credit 'Kenney' / www.kenney.nl is optional."},
        "files": ["characters/kenney-blocky-characters/kenney_blocky-characters_2.0.zip"],
        "rig_file": "characters/kenney-blocky-characters/extracted/Models/GLB format/character-a.glb",
        "report": "character-a_glb.json",
        "format": "GLB/FBX/OBJ, Y-up metres",
        "joint_map": KENNEY_BLOCKY_MAP,
        "notes": "Not a skinned humanoid: 7 rigid part nodes (root, torso, head, arm-left/right, leg-left/right) with 27 animations, 143 vertices. Usable only as a stylised placeholder; most SOMA-23 bodies have no counterpart. kenney.nl's own download link rejected scripted fetches (HTTP 403 'Download link expired or invalid'), so the OpenGameArt mirror was used; the zip carries Kenney's own CC0 License.txt.",
    },
    {
        "id": "khronos-gltf-sample-assets",
        "name": "Khronos glTF Sample Assets: CesiumMan, RiggedFigure, RiggedSimple",
        "status": "downloaded",
        "url": "https://github.com/KhronosGroup/glTF-Sample-Assets",
        "source_urls": [
            "https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/Models/CesiumMan/README.md",
            "https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/Models/RiggedFigure/README.md",
        ],
        "pinned": {"github_commit": "8f492390ddc7a2ae221a1369ef560589cf8c70fb"},
        "licence": {**CCBY4, "text_file": "characters/khronos-gltf-sample-assets/CC-BY-4.0.txt",
                    "attribution_required": "'CesiumMan / RiggedFigure / RiggedSimple © 2017 Cesium, CC BY 4.0'. The Cesium logo texture inside CesiumMan is a trademark excluded from CC-BY (LicenseRef-LegalMark-Cesium)."},
        "files": ["characters/khronos-gltf-sample-assets/CC-BY-4.0.txt", "characters/khronos-gltf-sample-assets/LicenseRef-LegalMark-Cesium.txt",
                  "characters/khronos-gltf-sample-assets/CesiumMan/CesiumMan.glb", "characters/khronos-gltf-sample-assets/CesiumMan/LICENSE.md",
                  "characters/khronos-gltf-sample-assets/CesiumMan/metadata.json",
                  "characters/khronos-gltf-sample-assets/RiggedFigure/RiggedFigure.glb", "characters/khronos-gltf-sample-assets/RiggedFigure/LICENSE.md",
                  "characters/khronos-gltf-sample-assets/RiggedFigure/metadata.json",
                  "characters/khronos-gltf-sample-assets/RiggedSimple/RiggedSimple.glb", "characters/khronos-gltf-sample-assets/RiggedSimple/LICENSE.md",
                  "characters/khronos-gltf-sample-assets/RiggedSimple/metadata.json"],
        "rig_file": "characters/khronos-gltf-sample-assets/CesiumMan/CesiumMan.glb",
        "report": "CesiumMan_glb.json",
        "format": "GLB, Y-up metres",
        "joint_map": CESIUMMAN_MAP,
        "extra_joint_maps": {"RiggedFigure.glb": RIGGEDFIGURE_MAP},
        "notes": "19-joint test rigs, about 1.2 m tall. Good for pipeline tests (skinning, animation playback), too crude for a shipped character. RiggedSimple is a 2-bone cylinder (no map). BrainStem (same repo) is excluded: LicenseRef-Poser-EULA.",
    },
    {
        "id": "100avatars",
        "name": "Polygonal Mind 100Avatars (VRM + FBX, Mixamo auto-rigged)",
        "status": "downloaded",
        "url": "https://github.com/PolygonalMind/100Avatars",
        "source_urls": [],
        "pinned": {"github_commit": "ff07c2ad0017819c4e5366656ee1e5bcc4029bd4"},
        "licence": {**CCBY4, "text_file": "characters/100avatars/CCLicense.md",
                    "attribution_required": "'100Avatars by Polygonal Mind (https://github.com/PolygonalMind/100Avatars), CC BY 4.0'. README asks not to sell the avatars without major modification (a request, not a licence term)."},
        "files": ["characters/100avatars/CCLicense.md", "characters/100avatars/README.md",
                  "characters/100avatars/100Avatars_001.zip", "characters/100avatars/100Avatars_002.zip"],
        "rig_file": "characters/100avatars/extracted/100Avatars_001/100Avatars_001_Crimsom.vrm",
        "report": "100Avatars_001_Crimsom_vrm.json",
        "format": "VRM 0.0 (glTF 2.0 binary with VRM humanoid extension) + FBX + PNG; Y-up metres",
        "joint_map": mixamo_map("vis_char_001_fbx:mixamorig:"),
        "joint_name_regex": r"^(?:.*mixamorig:)(?P<name>.+)$",
        "notes": "Two of 200 avatars fetched (001 Crimsom, 002 CoolAlien; each zip 3-4 MB). Mixamo bone names with a per-file prefix (strip with joint_name_regex). The VRM 'humanoid.humanBones' block gives a second, standardised name map. Stylised ~1.2 m voxel-ish characters; FBX report shows the same skeleton.",
    },
    {
        "id": "microsoft-rocketbox",
        "name": "Microsoft Rocketbox avatar library (Male_Adult_01 sample)",
        "status": "downloaded",
        "url": "https://github.com/microsoft/Microsoft-Rocketbox",
        "source_urls": ["https://www.frontiersin.org/articles/10.3389/frvir.2020.561558/abstract"],
        "pinned": {"github_commit": "0943055db6ec570bcef9f2c8b41c9e5467c808f9"},
        "licence": {**MIT, "text_file": "characters/microsoft-rocketbox/LICENSE.md",
                    "attribution_required": "Retain 'Copyright (c) 2020 Microsoft' and the MIT licence text. Citation of the Frontiers paper is requested for research use (not a licence term)."},
        "files": ["characters/microsoft-rocketbox/LICENSE.md", "characters/microsoft-rocketbox/README.md",
                  "characters/microsoft-rocketbox/Male_Adult_01/Male_Adult_01.fbx",
                  "characters/microsoft-rocketbox/Male_Adult_01/Textures/m002_body_color.tga",
                  "characters/microsoft-rocketbox/Male_Adult_01/Textures/m002_head_color.tga",
                  "characters/microsoft-rocketbox/Male_Adult_01/Textures/m002_opacity_color.tga"],
        "rig_file": "characters/microsoft-rocketbox/Male_Adult_01/Male_Adult_01.fbx",
        "report": "Male_Adult_01_fbx.json",
        "format": "FBX binary 7.4 (3ds Max Biped 'Bip01' rig), Y-up, UnitScaleFactor 1 (cm); TGA textures",
        "joint_map": ROCKETBOX_MAP,
        "notes": "115 realistic adults/children/professions, 4k vertices each, 82 bones incl. facial bones. Only one avatar (4 GB repo) fetched. Biped topology differs: clavicles are children of Neck and thighs of Spine in this export; A-pose rest. FBX needs a converter (Blender or FBX SDK) to reach USD; normal/specular TGAs (12 MB each) not fetched.",
    },
    # ------------------------------------------------------------------ not downloaded
    {
        "id": "mixamo",
        "name": "Adobe Mixamo characters",
        "status": "excluded",
        "exclusion_reason": "Adobe terms permit royalty-free use of characters/animations inside projects but the raw character files may not be redistributed; download needs an Adobe ID (web app only, no API). Documented for manual, user-local import only; nothing is shipped.",
        "url": "https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html",
        "source_urls": ["https://web.archive.org/web/20260105134624/https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html",
                        "https://community.adobe.com/t5/mixamo-discussions/mixamo-faq-licensing-royalties-ownership-eula-and-tos/td-p/13234775",
                        "https://www.adobe.com/legal/terms.html"],
        "licence": {"name": "Adobe General Terms of Use (Mixamo FAQ)", "spdx": "LicenseRef-Adobe-Mixamo", "url": "https://helpx.adobe.com/creative-cloud/faq/mixamo-faq.html",
                    "attribution_required": "None per the FAQ re-post ('not required to give credit to Adobe, Mixamo, or Fuse'); unverified against the live page (HTTP 403 from this host)."},
        "format": "FBX / Collada from the web app; Mixamo bone names (mixamorig:*)",
        "joint_map": mixamo_map(),
        "joint_name_regex": r"^(?:mixamorig\d*:)?(?P<name>.+)$",
        "manual_path": "Sign in at https://www.mixamo.com with an Adobe ID, pick a character, Download (FBX Binary, T-pose, with skin), save under .runtime/downloads/characters/mixamo/<name>/ with a SOURCE.txt; never commit or ship the files.",
    },
    {
        "id": "blender-studio-characters",
        "name": "Blender Studio characters (Snow, Rain, Einar, ...)",
        "status": "deferred",
        "exclusion_reason": "Licence is CC-BY (permits use and redistribution with credit), but the downloads are .blend-only archives (Snow v2: 105.6 MB) with CloudRig rigs; no Blender is installed on this host, so the rig cannot be parsed or converted yet. Not downloaded.",
        "url": "https://studio.blender.org/characters/",
        "source_urls": ["https://studio.blender.org/characters/snow/v2/"],
        "licence": {"name": "Creative Commons Attribution (CC-BY)", "spdx": "CC-BY-4.0", "url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution_required": "'Snow Rig © Blender Foundation | studio.blender.org' (wording from the character page)."},
        "format": ".blend (CloudRig / Rigify-style), needs Blender export to glTF/USD",
    },
    {
        "id": "sketchfab-cc0",
        "name": "Sketchfab CC0 / CC-BY rigged humanoids",
        "status": "deferred",
        "exclusion_reason": "Downloads require a Sketchfab account and API token; not fetched. Licence must be checked per model.",
        "url": "https://sketchfab.com/3d-models?features=downloadable&licenses=7c23a1ba438d4306920229c12afcb5f9",
        "licence": {"name": "per-model (CC0 filter)", "spdx": None, "url": "https://sketchfab.com/licenses"},
    },
    {
        "id": "opengameart-base-rigged-yw",
        "name": "OpenGameArt 'Base Rigged Stylized Humanoid Character (YW)' by Girush",
        "status": "deferred",
        "exclusion_reason": "CC0 and a direct download exists (7z, 4.6 MB), but the model format inside the archive is not stated and no 7z extractor is installed; not fetched.",
        "url": "https://opengameart.org/content/base-rigged-stylized-humanoid-character-yw",
        "source_urls": ["https://opengameart.org/sites/default/files/basemesh_a1_human_yw_by_girush_2.7z"],
        "licence": {**CC0},
    },
    {
        "id": "kenney-animated-characters",
        "name": "Kenney Animated Characters (Protagonists / Retro / Survivors) and Mini Characters",
        "status": "deferred",
        "exclusion_reason": "CC0 per the pack pages, but kenney.nl's tokenised download URL returned HTTP 403 'Download link expired or invalid' to scripted requests; a manual browser download is needed. Not fetched; rig type unverified.",
        "url": "https://kenney.nl/assets/animated-characters-protagonists",
        "source_urls": ["https://kenney.nl/assets/animated-characters-retro", "https://kenney.nl/assets/animated-characters-survivors", "https://kenney.nl/assets/mini-characters"],
        "licence": {**CC0},
    },
    {
        "id": "khronos-brainstem",
        "name": "Khronos glTF Sample Assets: BrainStem",
        "status": "excluded",
        "exclusion_reason": "metadata.json declares LicenseRef-Poser-EULA (Smith Micro Software), not a free licence.",
        "url": "https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/BrainStem",
        "licence": {"name": "Poser EULA", "spdx": "LicenseRef-Poser-EULA", "url": "https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/LICENSES/LicenseRef-Poser-EULA.txt"},
    },
    {
        "id": "smpl-family",
        "name": "SMPL / SMPL-X / MANO body models (SOMA-X optional backends)",
        "status": "excluded",
        "exclusion_reason": "Non-commercial research licences that require registration; SOMA-X deliberately does not redistribute them. The studio uses only the native SOMA identity.",
        "url": "https://smpl.is.tue.mpg.de/modellicense.html",
        "licence": {"name": "SMPL Model License (non-commercial)", "spdx": "LicenseRef-SMPL", "url": "https://smpl.is.tue.mpg.de/modellicense.html"},
    },
    {
        "id": "engine-bundled-mannequins",
        "name": "Unreal Engine Mannequin / Unity sample characters / three.js Mixamo-derived demo models",
        "status": "excluded",
        "exclusion_reason": "Engine EULA content (Unreal, Unity Asset Store) is licensed for use with that engine only; three.js' Xbot/Ybot/Soldier/Michelle GLBs are Mixamo exports whose terms are Adobe's, not the repo's MIT. Not verified further in this session.",
        "url": "https://www.unrealengine.com/en-US/eula/content",
        "licence": {"name": "engine-specific EULA", "spdx": None, "url": "https://www.unrealengine.com/en-US/eula/content"},
    },
]


# --------------------------------------------------------------------------- SOMA-23 reference
def soma23_mjcf_positions() -> dict:
    tree = ET.parse(MJCF)
    pos = {}

    def walk(body, parent_pos):
        p = parent_pos + np.array([float(x) for x in body.get("pos", "0 0 0").split()])
        pos[body.get("name")] = p
        for child in body.findall("body"):
            walk(child, p)

    for body in tree.getroot().find("worldbody").findall("body"):
        walk(body, np.zeros(3))
    return pos


def segment_lengths(pos_by_soma: dict) -> dict:
    out = {}
    for seg, (a, b) in SEGMENTS.items():
        if a in pos_by_soma and b in pos_by_soma:
            out[seg] = round(float(np.linalg.norm(np.array(pos_by_soma[a]) - np.array(pos_by_soma[b]))), 4)
        else:
            out[seg] = None
    return out


def load_report(name: str) -> dict:
    return json.loads((REPORTS / name).read_text())


def joint_positions(report: dict, regex: str | None):
    """Return {joint display name: position} from the first skin, in metres."""
    joints = report["skins"][0]["joints"] if report["skins"] else []
    key = "rest_world_pos_m" if joints and "rest_world_pos_m" in joints[0] else "rest_world_pos"
    out = {}
    for j in joints:
        name = j.get("path") or j["name"]
        if regex:
            m = re.match(regex, name)
            if m:
                name = m.group("name")
            elif "path" in j:
                name = j["name"]
        out[name] = j[key]
        out.setdefault(j["name"], j[key])
    return out


def validate(entry: dict) -> dict:
    rep = load_report(entry["report"])
    pos = joint_positions(rep, entry.get("joint_name_regex"))
    check = {"rig_file": entry["rig_file"], "format": rep["format"], "joint_count": rep["skins"][0]["joint_count"] if rep["skins"] else 0,
             "mesh_vertex_count": rep["mesh_vertex_count"], "has_skin_weights": rep["has_skin_weights"],
             "has_textures": rep["has_textures"], "missing_joints": [], "unmapped_soma_bodies": []}
    mapped = {}
    for soma, rig in entry["joint_map"].items():
        if rig is None:
            check["unmapped_soma_bodies"].append(soma)
        elif rig not in pos:
            check["missing_joints"].append(rig)
        else:
            mapped[soma] = pos[rig]
    check["segment_lengths_m"] = segment_lengths(mapped)
    if "Hips" in mapped and "Head" in mapped:
        check["hips_height_m"] = round(float(mapped["Hips"][1]), 4)
        check["head_joint_height_m"] = round(float(mapped["Head"][1]), 4)
    return check


def main():
    soma_pos = soma23_mjcf_positions()
    ref = {"mjcf": str(MJCF.relative_to(ROOT)), "bodies": SOMA23, "up_axis": "Z", "units": "metres", "facing": "-Y",
           "rest_positions_m": {k: [round(float(x), 4) for x in v] for k, v in soma_pos.items()},
           "segment_lengths_m": segment_lengths(soma_pos)}
    ref["hips_height_m"] = 0.0
    ref["head_joint_height_m"] = round(float(soma_pos["Head"][2]), 4)

    entries, checks = [], {}
    for src in SOURCES:
        e = {k: v for k, v in src.items() if k not in ("files", "rig_file", "report")}
        if "text_file" in src.get("licence", {}):
            lt = DOWNLOADS / src["licence"]["text_file"]
            e["licence"]["text_sha256"] = sha256(lt)
            e["licence"]["text_bytes"] = lt.stat().st_size
        if src.get("files"):
            e["files"] = [file_entry(f) for f in src["files"]]
            e["total_bytes"] = sum(f["bytes"] for f in e["files"])
        if src.get("report"):
            e["rig_file"] = src["rig_file"]
            e["rig_report"] = f".runtime/characters/reports/{src['report']}"
            chk = validate(src)
            e["joint_count"] = chk["joint_count"]
            e["mesh_vertex_count"] = chk["mesh_vertex_count"]
            e["has_skin_weights"] = chk["has_skin_weights"]
            e["has_textures"] = chk["has_textures"]
            e["unmapped_soma_bodies"] = chk["unmapped_soma_bodies"]
            e["mapping_check"] = {"missing_joints": chk["missing_joints"], "segment_lengths_m": chk["segment_lengths_m"],
                                  "hips_height_m": chk.get("hips_height_m"), "head_joint_height_m": chk.get("head_joint_height_m")}
            checks[src["id"]] = chk
            for extra_file, extra_map in src.get("extra_joint_maps", {}).items():
                sub = dict(src, joint_map=extra_map, report=extra_file.replace(".", "_") + ".json", rig_file=extra_file)
                checks[f"{src['id']}:{extra_file}"] = validate(sub)
        entries.append(e)

    out = {
        "schema_version": 1,
        "survey_date": SURVEY_DATE,
        "generated_by": "scripts/characters/build_character_sources.py",
        "download_root": ".runtime/downloads",
        "target_skeleton": ref,
        "recommended_first_character": "soma-x",
        "sources": entries,
    }
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    (REPORTS / "mapping-check.json").write_text(json.dumps({"target": ref, "rigs": checks}, indent=1) + "\n")

    print(f"wrote {OUT.relative_to(ROOT)} ({len(entries)} sources)")
    print("SOMA-23 MJCF segments:", ref["segment_lengths_m"])
    for sid, chk in checks.items():
        flag = "OK" if not chk["missing_joints"] else f"MISSING {chk['missing_joints']}"
        print(f"{sid:50s} joints={chk['joint_count']:4d} verts={chk['mesh_vertex_count']:7d} {flag}")
        print(f"{'':50s} unmapped={chk['unmapped_soma_bodies']}")
        print(f"{'':50s} segments={chk['segment_lengths_m']} hips_y={chk.get('hips_height_m')}")
    total = sum(e.get("total_bytes", 0) for e in entries)
    print(f"total downloaded bytes recorded: {total} ({total/1e6:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
