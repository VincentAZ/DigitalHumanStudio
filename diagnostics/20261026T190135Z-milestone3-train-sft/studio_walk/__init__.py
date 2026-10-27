"""Milestone 3 destination-walking task package for the pinned ProtoMotions runtime.

The package is mounted read-only inside the runtime container at /studio/scripts and
imported as ``studio_walk``; experiment files reference these importable kernels so
that pickled resolved configurations remain loadable at evaluation time.
"""

PRIOR_CHECKPOINT = "/studio/assets/data/pretrained_models/gpc_prior/soma_bones/inference_last.ckpt"
MOTION_FILE = "/studio/assets/data/motion_for_trackers/soma23_bones_seed_mini.pt"

# Clips in soma23_bones_seed_mini.pt whose reference poses are on the floor, crawling or
# kneeling (minimum root height below 0.6 m). They are not walking start states.
FLOOR_LEVEL_MOTION_IDS = [1, 4, 18, 25, 35, 39, 41, 42, 52, 57]
# Standing/walking clips reserved exclusively for acceptance-scenario start poses.
RESERVED_EVALUATION_MOTION_IDS = [7, 9, 20, 24, 43, 59]
TRAINING_EXCLUDED_MOTION_IDS = sorted(FLOOR_LEVEL_MOTION_IDS + RESERVED_EVALUATION_MOTION_IDS)

TARGET_PROXIMITY_THRESHOLD = 0.3
SOMA_FORWARD_AXIS_XY = (0.0, -1.0)
