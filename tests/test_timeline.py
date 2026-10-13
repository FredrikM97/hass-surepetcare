from surepcio.timeline import TimelineEvent
from syrupy.assertion import SnapshotAssertion

from custom_components.surepcha.timeline import build_event_payload


def test_timeline_fixture_payloads(
    timeline_events: list[TimelineEvent], snapshot: SnapshotAssertion
) -> None:
    """Snapshot the serialized payloads for all representative timeline events."""
    assert {
        str(event.id): build_event_payload(222527, event) for event in timeline_events
    } == snapshot
