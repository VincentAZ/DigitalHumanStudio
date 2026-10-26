# SOMA articulation probe — blocked launcher prerequisite

The process exited 1; the wrapper exited 4 and retained its container. ProtoMotions constructs `output/renderings` relative to the working directory in `record.py::_init_recording_state`. The inherited image working directory `/opt/IsaacLab` is not writable by the user. `PermissionError` occurred before `IsaacLabSimulator` created its SimulationContext or loaded the articulation.

No motion data or learned policy was used. The initial attempt therefore does not establish humanoid physics compatibility. The launcher repair sets `--workdir /studio/output`, an existing writable bind mount. Original command, complete logs, configuration, process and wrapper exit codes, and container inspection are preserved here. The image, source revisions, body contract and host are unchanged.
