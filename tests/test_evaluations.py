from custom_components.skolengo.evaluations import apply_skill_level_labels, flatten_evaluations


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


def test_skill_level_enum_code_is_translated_to_french_label():
    # Regression test: `/evaluation-services` can return the raw mastery
    # enum code (e.g. "SATISFACTORY_MASTERY") instead of a human label,
    # which used to leak as-is into the sensor attributes and cards.
    service = _evaluation_service(
        evaluations=[
            {
                "id": "eval-5",
                "evaluationResult": {
                    "mark": None,
                    "nonEvaluationReason": None,
                    "subSkillsEvaluationResults": [
                        {
                            "level": "SATISFACTORY_MASTERY",
                            "subSkill": {"shortLabel": "Débat"},
                        }
                    ],
                },
            }
        ]
    )

    [item] = flatten_evaluations([service])

    assert item["skills"] == [{"skill": "Débat", "level": "Maîtrise satisfaisante"}]


def test_teachers_are_extracted_from_evaluation_service():
    service = _evaluation_service(
        teachers=[{"firstName": "Eric", "lastName": "Gisbert"}],
        evaluations=[{"id": "eval-6", "evaluationResult": {"mark": 12, "nonEvaluationReason": None}}],
    )

    [item] = flatten_evaluations([service])

    assert item["teachers"] == ["Eric Gisbert"]


def test_apply_skill_level_labels_prefers_school_configured_label():
    # The school's own `/evaluations-settings` labels take priority over
    # our generic fallback translation in normalize_mastery_level().
    service = _evaluation_service(
        evaluations=[
            {
                "id": "eval-7",
                "evaluationResult": {
                    "mark": None,
                    "nonEvaluationReason": None,
                    "subSkillsEvaluationResults": [
                        {
                            "level": "SATISFACTORY_MASTERY",
                            "subSkill": {"shortLabel": "Débat"},
                        }
                    ],
                },
            }
        ]
    )
    services = [service]

    apply_skill_level_labels(services, {"SATISFACTORY_MASTERY": "Maîtrise correcte"})
    [item] = flatten_evaluations(services)

    assert item["skills"] == [{"skill": "Débat", "level": "Maîtrise correcte"}]


def test_apply_skill_level_labels_falls_back_when_code_unmapped():
    # A code missing from the school's settings (flaky/unsupported school)
    # is left untouched, so flatten_evaluations()'s generic translation
    # still applies -- it must never end up unreadable.
    service = _evaluation_service(
        evaluations=[
            {
                "id": "eval-8",
                "evaluationResult": {
                    "mark": None,
                    "nonEvaluationReason": None,
                    "subSkillsEvaluationResults": [
                        {
                            "level": "SATISFACTORY_MASTERY",
                            "subSkill": {"shortLabel": "Débat"},
                        }
                    ],
                },
            }
        ]
    )
    services = [service]

    apply_skill_level_labels(services, {"VERY_GOOD_MASTERY": "Excellent"})
    [item] = flatten_evaluations(services)

    assert item["skills"] == [{"skill": "Débat", "level": "Maîtrise satisfaisante"}]


def test_period_id_is_tagged_by_coordinator_and_propagated():
    service = _evaluation_service(
        evaluations=[{"id": "eval-5", "evaluationResult": {"mark": 9, "nonEvaluationReason": None}}]
    )
    service["_period_id"] = "period-1"

    [item] = flatten_evaluations([service])

    assert item["period_id"] == "period-1"


def test_empty_input_returns_empty_list():
    assert flatten_evaluations([]) == []
