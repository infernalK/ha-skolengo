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


def _hw(i, due, done=False):
    return {"id": str(i), "dueDateTime": due, "done": done}


def test_upcoming_homework_is_never_pushed_out_by_old_unticked_ones():
    from datetime import date

    from custom_components.skolengo.homework import select_homework_attributes

    old = [_hw(i, f"2026-09-{(i % 28) + 1:02d}T08:00:00Z") for i in range(40)]
    upcoming = [_hw(100, "2026-11-13T08:30:00Z"), _hw(101, "2026-12-07T09:40:00Z")]

    not_done, done = select_homework_attributes(
        old + upcoming, today=date(2026, 11, 13), max_past=30
    )

    assert len(not_done) == 32
    assert [h["id"] for h in not_done[-2:]] == ["100", "101"]
    assert done == []


def test_done_list_is_most_recent_first_and_keeps_upcoming():
    from datetime import date

    from custom_components.skolengo.homework import select_homework_attributes

    items = [
        _hw(1, "2026-10-01T08:00:00Z", True),
        _hw(2, "2026-11-12T08:00:00Z", True),
        _hw(3, "2026-11-20T08:00:00Z", True),
    ]
    _, done = select_homework_attributes(items, today=date(2026, 11, 13), max_past=1)

    assert [h["id"] for h in done] == ["3", "2"]
