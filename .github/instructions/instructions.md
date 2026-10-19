---
applyTo: "custom_components/surepcha/**/*.py"
description: "SurePetCare integration conventions for backend values and event-backed entities."
---

# SurePetCare Integration Guidelines

- Prefer backend and API values as they are. Avoid renaming, normalizing, or remapping them unless Home Assistant's entity contract or an outbound device command requires it.
- Preserve backend models when consumers support them. Serialize only when a boundary requires JSON-safe data; Home Assistant event-bus listeners receive the serialized mapping, not the original Pydantic model. At that boundary, expose typed enums by name and omit default empty or `None` fields when useful.
- Treat opaque backend `data` fields according to their declared type; do not assume strings contain valid JSON or parse them without a reliable schema.
- When Home Assistant-facing consistency requires interpreting backend values, use a shared read-time helper; keep the original event payload unchanged.
- Keep entity descriptions declarative: use `MethodField.path` to read values and `get_extra_fn` for attributes. Do not add per-entity selectors or mapping configuration when shared handling can resolve the event record.
- Event-backed entities must not have coordinator refreshes overwrite their state or silently fall back to polled values.
- Use exactly one timeline ingestion source per household: do not run a push/event stream alongside `SurePetCareHouseholdTimelineCoordinator` polling. If an event-stream mode is introduced, validate the configuration during setup and raise a config/setup error when both sources are enabled.