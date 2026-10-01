import pytest

from custom_components.skolengo.api import (
    ABSENCE_TYPES,
    SkolengoApiError,
    SkolengoClient,
)


def _client(handler):
    client = object.__new__(SkolengoClient)
    client._request = handler  # noqa: SLF001
    return client


def _doc(file_id, absence_type):
    return {
        "data": [
            {
                "id": file_id,
                "type": "absenceFile",
                "relationships": {"currentState": {"data": {"type": "absenceState", "id": f"s-{file_id}"}}},
            }
        ],
        "included": [
            {"id": f"s-{file_id}", "type": "absenceState", "attributes": {"absenceType": absence_type}}
        ],
    }


def test_queries_each_absence_type_and_merges_results():
    seen = []

    def handler(method, path, params=None):
        seen.append(params["filter[currentState.absenceType]"])
        assert path == "/absence-files"
        return _doc(f"f-{params['filter[currentState.absenceType]']}", params["filter[currentState.absenceType]"])

    result = _client(handler).get_absences("stu-1")

    assert seen == list(ABSENCE_TYPES)
    assert [a["currentState"]["absenceType"] for a in result] == list(ABSENCE_TYPES)


def test_skips_a_failing_type_but_keeps_the_others():
    def handler(method, path, params=None):
        absence_type = params["filter[currentState.absenceType]"]
        if absence_type == "LATENESS":
            raise SkolengoApiError("boom")
        return _doc(f"f-{absence_type}", absence_type)

    result = _client(handler).get_absences("stu-1")

    assert {a["currentState"]["absenceType"] for a in result} == {"ABSENCE", "EXEMPTION", "DEPARTURE"}


def test_raises_when_every_type_fails():
    def handler(method, path, params=None):
        raise SkolengoApiError("boom")

    with pytest.raises(SkolengoApiError):
        _client(handler).get_absences("stu-1")
