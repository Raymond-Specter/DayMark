import pytest


DAY = "2026-09-21"


def test_first_open_has_no_seeded_goals_or_tasks(client):
    response = client.get("/api/bootstrap")
    assert response.status_code == 200
    data = response.json()
    assert data["today"] == DAY
    for key in ("goals", "projects", "milestones", "routines", "tasks", "notifications"):
        assert data[key] == []
    stats = client.get("/api/statistics").json()
    assert stats["total_tasks"] == stats["completion_rate"] == stats["actual_minutes"] == 0
    assert client.get("/api/progress").json() == {"goals": [], "standalone_projects": [], "unassigned_tasks": 0}


def test_hierarchy_restricts_deletion_and_mismatched_links(client, create):
    goal = create("goals", name="User supplied goal", color="#aabbcc")
    project = create("projects", name="First", goal_id=goal["id"])
    other = create("projects", name="Second")
    stage = create("milestones", name="Stage", project_id=project["id"])
    assert client.delete(f"/api/goals/{goal['id']}").status_code == 409
    assert client.delete(f"/api/projects/{project['id']}").status_code == 409
    assert client.post("/api/tasks", json={"title": "Wrong project", "project_id": other["id"], "milestone_id": stage["id"]}).status_code == 422
    create("tasks", title="Linked", project_id=project["id"], milestone_id=stage["id"])
    assert client.delete(f"/api/milestones/{stage['id']}").status_code == 409
    assert client.put(f"/api/milestones/{stage['id']}", json={"name": "Stage", "project_id": other["id"]}).status_code == 409
    assert client.get("/api/milestones").json()[0]["project_id"] == project["id"]


def test_empty_hierarchy_can_be_deleted_from_leaves(client, create):
    goal = create("goals", name="Goal")
    project = create("projects", name="Project", goal_id=goal["id"])
    stage = create("milestones", name="Stage", project_id=project["id"])
    for collection, row in (("milestones", stage), ("projects", project), ("goals", goal)):
        assert client.delete(f"/api/{collection}/{row['id']}").status_code == 200
        assert client.get(f"/api/{collection}").json() == []


@pytest.mark.parametrize("collection,payload", [
    ("goals", {"name": "", "priority": 2}),
    ("goals", {"name": "Bad date", "start_date": "2026-02-30"}),
    ("goals", {"name": "Reversed", "start_date": "2026-09-22", "target_date": DAY}),
    ("projects", {"name": "Reversed", "start_date": "2026-09-22", "end_date": DAY}),
    ("tasks", {"title": "No date", "start_time": "09:00"}),
    ("tasks", {"title": "No start", "date": DAY, "end_time": "10:00"}),
    ("tasks", {"title": "Backwards", "date": DAY, "start_time": "10:00", "end_time": "09:00"}),
    ("tasks", {"title": "Bad clock", "date": DAY, "start_time": "25:00"}),
    ("tasks", {"title": "Naive deadline", "deadline": "2026-09-22T10:00:00"}),
    ("tasks", {"title": "No anchor", "reminder": 10}),
    ("tasks", {"title": "Bad priority", "priority": 4}),
    ("tasks", {"title": "Numeric date", "date": 20260921}),
    ("tasks", {"title": "Implicit cross midnight", "date": DAY, "start_time": "23:30", "estimated_duration": 120}),
])
def test_rejects_invalid_user_input(client, collection, payload):
    response = client.post(f"/api/{collection}", json=payload)
    assert response.status_code == 422, response.text
    assert client.get(f"/api/{collection}").json() == []


def test_missing_foreign_keys_return_not_found(client):
    assert client.post("/api/projects", json={"name": "Missing", "goal_id": "missing"}).status_code == 404
    assert client.post("/api/milestones", json={"name": "Missing", "project_id": "missing"}).status_code == 404
    assert client.post("/api/tasks", json={"title": "Missing", "depends_on_task_id": "missing"}).status_code == 404


def test_task_completion_reopening_and_stale_versions(client, create, action):
    task = create("tasks", title="Read", date=DAY, start_time="13:00", end_time="14:00", estimated_duration=5)
    assert task["estimated_duration"] == 60
    done = action(task, "complete")
    assert done["status"] == "completed" and done["completed_at"] == "2026-09-21T04:00:00+00:00"
    assert done["version"] == task["version"] + 1
    stale = client.post(f"/api/tasks/{task['id']}/actions", json={"action": "reopen", "version": task["version"]})
    assert stale.status_code == 409
    events = client.get(f"/api/calendar?start={DAY}&end=2026-09-22").json()
    assert len(events) == 1 and events[0]["classNames"] == ["task-completed"]
    reopened = action(done, "reopen")
    assert reopened["status"] == "pending" and reopened["completed_at"] is None
    assert len(client.get(f"/api/tasks/{task['id']}/history").json()) == 3


def test_task_edit_requires_version_and_preserves_calendar_identity(client, create):
    task = create("tasks", title="First", date=DAY, start_time="13:00", end_time="14:00")
    original = client.get(f"/api/calendar?start={DAY}&end=2026-09-23").json()[0]
    payload = {"title": "Moved", "date": "2026-09-22", "start_time": "15:00", "end_time": "16:30"}
    assert client.put(f"/api/tasks/{task['id']}", json=payload).status_code == 422
    changed = client.put(f"/api/tasks/{task['id']}", json={**payload, "version": task["version"]})
    assert changed.status_code == 200
    assert changed.json()["status"] == "rescheduled"
    assert changed.json()["estimated_duration"] == 90
    events = client.get(f"/api/calendar?start={DAY}&end=2026-09-23").json()
    assert len(events) == 1 and events[0]["id"] == original["id"]
    assert events[0]["start"] == "2026-09-22T15:00:00"
    assert events[0]["title"] == "Moved"
    assert client.put(f"/api/tasks/{task['id']}", json={**payload, "version": task["version"]}).status_code == 409


