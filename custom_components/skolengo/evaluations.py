"""Shared helpers for flattening Skolengo evaluation-service payloads.

Split out from `sensor.py` so `coordinator.py` can also flatten evaluations
(to detect new grades and fire events) without a circular import.
"""
from __future__ import annotations

from .colors import normalize_color


def flatten_evaluations(evaluation_services: list[dict]) -> list[dict]:
    """Flatten evaluation-services -> evaluations into one list.

    Skolengo doesn't separate "grades" (numeric) from "evaluations"
    (skill-based) the way Pronote does: a single `evaluation` resource
    can carry either a numeric `mark` or a set of skill levels,
    depending on the school's grading system, so both are surfaced
    here under one unified list.
    """
    items: list[dict] = []
    for evaluation_service in evaluation_services:
        subject = evaluation_service.get("subject") or {}
        subject_student_average = evaluation_service.get("studentAverage")
        subject_class_average = evaluation_service.get("average")
        subject_coefficient = evaluation_service.get("coefficient")
        for evaluation in evaluation_service.get("evaluations") or []:
            # The API doc names this relationship "evaluationResult"
            # (singular), but it can still resolve to a list of result
            # records -- normalize either shape.
            result_data = evaluation.get("evaluationResult")
            if result_data is None:
                results = evaluation.get("evaluationResults") or []
            elif isinstance(result_data, list):
                results = result_data
            else:
                results = [result_data]

            mark = None
            skills = []
            for result in results:
                if result.get("nonEvaluated") is not True and isinstance(
                    result.get("value"), (int, float)
                ):
                    mark = float(result["value"])
                for skill_result in result.get("subSkillsEvaluationResults") or []:
                    level = skill_result.get("level")
                    skill = (skill_result.get("subSkill") or {}).get("shortLabel")
                    if level or skill:
                        skills.append({"skill": skill, "level": level})
            items.append(
                {
                    "id": evaluation.get("id"),
                    "subject": subject.get("label"),
                    "subject_color": normalize_color(subject.get("color")),
                    "title": evaluation.get("title") or evaluation.get("topic"),
                    "date": evaluation.get("dateTime"),
                    "mark": mark,
                    "scale": evaluation.get("scale"),
                    "coefficient": evaluation.get("coefficient"),
                    "class_average": evaluation.get("average"),
                    "skills": skills,
                    # Skolengo's own officially-computed average for this
                    # subject over the period (coefficient-weighted by the
                    # school, not by us) -- see `_official_average()` in
                    # sensor.py.
                    "subject_student_average": subject_student_average,
                    "subject_class_average": subject_class_average,
                    "subject_coefficient": subject_coefficient,
                    # Tagged by the coordinator (one fetch per period) so
                    # the sensors/cards can offer a per-period breakdown.
                    "period_id": evaluation_service.get("_period_id"),
                }
            )
    return items
