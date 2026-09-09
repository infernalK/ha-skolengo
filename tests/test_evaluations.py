from custom_components.skolengo.evaluations import flatten_evaluations


def _evaluation_service(**overrides):
    base = {
        "subject": {"label": "Mathématiques", "color": "57006D"},
        "studentAverage": 15.2,
        "average": 12.8,
        "coefficient": 2,
        "evaluations": [],
    }
    base.update(overrides)
    return base


def test_numeric_mark_is_extracted():
    # Regression test for the "Non noté" bug (commit dd8a3c8): a real,
    # evaluated grade is shaped as evaluationResult.mark with
    # nonEvaluationReason == None -- not evaluationResult.value /
    # nonEvaluated as an earlier version of this parser assumed.
    service = _evaluation_service(
        evaluations=[
            {
                "id": "eval-1",
                "title": "Contrôle chapitre 3",
                "dateTime": "2026-09-01T00:00:00Z",
                "scale": 20,
                "coefficient": 1,
                "average": 11.4,
                "evaluationResult": {"mark": 20, "nonEvaluationReason": None},
            }
        ]
    )

    [item] = flatten_evaluations([service])

    assert item["mark"] == 20.0
    assert item["subject"] == "Mathématiques"
    assert item["subject_color"] == "#57006D"


def test_non_evaluated_result_has_no_mark():
    service = _evaluation_service(
        evaluations=[
            {
                "id": "eval-2",
                "title": "Absent",
                "evaluationResult": {"mark": None, "nonEvaluationReason": "ABSENT"},
            }
        ]
    )

    [item] = flatten_evaluations([service])

    assert item["mark"] is None


def test_evaluation_result_as_list_is_supported():
    service = _evaluation_service(
        evaluations=[
            {
                "id": "eval-3",
                "evaluationResults": [
                    {"mark": 14, "nonEvaluationReason": None},
                ],
            }
        ]
    )

    [item] = flatten_evaluations([service])

    assert item["mark"] == 14.0


def test_skill_based_evaluation_collects_levels():
    service = _evaluation_service(
        evaluations=[
            {
                "id": "eval-4",
                "evaluationResult": {
                    "mark": None,
                    "nonEvaluationReason": None,
                    "subSkillsEvaluationResults": [
                        {
                            "level": "Acquis",
                            "subSkill": {"shortLabel": "Rédaction"},
                        }
                    ],
                },
            }
        ]
    )

    [item] = flatten_evaluations([service])

    assert item["mark"] is None
    assert item["skills"] == [{"skill": "Rédaction", "level": "Acquis"}]


def test_period_id_is_tagged_by_coordinator_and_propagated():
    service = _evaluation_service(
        evaluations=[{"id": "eval-5", "evaluationResult": {"mark": 9, "nonEvaluationReason": None}}]
    )
    service["_period_id"] = "period-1"

    [item] = flatten_evaluations([service])

    assert item["period_id"] == "period-1"


def test_empty_input_returns_empty_list():
    assert flatten_evaluations([]) == []
