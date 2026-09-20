from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import ReminderJob


DAY = "2026-09-21"


@pytest.mark.parametrize("offset", [0, 10, 30, 60, 1440])
def test_reminder_offsets_and_exact_due_delivery(client, create, session_factory, clock, offset):
    task = create("tasks", title="Remind", date=DAY, start_time="13:00", reminder=offset)
    due = datetime(2026, 9, 21, 5, tzinfo=timezone.utc) - timedelta(minutes=offset)
    with session_factory() as session:
        job = session.scalar(select(ReminderJob).where(ReminderJob.task_id == task["id"]))
        assert job.due_at == due.isoformat()
    clock.set((due - timedelta(seconds=1)).isoformat())
    assert client.post("/api/reminders/dispatch").json() == {"delivered": 0}
    clock.set(due.isoformat())
    assert client.post("/api/reminders/dispatch").json() == {"delivered": 1}
    assert client.post("/api/reminders/dispatch").json() == {"delivered": 0}
    notifications = client.get("/api/notifications").json()
    assert len(notifications) == 1 and notifications[0]["task_id"] == task["id"]


def test_reschedule_and_cancel_invalidate_pending_reminders(client, create, action, clock):
    moved = create("tasks", title="Move", date=DAY, start_time="13:00", reminder=60)
    cancelled = create("tasks", title="Cancel", date=DAY, start_time="13:00", reminder=60)
    moved = action(moved, "reschedule", date="2026-09-22")
    action(cancelled, "cancel")
    assert client.post("/api/reminders/dispatch").json()["delivered"] == 0
    clock.set("2026-09-22T04:00:00+00:00")
    assert client.post("/api/reminders/dispatch").json()["delivered"] == 1
    assert [n["task_id"] for n in client.get("/api/notifications").json()] == [moved["id"]]


def test_already_delivered_reminder_is_not_duplicated_by_task_edit(client, create):
    task = create("tasks", title="Original", date=DAY, start_time="13:00", reminder=60)
    assert client.post("/api/reminders/dispatch").json()["delivered"] == 1
    response = client.put(f"/api/tasks/{task['id']}", json={"title": "Renamed", "date": DAY, "start_time": "13:00", "reminder": 60, "version": task["version"]})
    assert response.status_code == 200
    assert client.post("/api/reminders/dispatch").json()["delivered"] == 0
    client.get("/api/bootstrap")
    notifications = client.get("/api/notifications").json()
    assert len(notifications) == 1
    first_read = client.post(f"/api/notifications/{notifications[0]['id']}/read").json()["read_at"]
    assert first_read is not None
    assert client.post(f"/api/notifications/{notifications[0]['id']}/read").json()["read_at"] == first_read


def test_settings_use_timezone_and_default_clock_and_reschedule_jobs(client, create, session_factory):
    task = create("tasks", title="Flexible reminder", date=DAY, reminder=0)
    with session_factory() as session:
        old = session.scalar(select(ReminderJob).where(ReminderJob.task_id == task["id"]))
        assert old.due_at == "2026-09-21T01:00:00+00:00"
    response = client.put("/api/settings", json={"timezone": "America/Los_Angeles", "day_start": "10:00"})
    assert response.status_code == 200
    assert client.get("/api/today").json()["date"] == "2026-09-20"
    with session_factory() as session:
        jobs = list(session.scalars(select(ReminderJob).where(ReminderJob.task_id == task["id"])))
        assert len(jobs) == 2
        pending = next(job for job in jobs if job.status == "pending")
        assert pending.due_at == "2026-09-21T17:00:00+00:00"
        assert any(job.status == "cancelled" for job in jobs)
    assert client.put("/api/settings", json={"timezone": "Bad/Timezone"}).status_code == 422
    assert client.put("/api/settings", json={"day_start": "24:00"}).status_code == 422


def test_deadline_only_reminder_is_normalized_to_utc(client, create):
    task = create("tasks", title="Deadline", deadline="2026-09-21T13:00:00+08:00", reminder=60)
    assert task["deadline"] == "2026-09-21T05:00:00+00:00"
    assert client.post("/api/reminders/dispatch").json()["delivered"] == 1


