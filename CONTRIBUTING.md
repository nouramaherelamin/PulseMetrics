# Contributing

## Start locally

After publication, use the actual repository URL supplied by the lead: `git clone <approved-repository-url>`, then enter the checkout. No remote exists yet; the placeholder is not a working URL. Choose a fresh parent directory so the sibling build/environment directories do not collide with another checkout.

Follow [Windows setup](docs/setup.md), install the pinned runtime and development requirements into the sibling virtual environment, then run `scripts/build.py` and `scripts/launch.py` with that environment's Python. Do not commit runtime data or alter system PATH. Read [architecture](docs/architecture.md) and [user guide](docs/user-guide.md) before changing behavior.

## Branch, review and validate

1. Start from the approved main branch; create `git switch -c fix/short-description` (or `feat/`, `docs/`, `test/`). Agree scope with the lead before changing accepted behavior or UI.
2. Keep commits focused: `fix: description`, `docs: description`, `test: description`, or `feat: description`. Describe why a change is necessary. Use your own verified identity; never attribute work to another contributor.
3. Run the environment's Python with `scripts/verify.py --configuration Release`. It builds current native source, runs CTest and pytest, and records evidence outside source. Add relevant regression tests for behavior changes; do not weaken assertions to make checks pass.
4. Inspect `git diff` and `git status`; exclude secrets, personal process history, caches and generated files. Record actual test results and remaining limitations.
5. After a remote is separately approved, open a pull request describing the problem, changes, tests and risks. UI changes require explicit approval and genuine privacy-reviewed captures. Require reviewer approval before merging; resolve review comments and rerun affected verification.

The lead should configure main-branch protection after remote creation: require pull requests and review, prevent force pushes/deletion, and require relevant checks when automated checks exist. These protections are recommendations, not currently configured GitHub settings. Do not push directly to approved main or rewrite shared history without authorization.

No first-party license or publication permission is implied by this file. Preserve vendor notices and record actual contributions honestly.
