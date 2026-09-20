from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .database import SessionLocal, get_db
from .models import CalendarEvent, DailyReview, Goal, Milestone, Notification, Project, Routine, Task, TaskHistory, now_iso
from .schemas import EventIn, GoalIn, MilestoneIn, ProjectIn, ReviewIn, RoutineIn, SettingsIn, TaskAction, TaskIn
from .services.calendar import CalendarService
from .services.common import live_tasks, raw, require, settings, sorted_tasks, task_dict, today
from .services.planner import PlannerService
from .services.reminder import ReminderService
from .services.scheduler import SchedulerService
from .services.statistics import StatisticsService


@asynccontextmanager
async def lifespan(app):
    # Migrations are explicit (setup/start scripts), never destructive auto-upgrades.
    with SessionLocal() as db:
        settings(db)
        SchedulerService(db).materialize()
        ReminderService(db).dispatch()
        db.commit()
    yield


app = FastAPI(title="Personal Planning System", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def local_mutation_guard(request: Request, call_next):
    # The MVP is localhost-only. Reject browser mutations from other websites.
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and origin not in {"http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"}:
            return JSONResponse(status_code=403, content={"detail": "仅允许本机应用修改数据"})
    return await call_next(request)


@app.exception_handler(IntegrityError)
async def integrity_error(request, error):
    return JSONResponse(status_code=409, content={"detail": "记录有关联内容或已被修改，请刷新后重试"})


@app.exception_handler(ValidationError)
async def domain_validation_error(request, error):
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(error.errors(), custom_encoder={ValueError: str})})


@app.exception_handler(OperationalError)
async def database_error(request, error):
    return JSONResponse(status_code=503, content={"detail": "数据库暂时不可用，请稍后重试；首次启动请先运行 setup.ps1"})


def commit(db):
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


@app.get("/health")
def health(db: Session = Depends(get_db)):
    settings(db)
    return {"status": "ok", "service": "personal-planning", "schema": "0001"}


@app.get("/api/bootstrap")
def bootstrap(db: Session = Depends(get_db)):
    SchedulerService(db).materialize()
    ReminderService(db).dispatch()
    commit(db)
    return {"settings": raw(settings(db)), "today": today(db).isoformat(),
            "goals": [raw(g) for g in db.scalars(select(Goal).order_by(Goal.created_at))],
            "projects": [raw(p) for p in db.scalars(select(Project).order_by(Project.created_at))],
            "milestones": [raw(m) for m in db.scalars(select(Milestone).order_by(Milestone.created_at))],
            "routines": [raw(r) for r in db.scalars(select(Routine).where(Routine.deleted_at.is_(None)).order_by(Routine.created_at))],
            "tasks": sorted_tasks(db, live_tasks(db)), "notifications": notifications(db)}


@app.get("/api/goals")
def goals(db: Session = Depends(get_db)):
    return [raw(row) for row in db.scalars(select(Goal).order_by(Goal.created_at))]


@app.post("/api/goals", status_code=201)
def create_goal(data: GoalIn, db: Session = Depends(get_db)):
    row = Goal(**data.model_dump())
    db.add(row)
    commit(db)
    return raw(row)


@app.put("/api/goals/{key}")
def update_goal(key: str, data: GoalIn, db: Session = Depends(get_db)):
    row = require(db, Goal, key)
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    commit(db)
    return raw(row)


@app.delete("/api/goals/{key}")
def delete_goal(key: str, db: Session = Depends(get_db)):
    row = require(db, Goal, key)
    if db.scalar(select(Project).where(Project.goal_id == key)):
        raise HTTPException(409, "目标下还有项目，请先移走项目，或将目标归档")
    db.delete(row)
    commit(db)
    return {"deleted": True}


@app.get("/api/projects")
def projects(db: Session = Depends(get_db)):
    return [raw(row) for row in db.scalars(select(Project).order_by(Project.created_at))]


