"""Shared helpers for flattening Skolengo evaluation-service payloads.

Split out from `sensor.py` so `coordinator.py` can also flatten evaluations
(to detect new grades and fire events) without a circular import.
"""
from __future__ import annotations

from .colors import normalize_color, normalize_mastery_level


def _iter_evaluation_results(evaluation: dict) -> list[dict]:
    """Normalize `evaluation.evaluationResult(s)` to a flat list.

    The API doc names this relationship "evaluationResult" (singular),
    but it can still resolve to a list of result records.
    """
    result_data = evaluation.get("evaluationResult")
    if result_data is None:
        return evaluation.get("evaluationResults") or []
    if isinstance(result_data, list):
        return result_data
    return [result_data]


def apply_skill_level_labels(evaluation_services: list[dict], level_labels: dict[str, str]) -> None:
    """Replace raw skill mastery-level codes with the school's own labels.

    `/evaluations-settings` -> `skillsSetting.skillAcquisitionLevels` carries
    the establishment's own configured label for each level code (schools
    can and do customize the wording), which is more accurate than our
    generic fallback translation in `normalize_mastery_level()`. Mutates
    `evaluation_services` in place so both `flatten_evaluations()` call
    sites (coordinator event-diffing and sensor display) pick it up.
    Codes not present in `level_labels` (e.g. the settings fetch failed or
    is flaky for this school) are left untouched, so `flatten_evaluations()`
    still falls back to the generic translation for them.
    """
    if not level_labels:
        return
    for evaluation_service in evaluation_services:
        for evaluation in evaluation_service.get("evaluations") or []:
            for result in _iter_evaluation_results(evaluation):
                for skill_result in result.get("subSkillsEvaluationResults") or []:
                    level = skill_result.get("level")
                    if level in level_labels:
                        skill_result["level"] = level_labels[level]


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
        teachers = [
            f"{t.get('firstName', '')} {t.get('lastName', '')}".strip()
            for t in (evaluation_service.get("teachers") or [])
        ]
        for evaluation in evaluation_service.get("evaluations") or []:
            mark = None
            skills = []
            for result in _iter_evaluation_results(evaluation):
                if result.get("nonEvaluationReason") is None and isinstance(
                    result.get("mark"), (int, float)
                ):
                    mark = float(result["mark"])
                for skill_result in result.get("subSkillsEvaluationResults") or []:
                    level = normalize_mastery_level(skill_result.get("level"))
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
                    "teachers": teachers,
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
