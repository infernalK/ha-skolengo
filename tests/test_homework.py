from custom_components.skolengo.homework import flatten_homework


def test_flattens_subject_teacher_and_color():
    hw = {
        "id": "hw-1",
        "subject": {"label": "Histoire", "color": "#123ABC"},
        "dueDate": "2026-09-15",
        "done": False,
        "title": "Lire le chapitre 4",
        "html": "<p>Lire le chapitre 4</p>",
        "teacher": {"firstName": "Jean", "lastName": "Dupont"},
    }

    result = flatten_homework(hw)

    assert result == {
        "id": "hw-1",
        "subject": "Histoire",
        "subject_color": "#123ABC",
        "due_date": "2026-09-15",
        "done": False,
        "title": "Lire le chapitre 4",
        "html": "<p>Lire le chapitre 4</p>",
        "teacher": "Jean Dupont",
    }


def test_falls_back_to_due_date_time_when_due_date_absent():
    hw = {"id": "hw-2", "dueDateTime": "2026-09-16T00:00:00Z"}

    result = flatten_homework(hw)

    assert result["due_date"] == "2026-09-16T00:00:00Z"


def test_missing_teacher_and_subject_are_none():
    hw = {"id": "hw-3", "done": True}

    result = flatten_homework(hw)

    assert result["subject"] is None
    assert result["teacher"] is None
    assert result["done"] is True


def test_teacher_with_only_one_name_part_is_not_blank():
    hw = {"id": "hw-4", "teacher": {"lastName": "Martin"}}

    result = flatten_homework(hw)

    assert result["teacher"] == "Martin"
