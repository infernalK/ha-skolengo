from datetime import datetime, timezone

from custom_components.skolengo.coordinator import (
    SOURCE_AGENDA,
    SOURCE_HOMEWORK,
    SkolengoData,
    SourceFreshness,
)


def test_sources_are_fresh_by_default():
    data = SkolengoData()
    assert data.is_fresh(SOURCE_AGENDA)
    assert data.last_update(SOURCE_AGENDA) is None


def test_failed_source_is_flagged_with_its_last_success():
    last = datetime(2026, 10, 6, 8, 0, tzinfo=timezone.utc)
    data = SkolengoData(
        freshness={
            SOURCE_AGENDA: SourceFreshness(ok=False, last_update=last),
            SOURCE_HOMEWORK: SourceFreshness(ok=True, last_update=last),
        }
    )
    assert not data.is_fresh(SOURCE_AGENDA)
    assert data.last_update(SOURCE_AGENDA) == last
    assert data.is_fresh(SOURCE_HOMEWORK)