def test_carryover_is_explicit_and_reschedule_keeps_history(client, create, action):
    yesterday = create("tasks", title="Yesterday", date="2026-09-20", start_time="09:00", end_time="10:00")
    older = create("tasks", title="Earlier", date="2026-09-19")
    cancelled = action(create("tasks", title="Cancelled", date="2026-09-20"), "cancel")
    data = client.get("/api/today").json()
    assert [t["id"] for t in data["unfinished_yesterday"]] == [yesterday["id"]]
    assert [t["id"] for t in data["overdue"]] == [older["id"]]
    assert data["unfinished_yesterday"][0]["status"] == "overdue"
    assert client.get(f"/api/tasks/{yesterday['id']}").json()["date"] == "2026-09-20"
    kept = action(older, "keep_overdue")
    assert kept["status"] == "overdue" and kept["date"] == older["date"]
    moved = action(yesterday, "reschedule", date=DAY, start_time="10:00", end_time="11:30")
    assert moved["status"] == "rescheduled" and moved["start_time"] == "10:00"
    assert moved["estimated_duration"] == 90
    history = client.get(f"/api/tasks/{yesterday['id']}/history").json()
    record = next(h for h in history if h["action"] == "reschedule")
    assert record["before"]["date"] == "2026-09-20" and record["after"]["date"] == DAY
    assert client.get("/api/today").json()["unfinished_yesterday"] == []
    assert client.get(f"/api/tasks/{cancelled['id']}").json()["status"] == "cancelled"


def test_today_sorts_by_time_then_user_priority(client, create):
    late = create("tasks", title="Later high priority", date=DAY, start_time="15:00", priority=1)
    low = create("tasks", title="Morning low", date=DAY, start_time="09:00", priority=3)
    high = create("tasks", title="Morning high", date=DAY, start_time="09:00", priority=1)
    flexible = create("tasks", title="Flexible", date=DAY, priority=1)
    assert [t["id"] for t in client.get("/api/today").json()["tasks"]] == [high["id"], low["id"], late["id"], flexible["id"]]


def test_dependencies_block_completion_cycles_and_parent_removal(client, create, action):
    first = create("tasks", title="First")
    second = create("tasks", title="Second", depends_on_task_id=first["id"])
    assert second["blocked"] is True
    assert client.post(f"/api/tasks/{second['id']}/actions", json={"action": "complete", "version": second["version"]}).status_code == 409
    assert client.put(f"/api/tasks/{first['id']}", json={"title": "First", "depends_on_task_id": second["id"], "version": first["version"]}).status_code == 422
    assert client.put(f"/api/tasks/{first['id']}", json={"title": "First", "depends_on_task_id": first["id"], "version": first["version"]}).status_code == 422
    assert client.delete(f"/api/tasks/{first['id']}?version={first['version']}").status_code == 409
    first = action(first, "complete")
    second = action(second, "complete")
    assert second["blocked"] is False
    assert client.post(f"/api/tasks/{first['id']}/actions", json={"action": "reopen", "version": first["version"]}).status_code == 409
    action(second, "reopen")
    assert action(first, "reopen")["status"] == "pending"


def test_calendar_standalone_events_overlap_and_linked_events_are_guarded(client, create):
    create("tasks", title="All day", date=DAY)
    event = create("events", title="Crosses midnight", start="2026-09-20T23:00:00", end="2026-09-21T01:00:00")
    events = client.get(f"/api/calendar?start={DAY}&end=2026-09-22").json()
    assert len(events) == 2
    linked = next(e for e in events if e["extendedProps"]["task_id"])
    assert linked["allDay"] is True and linked["end"] == "2026-09-22"
    assert client.delete(f"/api/events/{linked['id']}").status_code == 409
    assert client.put(f"/api/events/{linked['id']}", json={"title": "Changed", "start": DAY, "end": "2026-09-22", "all_day": True}).status_code == 409
    assert client.delete(f"/api/events/{event['id']}").status_code == 200
    assert len(client.get(f"/api/calendar?start={DAY}&end=2026-09-22").json()) == 1
    assert client.get(f"/api/calendar?start={DAY}&end={DAY}").status_code == 422


def test_soft_delete_hides_task_and_calendar_but_preserves_export(client, create):
    task = create("tasks", title="Remove", date=DAY)
    assert client.delete(f"/api/tasks/{task['id']}?version={task['version']}").status_code == 200
    assert client.get("/api/tasks").json() == []
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404
    assert client.get(f"/api/calendar?start={DAY}&end=2026-09-22").json() == []
    backup = client.get("/api/export").json()
    assert backup["tables"]["tasks"][0]["deleted_at"] is not None
    assert {entry["action"] for entry in backup["tables"]["task_history"]} == {"created", "deleted"}


def test_external_browser_origin_cannot_mutate(client):
    assert client.post("/api/goals", json={"name": "Unauthorized"}, headers={"origin": "https://unrelated.example"}).status_code == 403
    assert client.post("/api/goals", json={"name": "Local"}, headers={"origin": "http://localhost:3000"}).status_code == 201
