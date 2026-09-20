from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from ..models import Goal, Project, Settings, Task


def utc_now():
    return datetime.now(timezone.utc)


def settings(db):
    value = db.get(Settings, 1)
    if value is None:
        value = Settings(id=1, timezone="Asia/Shanghai", day_start="09:00")
        db.add(value)
        db.flush()
    return value


def local_now(db):
    return utc_now().astimezone(ZoneInfo(settings(db).timezone))


def today(db):
    return local_now(db).date()


def raw(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def require(db, model, key):
    row = db.get(model, key)
    if row is None or getattr(row, "deleted_at", None):
        raise HTTPException(404, "记录不存在或已删除")
    return row


def effective_status(db, task):
    if task.status in {"completed", "cancelled"}:
        return task.status
    if task.deadline and datetime.fromisoformat(task.deadline) < utc_now():
        return "overdue"
    if task.date and task.date < today(db).isoformat():
        return "overdue"
    return "pending" if task.status == "overdue" else task.status


def task_dependency(db, task):
    if task.depends_on_task_id:
        parent = db.get(Task, task.depends_on_task_id)
        if parent is None or parent.deleted_at:
            return True, "前置任务已删除，请先修改依赖", None
        if parent.status != "completed":
            return True, f"等待完成：{parent.title}", parent.title
        return False, None, parent.title
    if task.depends_on_routine_id:
        return True, "对应日期没有前置任务，请调整重复规则或本次依赖", None
    return False, None, None


def task_dict(db, task):
    result = raw(task)
    result["stored_status"] = task.status
    result["status"] = effective_status(db, task)
    result["blocked"], result["blocked_reason"], result["dependency_title"] = task_dependency(db, task)
    return result


def live_tasks(db):
    return list(db.scalars(select(Task).where(Task.deleted_at.is_(None))))


def task_color(db, task):
    project = db.get(Project, task.project_id) if task.project_id else None
    goal = db.get(Goal, project.goal_id) if project and project.goal_id else None
    return goal.color if goal else "#4f6ef7"


def sorted_tasks(db, tasks):
    return [task_dict(db, task) for task in sorted(tasks, key=lambda t: (t.start_time or "99:99", t.priority, t.created_at))]


def upcoming(db, limit=12):
    tasks = [t for t in live_tasks(db) if t.deadline and t.status not in {"completed", "cancelled"}]
    tasks.sort(key=lambda t: (t.deadline, t.priority))
    return [task_dict(db, task) for task in tasks[:limit]]


def completion_date(db, task):
    return datetime.fromisoformat(task.completed_at).astimezone(ZoneInfo(settings(db).timezone)).date() if task.completed_at else None
