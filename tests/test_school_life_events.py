from types import SimpleNamespace

from custom_components.skolengo.const import (
    EVENT_SKOLENGO,
    EVENT_TYPE_NEW_ABSENCE,
    EVENT_TYPE_NEW_DELAY,
    EVENT_TYPE_NEW_OBSERVATION,
    EVENT_TYPE_NEW_PUNISHMENT,
)
from custom_components.skolengo.coordinator import (
    SkolengoData,
    SkolengoDataUpdateCoordinator,
)


def _coordinator():
    coordinator = object.__new__(SkolengoDataUpdateCoordinator)
    fired = []
    coordinator.hass = SimpleNamespace(bus=SimpleNamespace(async_fire=lambda name, data: fired.append((name, data))))
    coordinator.entry = SimpleNamespace(data={"student_name": "Lilwenn"})
    coordinator._known_school_life_ids = {}  # noqa: SLF001
    return coordinator, fired


def _absence(file_id, absence_type):
    return {"id": file_id, "currentState": {"absenceType": absence_type, "absenceStartDateTime": "2026-09-01T08:00:00Z"}}


def _data(absences=(), observations=(), punishments=(), fetched=True):
    return SkolengoData(
        absences=list(absences),
        absences_fetched=fetched,
        school_life={"observations": list(observations), "punishments": list(punishments)},
    )


def test_nothing_fired_on_first_update_then_new_items_fire():
    coordinator, fired = _coordinator()
    coordinator._async_fire_school_life_events(  # noqa: SLF001
        _data([_absence("a1", "ABSENCE")], [{"id": "o1"}], [{"id": "p1"}])
    )
    assert fired == []

    coordinator._async_fire_school_life_events(  # noqa: SLF001
        _data(
            [_absence("a1", "ABSENCE"), _absence("a2", "ABSENCE"), _absence("l1", "LATENESS")],
            [{"id": "o1"}, {"id": "o2", "reason": "Travail non fait"}],
            [{"id": "p1"}, {"id": "p2"}],
        )
    )

    types = sorted(data["type"] for name, data in fired if name == EVENT_SKOLENGO)
    assert types == sorted(
        [EVENT_TYPE_NEW_ABSENCE, EVENT_TYPE_NEW_DELAY, EVENT_TYPE_NEW_OBSERVATION, EVENT_TYPE_NEW_PUNISHMENT]
    )
    observation = next(d for _, d in fired if d["type"] == EVENT_TYPE_NEW_OBSERVATION)
    assert observation["id"] == "o2" and observation["student_name"] == "Lilwenn"
    assert observation["reason"] == "Travail non fait"
    absence = next(d for _, d in fired if d["type"] == EVENT_TYPE_NEW_ABSENCE)
    assert absence["id"] == "a2" and absence["absence_type"] == "ABSENCE"


def test_failed_absences_fetch_neither_fires_nor_poisons_known_ids():
    coordinator, fired = _coordinator()
    coordinator._async_fire_school_life_events(_data([_absence("a1", "ABSENCE")]))  # noqa: SLF001

    coordinator._async_fire_school_life_events(_data([], fetched=False))  # noqa: SLF001
    coordinator._async_fire_school_life_events(_data([_absence("a1", "ABSENCE")]))  # noqa: SLF001

    assert fired == []


def test_item_dropping_out_then_back_is_not_reported_again():
    coordinator, fired = _coordinator()
    coordinator._async_fire_school_life_events(_data(observations=[{"id": "o1"}]))  # noqa: SLF001
    coordinator._async_fire_school_life_events(_data(observations=[]))  # noqa: SLF001
    coordinator._async_fire_school_life_events(_data(observations=[{"id": "o1"}]))  # noqa: SLF001

    assert fired == []


def test_missing_school_life_data_is_skipped():
    coordinator, fired = _coordinator()
    coordinator._async_fire_school_life_events(SkolengoData(school_life={}))  # noqa: SLF001
    coordinator._async_fire_school_life_events(_data(observations=[{"id": "o1"}]))  # noqa: SLF001

    assert fired == []
