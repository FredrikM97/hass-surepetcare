---
applyTo: "tests/**/*.py"
description: "Require representative fixtures and snapshots for SurePetCare integration tests."
---

# Testing Guidelines

- Use Syrupy snapshots for structured outputs such as Home Assistant states, event payloads, and entity registry entries. Put focused scalar invariants and control-flow checks in separate behavior tests, not platform snapshot tests.
- Platform snapshot tests must not add direct assertions about captured state or attributes. Their test body should only call `initialize_entry` and `snapshot_platform`; put timeline response sequencing in named `conftest.py` fixtures and behavior checks in separate focused tests.
- Never add fallback values for event-backed entities. Without a matching event, their value remains unavailable; do not substitute polled status or another data source.
- Always use representative data from `tests/fixtures/` for API and timeline payloads. Parse fixtures into the relevant backend models; never hand-build inline API or timeline payload dictionaries.
- Load shared fixture data through named `conftest.py` fixtures as generic backend models; tests should consume those fixtures as parameters instead of indexing scenario maps. Add a named singular fixture for a specific representative event, and use indirect parametrization when a test needs several named scenarios.
- Put reusable scenario setup in named `conftest.py` fixtures. Treat loaded API and timeline fixture models as immutable: never copy-and-update them, change their fields or nested collections, or rewrite fixture payloads to align IDs with test entities. Split original events into named response batches when sequencing matters.
- Keep `tests/support.py` limited to reusable Home Assistant testing utilities such as snapshot serializers and config-entry helpers. Put fixture loading and test-domain model helpers in `conftest.py` or the relevant test module.
- Never alter fixture data for test convenience. Additional fixture records must be real representative API payloads, not synthetic replacements or identifier-adjusted copies.