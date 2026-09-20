from datetime import date, timedelta

from sqlalchemy import select

from ..models import DailyReview, Goal, Milestone, Project
from .common import completion_date, live_tasks, raw, sorted_tasks, today, upcoming


class StatisticsService:
    def __init__(self, db):
        self.db = db

    def today(self):
        current = today(self.db)
        tasks = live_tasks(self.db)
        scheduled = [t for t in tasks if t.date == current.isoformat() and t.status != "cancelled"]
        yesterday = [t for t in tasks if t.date == (current - timedelta(days=1)).isoformat() and t.status not in {"completed", "cancelled"}]
        overdue = [t for t in tasks if t.date and t.date < (current - timedelta(days=1)).isoformat() and t.status not in {"completed", "cancelled"}]
        return {"date": current.isoformat(), "tasks": sorted_tasks(self.db, scheduled),
                "unfinished_yesterday": sorted_tasks(self.db, yesterday), "overdue": sorted_tasks(self.db, overdue),
                "completed_count": sum(t.status == "completed" for t in scheduled),
                "remaining_count": sum(t.status != "completed" for t in scheduled), "upcoming_deadlines": upcoming(self.db)}

    def statistics(self, start, end):
        current = today(self.db)
        monday = current - timedelta(days=current.weekday())
        all_tasks = live_tasks(self.db)
        tasks = [t for t in all_tasks if t.date and start.isoformat() <= t.date <= end.isoformat() and t.status != "cancelled"]
        completed = [t for t in tasks if t.status == "completed"]
        reviews = list(self.db.scalars(select(DailyReview).where(DailyReview.date >= start.isoformat(), DailyReview.date <= end.isoformat())))
        projects = list(self.db.scalars(select(Project)))
        distribution = []
        for project in [*projects, None]:
            project_id = project.id if project else None
            goal = self.db.get(Goal, project.goal_id) if project and project.goal_id else None
            planned = sum(t.estimated_duration for t in tasks if t.project_id == project_id)
            actual = sum(r.project_minutes.get(project_id, 0) if project else r.actual_minutes - sum(r.project_minutes.values()) for r in reviews)
            if planned or actual:
                distribution.append({"project_id": project_id, "name": project.name if project else "未分配项目", "color": goal.color if goal else "#8b9cb5", "planned_minutes": planned, "actual_minutes": actual})
        daily = []
        day = start
        while day <= end:
            selected = [t for t in tasks if t.date == day.isoformat()]
            review = next((r for r in reviews if r.date == day.isoformat()), None)
            daily.append({"date": day.isoformat(), "planned_minutes": sum(t.estimated_duration for t in selected),
                          "actual_minutes": review.actual_minutes if review else 0,
                          "completed": sum(t.status == "completed" for t in selected), "total": len(selected)})
            day += timedelta(days=1)
        return {"start": start.isoformat(), "end": end.isoformat(),
                "completed_today": sum(t.status == "completed" and completion_date(self.db, t) == current for t in all_tasks),
                "completed_week": sum(t.status == "completed" and monday <= completion_date(self.db, t) < monday + timedelta(days=7) for t in all_tasks),
                "completion_rate": round(len(completed) / len(tasks) * 100, 1) if tasks else 0,
                "planned_minutes": sum(t.estimated_duration for t in tasks), "actual_minutes": sum(r.actual_minutes for r in reviews),
                "total_tasks": len(tasks), "completed_tasks": len(completed), "project_distribution": distribution,
                "daily": daily, "upcoming_deadlines": upcoming(self.db)}

    def progress(self):
        tasks = [t for t in live_tasks(self.db) if t.status != "cancelled"]
        def counts(items):
            total = len(items)
            completed = sum(t.status == "completed" for t in items)
            return {"total": total, "completed": completed, "percent": round(100 * completed / total) if total else 0}
        goals = list(self.db.scalars(select(Goal).order_by(Goal.priority, Goal.created_at)))
        projects = list(self.db.scalars(select(Project).order_by(Project.created_at)))
        milestones = list(self.db.scalars(select(Milestone).order_by(Milestone.start_date, Milestone.deadline, Milestone.created_at)))
        def project_view(project):
            stages = [{**raw(m), **counts([t for t in tasks if t.milestone_id == m.id])} for m in milestones if m.project_id == project.id]
            current = next((m for m in stages if m["status"] not in {"completed", "archived"} and (m["total"] == 0 or m["completed"] < m["total"])), None)
            return {**raw(project), **counts([t for t in tasks if t.project_id == project.id]), "milestones": stages, "current_milestone": current}
        return {"goals": [{**raw(g), **counts([t for t in tasks if any(p.id == t.project_id and p.goal_id == g.id for p in projects)]),
                            "projects": [project_view(p) for p in projects if p.goal_id == g.id]} for g in goals],
                "standalone_projects": [project_view(p) for p in projects if not p.goal_id],
                "unassigned_tasks": sum(not t.project_id for t in tasks)}

    def review(self, day, saved=None):
        tasks = live_tasks(self.db)
        scheduled = [t for t in tasks if t.date == day and t.status != "cancelled"]
        completed = [t for t in tasks if t.status == "completed" and completion_date(self.db, t).isoformat() == day]
        snapshot = lambda items: [{"id": t.id, "title": t.title} for t in items]
        if saved:
            return {**raw(saved), "saved": True}
        return {"date": day, "actual_minutes": 0, "energy_level": 3, "notes": "", "project_minutes": {},
                "completed_tasks": snapshot(completed), "unfinished_tasks": snapshot([t for t in scheduled if t.status != "completed"]), "saved": False}
