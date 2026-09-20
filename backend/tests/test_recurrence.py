import pytest

from app.schemas import RoutineIn


def rule_input(rule, **changes):
    return {**{key: rule[key] for key in RoutineIn.model_fields if key in rule}, **changes}


def occurrences(client, rule):
    tasks = client.get("/api/tasks").json()
    return sorted((t for t in tasks if t["routine_id"] == rule["id"]), key=lambda task: task["occurrence_date"])


@pytest.mark.parametrize("rule,expected", [
    ({"frequency": "daily", "end_date": "2026-09-24"}, ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24"]),
    ({"frequency": "every_n_days", "interval": 3, "end_date": "2026-09-28"}, ["2026-09-21", "2026-09-24", "2026-09-27"]),
    ({"frequency": "weekly", "interval": 2, "end_date": "2026-10-19"}, ["2026-09-21", "2026-10-05", "2026-10-19"]),
    ({"frequency": "weekdays", "weekdays": [0, 2, 4], "interval": 2, "end_date": "2026-10-05"}, ["2026-09-21", "2026-09-23", "2026-09-25", "2026-10-05"]),
    ({"frequency": "custom", "interval": 4, "interval_unit": "days", "end_date": "2026-09-30"}, ["2026-09-21", "2026-09-25", "2026-09-29"]),
    ({"frequency": "custom", "interval": 2, "interval_unit": "weeks", "end_date": "2026-10-06"}, ["2026-09-21", "2026-10-05"]),
])
def test_recurrence_boundaries_sequence_and_idempotence(client, create, rule, expected):
    routine = create("routines", name="Item {n} on {date}", start_date="2026-09-21", **rule)
    tasks = occurrences(client, routine)
    assert [task["date"] for task in tasks] == expected
    assert [task["sequence_number"] for task in tasks] == list(range(1, len(expected) + 1))
    assert tasks[-1]["title"] == f"Item {len(expected)} on {expected[-1]}"
    assert client.post("/api/scheduler/sync", json={}).json() == {"created": 0}
    client.get("/api/bootstrap")
    assert [task["id"] for task in occurrences(client, routine)] == [task["id"] for task in tasks]


def test_weekday_sequence_when_rule_starts_midweek(client, create):
    rule = create("routines", name="Session {n}", frequency="weekdays", weekdays=[4, 0, 2, 2], interval=2,
                  start_date="2026-09-23", end_date="2026-10-09")
    tasks = occurrences(client, rule)
    assert rule["weekdays"] == [0, 2, 4]
    assert [t["date"] for t in tasks] == ["2026-09-23", "2026-09-25", "2026-10-05", "2026-10-07", "2026-10-09"]
    assert [t["title"] for t in tasks] == [f"Session {i}" for i in range(1, 6)]


def test_deleted_and_rescheduled_occurrences_never_duplicate(client, create, action):
    rule = create("routines", name="Daily", start_date="2026-09-21", end_date="2026-09-23")
    first, second, third = occurrences(client, rule)
    assert client.delete(f"/api/tasks/{first['id']}?version={first['version']}").status_code == 200
    moved = action(second, "reschedule", date="2026-09-23")
    assert moved["occurrence_date"] == "2026-09-22" and moved["is_exception"] is True
    assert client.post("/api/scheduler/sync", json={}).json()["created"] == 0
    tasks = occurrences(client, rule)
    assert len(tasks) == 2 and {t["id"] for t in tasks} == {second["id"], third["id"]}
    assert all(t["date"] == "2026-09-23" for t in tasks)


def test_offset_dependency_links_previous_occurrence_and_survives_rescheduling(client, create, action):
    lecture = create("routines", name="Lecture {n}", start_date="2026-09-21", end_date="2026-09-23")
    assignment = create("routines", name="Assignment {n}", start_date="2026-09-22", end_date="2026-09-23",
                        depends_on_routine_id=lecture["id"], offset_days=1)
    lectures, assignments = occurrences(client, lecture), occurrences(client, assignment)
    assert assignments[0]["depends_on_task_id"] == lectures[0]["id"]
    assert assignments[1]["depends_on_task_id"] == lectures[1]["id"]
    assert assignments[0]["blocked"] is True
    moved = action(lectures[0], "reschedule", date="2026-09-22")
    assert client.post(f"/api/tasks/{assignments[0]['id']}/actions", json={"action": "complete", "version": assignments[0]["version"]}).status_code == 409
    action(moved, "complete")
    assert action(assignments[0], "complete")["status"] == "completed"


def test_missing_predecessor_stays_visible_and_blocked(client, create):
    parent = create("routines", name="Parent", start_date="2026-09-21", end_date="2026-09-21")
    child = create("routines", name="Child", start_date="2026-09-21", end_date="2026-09-21",
                   depends_on_routine_id=parent["id"], offset_days=1)
    task = occurrences(client, child)[0]
    assert task["depends_on_task_id"] is None and task["blocked"] is True
    assert task["blocked_reason"]
    assert client.post(f"/api/tasks/{task['id']}/actions", json={"action": "complete", "version": task["version"]}).status_code == 409


def test_routine_cycle_is_rejected_and_original_rule_preserved(client, create):
    first = create("routines", name="First", start_date="2026-09-21", end_date="2026-09-22")
    second = create("routines", name="Second", start_date="2026-09-21", end_date="2026-09-22", depends_on_routine_id=first["id"])
    assert client.put(f"/api/routines/{first['id']}", json=rule_input(first, depends_on_routine_id=second["id"])).status_code == 422
    assert client.delete(f"/api/routines/{first['id']}").status_code == 409
    assert next(r for r in client.get("/api/routines").json() if r["id"] == first["id"])["depends_on_routine_id"] is None


def test_mixed_manual_and_routine_dependency_cycle_rolls_back(client, create):
    first = create("routines", name="A", start_date="2026-09-22", end_date="2026-09-22")
    second = create("routines", name="B", start_date="2026-09-22", end_date="2026-09-22")
    a, b = occurrences(client, first)[0], occurrences(client, second)[0]
    response = client.put(f"/api/tasks/{a['id']}", json={"title": "A", "date": a["date"], "version": a["version"], "depends_on_task_id": b["id"]})
    assert response.status_code == 200
    response = client.put(f"/api/routines/{second['id']}", json=rule_input(second, depends_on_routine_id=first["id"]))
    assert response.status_code == 422
    assert client.get(f"/api/tasks/{b['id']}").json()["depends_on_task_id"] is None
    assert next(r for r in client.get("/api/routines").json() if r["id"] == second["id"])["version"] == second["version"]


def test_rule_edit_updates_only_untouched_future(client, create, action):
    rule = create("routines", name="Original {n}", start_date="2026-09-21", end_date="2026-09-24", preferred_time="09:00")
    current, completed, edited, untouched = occurrences(client, rule)
    action(completed, "complete")
    response = client.put(f"/api/tasks/{edited['id']}", json={"title": "Personal override", "date": edited["date"], "version": edited["version"]})
    assert response.status_code == 200
    response = client.put(f"/api/routines/{rule['id']}", json=rule_input(rule, name="Changed {n}", preferred_time="10:00"))
    assert response.status_code == 200
    tasks = {t["id"]: t for t in occurrences(client, rule)}
    assert tasks[current["id"]]["title"] == "Original 1" and tasks[current["id"]]["start_time"] == "09:00"
    assert tasks[completed["id"]]["title"] == "Original 2" and tasks[completed["id"]]["status"] == "completed"
    assert tasks[edited["id"]]["title"] == "Personal override"
    assert tasks[untouched["id"]]["title"] == "Changed 4" and tasks[untouched["id"]]["start_time"] == "10:00"
    assert client.put(f"/api/routines/{rule['id']}", json=rule_input(rule, name="Stale")).status_code == 409


def test_rule_weekday_edit_adds_future_days_without_reinterpreting_history(client, create):
    rule = create("routines", name="Weekly", frequency="weekly", start_date="2026-09-07", end_date="2026-10-05")
    old = {t["date"]: t for t in occurrences(client, rule)}
    response = client.put(f"/api/routines/{rule['id']}", json=rule_input(rule, frequency="weekdays", weekdays=[1]))
    assert response.status_code == 200
    tasks = {t["occurrence_date"]: t for t in occurrences(client, rule)}
    assert "2026-09-08" not in tasks and "2026-09-15" not in tasks
    for day in ("2026-09-07", "2026-09-14", "2026-09-21"):
        assert tasks[day]["id"] == old[day]["id"] and tasks[day]["stored_status"] == "pending"
    assert tasks["2026-09-22"]["stored_status"] == "pending"
    assert tasks["2026-09-29"]["stored_status"] == "pending"
    assert tasks["2026-09-28"]["status"] == "cancelled"
    assert client.post("/api/scheduler/sync", json={}).json()["created"] == 0


def test_paused_rule_does_not_catch_up_paused_days_on_resume(client, create, clock):
    rule = create("routines", name="Daily", start_date="2026-09-21", end_date="2026-10-31")
    response = client.put(f"/api/routines/{rule['id']}", json=rule_input(rule, active=False))
    assert response.status_code == 200
    paused = response.json()
    clock.set("2026-10-25T04:00:00+00:00")
    assert client.post("/api/scheduler/sync", json={}).json()["created"] == 0
    response = client.put(f"/api/routines/{rule['id']}", json=rule_input(paused, active=True))
    assert response.status_code == 200
    tasks = {t["date"]: t for t in occurrences(client, rule)}
    assert not any(day in tasks for day in ("2026-10-22", "2026-10-23", "2026-10-24"))
    assert tasks["2026-10-21"]["status"] == "cancelled"
    assert tasks["2026-10-25"]["status"] == "pending"


def test_scheduler_catches_up_after_offline_and_limits_future_horizon(client, create, clock):
    rule = create("routines", name="Daily", start_date="2026-09-21")
    assert len(occurrences(client, rule)) == 31
    clock.set("2026-11-01T04:00:00+00:00")
    response = client.post("/api/scheduler/sync", json={})
    assert response.status_code == 200 and response.json()["created"] == 41
    tasks = occurrences(client, rule)
    assert len(tasks) == 72
    assert next(t for t in tasks if t["date"] == "2026-10-31")["status"] == "overdue"
    assert client.post("/api/scheduler/sync", json={"end": "2027-11-03"}).status_code == 422
    assert client.post("/api/scheduler/sync", json={"start": "2026-11-05", "end": "2026-11-02"}).status_code == 422


@pytest.mark.parametrize("changes", [
    {"interval": 0}, {"frequency": "weekdays", "weekdays": []}, {"weekdays": [7]},
    {"preferred_time": "23:30", "estimated_duration": 60}, {"end_date": "2026-09-20"},
])
def test_invalid_rules_are_rejected_before_generating_tasks(client, changes):
    response = client.post("/api/routines", json={"name": "Invalid", "start_date": "2026-09-21", **changes})
    assert response.status_code == 422
    assert client.get("/api/tasks").json() == []


def test_distant_calendar_window_does_not_skip_intervening_occurrences(client, create, clock):
    rule = create("routines", name="Daily", start_date="2026-09-21")
    original_watermark = rule["materialized_through"]
    response = client.get("/api/calendar?start=2030-01-01&end=2030-01-04")
    assert response.status_code == 200
    assert len(response.json()) == 3
    saved_rule = client.get("/api/routines").json()[0]
    assert saved_rule["materialized_through"] == original_watermark
    clock.set("2026-10-23T04:00:00+00:00")
    assert client.post("/api/scheduler/sync", json={}).status_code == 200
    assert any(t["date"] == "2026-10-22" for t in occurrences(client, rule))


def test_initially_paused_rule_can_be_activated_on_its_start_day(client, create):
    rule = create("routines", name="Paused", start_date="2026-09-21", end_date="2026-09-21", active=False)
    assert occurrences(client, rule) == []
    response = client.put(f"/api/routines/{rule['id']}", json=rule_input(rule, active=True))
    assert response.status_code == 200
    assert [t["date"] for t in occurrences(client, rule)] == ["2026-09-21"]
