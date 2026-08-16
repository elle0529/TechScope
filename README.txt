TechScope GitHub Snapshot v5

Observed v4 block
-----------------
STAGED_FILES=588
FORBIDDEN_TRACKED_PATH=.env.example

Cause
-----
`.env.example` was intentionally unignored as a safe configuration template,
but the later tracked-path policy treated every `.env.*` path as forbidden.

v5
--
1. Verifies prior SQL password sanitization.
2. Finds the already-installed GitHub CLI.
3. Validates every .env.example:
   sensitive keys such as PASSWORD / SECRET / TOKEN / API_KEY must contain
   only empty or obvious placeholder values.
4. Runs the general secret scan again.
5. Allows `.env.example` only after that validation passes.
6. Restages the repository.
7. Creates/reuses private repo elle0529/TechScope.
8. Commits, pushes, and verifies the remote main SHA.

The LF/CRLF warnings from Git are informational and are not treated as errors.

Expected duration
-----------------
2-5 minutes.
Do not interrupt after GIT_PUSH=START.
More than 10 minutes without progress is abnormal.

Run
---
.\RUN_TECHSCOPE_GITHUB_SNAPSHOT_V5.cmd