def validate_project(db, data):
    if data.goal_id:
        require(db, Goal, data.goal_id)


@app.post("/api/projects", status_code=201)
def create_project(data: ProjectIn, db: Session = Depends(get_db)):
    validate_project(db, data)
    row = Project(**data.model_dump())
    db.add(row)
    commit(db)
    return raw(row)


@app.put("/api/projects/{key}")
def update_project(key: str, data: ProjectIn, db: Session = Depends(get_db)):
    row = require(db, Project, key)
    validate_project(db, data)
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    commit(db)
    return raw(row)


@app.delete("/api/projects/{key}")
def delete_project(key: str, db: Session = Depends(get_db)):
    row = require(db, Project, key)
    children = any(db.scalar(select(model).where(model.project_id == key)) for model in (Milestone, Task, Routine))
    allocated = any(key in r.project_minutes for r in db.scalars(select(DailyReview)))
    if children or allocated:
        raise HTTPException(409, "项目有关联任务、阶段或时间记录，请将项目归档以保留记录")
    db.delete(row)
    commit(db)
    return {"deleted": True}


@app.get("/api/milestones")
def milestones(db: Session = Depends(get_db)):
    return [raw(row) for row in db.scalars(select(Milestone).order_by(Milestone.created_at))]


@app.post("/api/milestones", status_code=201)
def create_milestone(data: MilestoneIn, db: Session = Depends(get_db)):
    require(db, Project, data.project_id)
    row = Milestone(**data.model_dump())
    db.add(row)
    commit(db)
    return raw(row)


@app.put("/api/milestones/{key}")
def update_milestone(key: str, data: MilestoneIn, db: Session = Depends(get_db)):
    row = require(db, Milestone, key)
    require(db, Project, data.project_id)
    if row.project_id != data.project_id and any(db.scalar(select(model).where(model.milestone_id == key)) for model in (Task, Routine)):
        raise HTTPException(409, "阶段已有任务，请先移动任务再更改所属项目")
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    commit(db)
    return raw(row)


@app.delete("/api/milestones/{key}")
def delete_milestone(key: str, db: Session = Depends(get_db)):
    row = require(db, Milestone, key)
    if any(db.scalar(select(model).where(model.milestone_id == key)) for model in (Task, Routine)):
        raise HTTPException(409, "阶段下仍有任务或重复规则，请先修改关联，或将阶段归档")
    db.delete(row)
    commit(db)
    return {"deleted": True}


@app.get("/api/tasks")
def tasks(start: date | None = None, end: date | None = None, status: str | None = None, project_id: str | None = None, db: Session = Depends(get_db)):
    result = sorted_tasks(db, live_tasks(db))
    return [t for t in result if (not start or t["date"] and t["date"] >= start.isoformat())
            and (not end or t["date"] and t["date"] <= end.isoformat()) and (not status or t["status"] == status)
            and (not project_id or t["project_id"] == project_id)]


@app.post("/api/tasks", status_code=201)
def create_task(data: TaskIn, db: Session = Depends(get_db)):
    task = PlannerService(db).create_task(data)
    commit(db)
    return task_dict(db, task)


@app.get("/api/tasks/{key}")
def get_task(key: str, db: Session = Depends(get_db)):
    return task_dict(db, require(db, Task, key))


@app.put("/api/tasks/{key}")
def update_task(key: str, data: TaskIn, db: Session = Depends(get_db)):
    task = PlannerService(db).update_task(require(db, Task, key), data)
    commit(db)
    return task_dict(db, task)


@app.post("/api/tasks/{key}/actions")
def task_action(key: str, data: TaskAction, db: Session = Depends(get_db)):
    task = PlannerService(db).action(require(db, Task, key), data)
    commit(db)
    return task_dict(db, task)


@app.delete("/api/tasks/{key}")
def delete_task(key: str, version: int, db: Session = Depends(get_db)):
    PlannerService(db).delete(require(db, Task, key), version)
    commit(db)
    return {"deleted": True}


