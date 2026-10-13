---
applyTo: "tests/**/*.py"
description: "Require representative fixtures and snapshots for SurePetCare integration tests."
---

# Testing Guidelines

- Use Syrupy snapshots for structured outputs such as Home Assistant states, event payloads, and entity registry entries. Direct assertions may supplement snapshots for focused scalar invariants and control-flow outcomes.
- Always use representative data from `tests/fixtures/` for API and timeline payloads. Parse fixtures into the relevant backend models; never hand-build inline API or timeline payload dictionaries.
- Load shared fixture data through named `conftest.py` fixtures as generic backend models; tests should consume those fixtures as parameters instead of indexing scenario maps. Add a named singular fixture for a specific representative event, and use indirect parametrization when a test needs several named scenarios.
- Put reusable entity-alignment and scenario setup in named `conftest.py` fixtures. Do not add test-local helpers that copy, mutate, serialize, or otherwise construct API/timeline events; preserve fixture payloads except for targeted identifiers required to match the entity under test.
- Keep `tests/support.py` limited to reusable Home Assistant testing utilities such as snapshot serializers and config-entry helpers. Put fixture loading and test-domain model helpers in `conftest.py` or the relevant test module.
- Keep fixture adaptation limited to values needed to target the test entity; preserve the backend payload shape and avoid deriving replacement fields in tests.