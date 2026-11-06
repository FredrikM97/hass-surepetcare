# Integration development guidance

## Architecture and compatibility

- This is a Home Assistant custom integration, not Home Assistant core. Read
  [project overview](README.md) and [contribution guidance](CONTRIBUTING.md) before
  changing the affected implementation.
- This project owns HA field descriptors, evaluation, discovery, restoration,
  and presentation. The sibling `py-surepetcare` library owns API access, typed
  models, commands, timeline parsing, polling, and low-level matching helpers.
  Keep API behavior in the library; do not introduce a second field catalogue
  there or a reverse dependency on Home Assistant.
- Respect the Python requirement in [pyproject.toml](pyproject.toml), currently
  3.14.2+. The sibling library supports Python 3.13; do not apply this project's
  newer syntax requirement to library changes.
- Development uses editable `../ps`, but production uses the released library
  specified by the integration manifest. Check release compatibility when
  changing the shared API.

## Behavior to preserve

- Preserve entity unique IDs, user-disabled entries, automation payloads, and
  restoration-before-first-refresh behavior unless explicitly changing them.
- Use native HA platform descriptions and existing shared field helpers rather
  than adding field-key dispatch or a parallel descriptor framework.
- Keep explicit Home Assistant state properties such as `is_on`, backed by the
  corresponding `_attr_*` storage. Do not introduce parallel state fields.
- Keep missing, unavailable, zero, and false values distinct. Do not mask malformed
  data or failed requests with successful empty results.
- Preserve async cancellation and avoid blocking I/O in async paths.
- Do not bypass the library's timeline ordering, retries, or cursor semantics.
  Timeline delivery is at-least-once; callbacks must not assume exactly-once use.

## Making and verifying changes

- Develop first; defer running tests, formatters, linters, type checks, builds,
  snapshot updates, and pre-commit hooks until the user explicitly requests
  validation. Finishing an edit or a development turn is not permission to run
  checks. Do not run them automatically or in the background between edits.
- Continue adding or updating tests alongside code changes, but leave execution
  deferred. Report validation as deferred, not passed, until checks are requested.
- Read affected code and tests first. Reuse existing helpers, types, and fixtures;
  prefer realistic models over broad mocks.
- Prefer structured snapshots for values, attributes, options, metadata, and API
  payloads over many individual assertions. Keep direct assertions for exceptions,
  identity, invariants, and mock-call contracts; review snapshot changes for correctness.
- Make the smallest complete change, preserve unrelated worktree changes, and
  avoid unrelated refactors or dependency upgrades.
- Keep README.md user-focused and concise. Do not update it automatically for
  internal refactors or add implementation walkthroughs and change logs.
  Update it only when requested or needed to correct user-facing instructions.
- Keep AGENTS.md concise: durable guidance only, not implementation notes.
- Add regression tests for fixes and update directly affected documentation
  where necessary, following the README policy above.
  For lifecycle changes, cover startup, restoration, and live updates as applicable.
- When setup or validation is requested, run commands from this project directory:
  - Initial setup or dependency changes: `uv sync --group dev`.
  - Focused tests, for example: `uv run pytest tests/test_fields.py`.
  - Full tests: `uv run pytest tests`.
  - Pre-PR checks: `uv run pre-commit run --all-files`.
- During requested validation, start with affected tests and expand for shared-code changes. For cross-project
  API changes, also run relevant tests in the sibling library when available.
- Review snapshot diffs against intended behavior; do not regenerate snapshots
  merely to make failing tests pass. Use repository-configured lint and type checks.
- Do not install new tooling or resync environments merely to inspect code or
  make documentation-only changes.
- Ask before materially ambiguous behavior changes or destructive operations.
  Never use live accounts, devices, or credentials for validation without approval.
- Review the final diff and report exact checks run, failures, and unverified
  behavior. Do not claim checks passed without running them.