@app.get("/api/tasks/{key}/history")
def task_history(key: str, db: Session = Depends(get_db)):
    require(db, Task, key)
    return [raw(row) for row in db.scalars(select(TaskHistory).where(TaskHistory.task_id == key).order_by(TaskHistory.created_at.desc()))]


@app.get("/api/routines")
def routines(db: Session = Depends(get_db)):
    return [raw(row) for row in db.scalars(select(Routine).where(Routine.deleted_at.is_(None)).order_by(Routine.created_at))]


@app.post("/api/routines", status_code=201)
def create_routine(data: RoutineIn, db: Session = Depends(get_db)):
    values = data.model_dump(exclude={"version"})
    PlannerService(db).validate_links(values)
    scheduler = SchedulerService(db)
    scheduler.validate_dependency(None, data.depends_on_routine_id)
    row = Routine(**values)
    db.add(row)
    db.flush()
    scheduler.materialize()
    commit(db)
    return raw(row)


@app.put("/api/routines/{key}")
def update_routine(key: str, data: RoutineIn, db: Session = Depends(get_db)):
    row = require(db, Routine, key)
    if data.version != row.version:
        raise HTTPException(409, "重复任务已更新，请刷新后重试")
    values = data.model_dump(exclude={"version"})
    PlannerService(db).validate_links(values)
    scheduler = SchedulerService(db)
    scheduler.validate_dependency(key, data.depends_on_routine_id)
    scheduler.materialize(end=today(db))
    if not row.active and data.active:
        # Paused days are intentionally skipped when a rule resumes.
        values["materialized_through"] = max(row.materialized_through or "0001-01-01", (today(db) - timedelta(days=1)).isoformat())
    changed = db.execute(update(Routine).where(Routine.id == key, Routine.version == data.version).values(**values, version=row.version + 1, updated_at=now_iso()))
    if not changed.rowcount:
        raise HTTPException(409, "重复任务已更新，请刷新后重试")
    db.refresh(row)
    scheduler.refresh_future(row)
    commit(db)
    return raw(row)


@app.delete("/api/routines/{key}")
def delete_routine(key: str, db: Session = Depends(get_db)):
    row = require(db, Routine, key)
    if db.scalar(select(Routine).where(Routine.depends_on_routine_id == key, Routine.deleted_at.is_(None))):
        raise HTTPException(409, "其他重复任务仍依赖此规则，请先修改依赖")
    row.active, row.deleted_at = False, now_iso()
    row.version += 1
    SchedulerService(db).refresh_future(row)
    commit(db)
    return {"deleted": True}


@app.post("/api/scheduler/sync")
def sync_scheduler(payload: dict = Body(default={}), db: Session = Depends(get_db)):
    try:
        start = date.fromisoformat(payload["start"]) if payload.get("start") else None
        end = date.fromisoformat(payload["end"]) if payload.get("end") else None
    except (ValueError, TypeError):
        raise HTTPException(422, "日期必须为 YYYY-MM-DD")
    created = SchedulerService(db).materialize(start, end)
    commit(db)
    return {"created": created}


@app.get("/api/calendar")
def calendar(start: date, end: date, db: Session = Depends(get_db)):
    if end <= start or (end - start).days > 366:
        raise HTTPException(422, "日历范围必须为 1–366 天")
    SchedulerService(db).materialize(start, end - timedelta(days=1))
    commit(db)
    return CalendarService(db).list_events(start.isoformat(), end.isoformat())


@app.post("/api/events", status_code=201)
def create_event(data: EventIn, db: Session = Depends(get_db)):
    row = CalendarEvent(**data.model_dump())
    db.add(row)
    commit(db)
    return raw(row)


@app.put("/api/events/{key}")
def update_event(key: str, data: EventIn, db: Session = Depends(get_db)):
    row = require(db, CalendarEvent, key)
    if row.task_id:
        raise HTTPException(409, "任务关联日历项请通过任务接口修改")
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    commit(db)
    return raw(row)


