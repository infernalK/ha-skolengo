from custom_components.skolengo.api import SkolengoClient, jsonapi_deserialize
from custom_components.skolengo.school_life import flatten_schooling_events

# Shape of a real /schooling-events-wrappers response (names/ids anonymised).
DOC = {
    "data": [
        {
            "id": "stu-1",
            "type": "schoolingEventWrapper",
            "attributes": {"positiveObservations": 0, "negativeObservations": 2, "punishmentsToRealize": None},
            "relationships": {
                "punishments": {"data": []},
                "observations": {"data": [{"id": "1", "type": "observation"}, {"id": "2", "type": "observation"}]},
            },
        }
    ],
    "included": [
        {
            "id": "1",
            "type": "observation",
            "attributes": {"eventDateTime": "2026-09-29T10:08:00Z", "comment": "Leçon non apprise"},
            "relationships": {
                "reason": {"data": {"id": "8", "type": "observationReason"}},
                "issuer": {"data": {"id": "t1", "type": "teacher"}},
            },
        },
        {
            "id": "2",
            "type": "observation",
            "attributes": {"eventDateTime": "2026-09-21T19:45:00Z", "comment": "Rappel"},
            "relationships": {
                "reason": {"data": {"id": "8", "type": "observationReason"}},
                "issuer": {"data": {"id": "t2", "type": "teacher"}},
            },
        },
        {"id": "8", "type": "observationReason", "attributes": {"longLabel": "Travail non fait", "tone": "NEGATIVE"}},
        {"id": "t1", "type": "teacher", "attributes": {"title": "Mme", "firstName": "ANNE", "lastName": "ROQUE"}},
        {"id": "t2", "type": "teacher", "attributes": {"title": "Mme", "firstName": "STEPHANIE", "lastName": "VAGNER"}},
    ],
}


def test_flattens_observations_newest_first():
    wrapper = jsonapi_deserialize(DOC)[0]

    life = flatten_schooling_events(wrapper)

    assert (life["positive"], life["negative"]) == (0, 2)
    assert life["punishments"] == []
    assert [o["date"] for o in life["observations"]] == ["2026-09-29T10:08:00Z", "2026-09-21T19:45:00Z"]
    first = life["observations"][0]
    assert first["reason"] == "Travail non fait"
    assert first["tone"] == "NEGATIVE"
    assert first["issuer"] == "Mme ANNE ROQUE"
    assert first["comment"] == "Leçon non apprise"


def test_counters_fall_back_to_list_when_null():
    wrapper = jsonapi_deserialize(DOC)[0]
    wrapper["positiveObservations"] = None
    wrapper["negativeObservations"] = None

    life = flatten_schooling_events(wrapper)

    assert (life["positive"], life["negative"]) == (0, 2)


def test_empty_wrapper_is_safe():
    life = flatten_schooling_events({})

    assert life["observations"] == [] and life["punishments"] == []
    assert (life["positive"], life["negative"]) == (0, 0)


def test_punishment_uses_first_available_date_field():
    life = flatten_schooling_events(
        {
            "punishments": [
                {
                    "id": "p1",
                    "dueDateTime": "2026-10-05T00:00:00Z",
                    "reason": {"longLabel": "Bavardages"},
                    "category": {"longLabel": "Retenue"},
                    "issuer": {"firstName": "A", "lastName": "B"},
                }
            ]
        }
    )

    punishment = life["punishments"][0]
    assert punishment["date"] == "2026-10-05T00:00:00Z"
    assert (punishment["reason"], punishment["category"], punishment["issuer"]) == ("Bavardages", "Retenue", "A B")


def test_get_schooling_events_returns_first_wrapper():
    client = object.__new__(SkolengoClient)
    client._request = lambda method, path, params=None: DOC  # noqa: SLF001

    assert client.get_schooling_events("stu-1")["id"] == "stu-1"
