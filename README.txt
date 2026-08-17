TechScope P3 Checkpoint + Preflight Resume v3

Why v2 failed
-------------
The Dev Container could not execute `gh`, so the checkpoint stopped before commit/push.

v3 design
---------
- Git checkpoint runs on Windows host, where GitHub push already works.
- Container does NOT call git or gh.
- Container only performs read-only P3 inspection.

Expected duration
-----------------
20 seconds to 1 minute.
Git push is the slowest stage.
If there is no output for more than 2 minutes, stop and send the full console output.

Run
---
.\RUN_P3_CHECKPOINT_PREFLIGHT_RESUME_V3.cmd