@app.delete("/api/events/{key}")
def delete_event(key: str, db: Session = Depends(get_db)):
    row = require(db, CalendarEvent, key)
    if row.task_id:
        raise HTTPException(409, "任务关联日历项请通过任务接口删除")
    db.delete(row)
    commit(db)
    return {"deleted": True}


@app.get("/api/today")
def get_today(db: Session = Depends(get_db)):
    SchedulerService(db).materialize()
    commit(db)
    return StatisticsService(db).today()


@app.get("/api/progress")
def get_progress(db: Session = Depends(get_db)):
    return StatisticsService(db).progress()


@app.get("/api/statistics")
def get_statistics(start: date | None = None, end: date | None = None, db: Session = Depends(get_db)):
    current = today(db)
    start, end = start or current - timedelta(days=current.weekday()), end or current
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "统计范围必须为 1–367 天")
    return StatisticsService(db).statistics(start, end)


@app.get("/api/reviews/{day}")
def get_review(day: date, db: Session = Depends(get_db)):
    row = db.scalar(select(DailyReview).where(DailyReview.date == day.isoformat()))
    return StatisticsService(db).review(day.isoformat(), row)


@app.put("/api/reviews/{day}")
def save_review(day: date, data: ReviewIn, db: Session = Depends(get_db)):
    if day > today(db):
        raise HTTPException(422, "每日回顾不能记录未来日期")
    for project_id in data.project_minutes:
        require(db, Project, project_id)
    row = db.scalar(select(DailyReview).where(DailyReview.date == day.isoformat()))
    if row is None:
        row = DailyReview(date=day.isoformat())
        db.add(row)
    snapshot = StatisticsService(db).review(day.isoformat())
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    row.completed_tasks, row.unfinished_tasks = snapshot["completed_tasks"], snapshot["unfinished_tasks"]
    commit(db)
    return {**raw(row), "saved": True}


@app.post("/api/reminders/dispatch")
def dispatch_reminders(db: Session = Depends(get_db)):
    SchedulerService(db).materialize()
    delivered = ReminderService(db).dispatch()
    commit(db)
    return {"delivered": delivered}


@app.get("/api/notifications")
def notifications(db: Session = Depends(get_db)):
    return [raw(row) for row in db.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(200))]


@app.post("/api/notifications/{key}/read")
def read_notification(key: str, db: Session = Depends(get_db)):
    row = require(db, Notification, key)
    row.read_at = row.read_at or now_iso()
    commit(db)
    return raw(row)


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    return raw(settings(db))


@app.put("/api/settings")
def update_settings(data: SettingsIn, db: Session = Depends(get_db)):
    row = settings(db)
    changed = row.timezone != data.timezone or row.day_start != data.day_start
    row.timezone, row.day_start = data.timezone, data.day_start
    db.flush()
    if changed:
        planner = PlannerService(db)
        for task in live_tasks(db):
            if task.status not in {"completed", "cancelled"} and task.reminder is not None:
                planner.mutate(task, {}, task.version, "settings_updated", exception=False)
    commit(db)
    return raw(row)


@app.get("/api/integrations")
def integrations():
    return {"google_calendar": {"configured": False, "status": "planned"}, "openai": {"configured": False, "status": "planned"},
            "reminders": {"channel": "in_app", "background_delivery": False}}


@app.get("/api/export")
def export_data(db: Session = Depends(get_db)):
    from .database import Base
    result = {"format": "personal-planning-v1", "exported_at": now_iso(), "tables": {}}
    for table in Base.metadata.sorted_tables:
        result["tables"][table.name] = [dict(row) for row in db.execute(select(table)).mappings()]
    return JSONResponse(content=result, headers={"Content-Disposition": 'attachment; filename="personal-planning.json"'})