def test_daily_review_snapshot_survives_task_changes_and_upsert_does_not_double_count(client, create, action):
    project = create("projects", name="Own project")
    done = action(create("tasks", title="Finished", date=DAY, project_id=project["id"], estimated_duration=60), "complete")
    pending = create("tasks", title="Unfinished", date=DAY, estimated_duration=30)
    response = client.put(f"/api/reviews/{DAY}", json={"actual_minutes": 80, "energy_level": 4, "notes": "First note", "project_minutes": {project["id"]: 50}})
    assert response.status_code == 200
    saved = response.json()
    assert saved["completed_tasks"] == [{"id": done["id"], "title": "Finished"}]
    assert saved["unfinished_tasks"] == [{"id": pending["id"], "title": "Unfinished"}]
    action(pending, "reschedule", date="2026-09-22")
    assert client.get(f"/api/reviews/{DAY}").json()["unfinished_tasks"] == saved["unfinished_tasks"]
    stats = client.get(f"/api/statistics?start={DAY}&end={DAY}").json()
    assert stats["actual_minutes"] == 80
    assert sum(p["actual_minutes"] for p in stats["project_distribution"]) == 80
    updated = client.put(f"/api/reviews/{DAY}", json={"actual_minutes": 100, "project_minutes": {project["id"]: 70}})
    assert updated.status_code == 200 and updated.json()["id"] == saved["id"]
    assert client.get(f"/api/statistics?start={DAY}&end={DAY}").json()["actual_minutes"] == 100
    assert client.delete(f"/api/projects/{project['id']}").status_code == 409


def test_daily_review_rejects_invalid_allocations_and_future_dates(client, create):
    project = create("projects", name="Project")
    assert client.put(f"/api/reviews/{DAY}", json={"actual_minutes": 30, "project_minutes": {project["id"]: 31}}).status_code == 422
    assert client.put(f"/api/reviews/{DAY}", json={"actual_minutes": 30, "project_minutes": {project["id"]: -1}}).status_code == 422
    assert client.put(f"/api/reviews/{DAY}", json={"actual_minutes": 30, "project_minutes": {"missing": 10}}).status_code == 404
    assert client.put("/api/reviews/2026-09-22", json={"actual_minutes": 30}).status_code == 422
    assert client.get(f"/api/reviews/{DAY}").json()["saved"] is False


def test_completion_counts_follow_completion_day_and_ignore_cancelled_tasks(client, create, action):
    action(create("tasks", title="Yesterday done today", date="2026-09-20", estimated_duration=45), "complete")
    action(create("tasks", title="Today done", date=DAY, estimated_duration=60), "complete")
    create("tasks", title="Today open", date=DAY, estimated_duration=30)
    action(create("tasks", title="Cancelled", date=DAY, estimated_duration=100), "cancel")
    stats = client.get(f"/api/statistics?start={DAY}&end={DAY}").json()
    assert stats["completed_today"] == 2 and stats["completed_week"] == 2
    assert stats["total_tasks"] == 2 and stats["completed_tasks"] == 1
    assert stats["completion_rate"] == 50 and stats["planned_minutes"] == 90
    assert stats["actual_minutes"] == 0


def test_progress_rollup_reports_current_stage_and_empty_stages(client, create, action):
    goal = create("goals", name="My goal")
    project = create("projects", name="My project", goal_id=goal["id"])
    first = create("milestones", name="First", project_id=project["id"], start_date="2026-09-01", deadline="2026-09-20")
    second = create("milestones", name="Second", project_id=project["id"], start_date=DAY, deadline="2026-09-30")
    third = create("milestones", name="Empty next", project_id=project["id"], start_date="2026-10-01")
    action(create("tasks", title="Stage one", project_id=project["id"], milestone_id=first["id"]), "complete")
    task = create("tasks", title="Stage two", project_id=project["id"], milestone_id=second["id"])
    create("tasks", title="Outside projects")
    progress = client.get("/api/progress").json()
    assert progress["goals"][0]["percent"] == 50
    assert progress["goals"][0]["projects"][0]["current_milestone"]["id"] == second["id"]
    assert progress["unassigned_tasks"] == 1
    action(task, "complete")
    progress = client.get("/api/progress").json()
    view = progress["goals"][0]["projects"][0]
    assert view["percent"] == 100
    assert view["current_milestone"]["id"] == third["id"]
    assert view["current_milestone"]["percent"] == 0
