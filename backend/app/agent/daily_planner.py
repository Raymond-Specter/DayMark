"""Plan additions only. Existing tasks, events and recurrence rules are never moved."""
from datetime import date, timedelta

from ..models import Task
from ..services.common import local_now, require
from .planner_service import AgentPlannerService, clock, minutes


class DailyPlanner:
    def __init__(self, db):
        self.db = db
        self.planner = AgentPlannerService(db)

    def missing_questions(self, args):
        questions = []
        if not args.start_date:
            questions.append({"id": "start_date", "question": "从哪一天开始？", "options": ["今天", "明天"]})
        if not args.end_date:
            questions.append({"id": "end_date", "question": "这次先规划多长时间？", "options": ["7天", "14天", "30天"]})
        if not args.windows:
            questions.append({"id": "windows", "question": "每天哪些时段可以用于这个计划？请排除睡眠、用餐等保留时间。", "options": []})
        if args.allow_split is None:
            questions.append({"id": "allow_split", "question": "每日目标能否拆成多个时段？", "options": ["可以分段", "必须连续完成"]})
        elif args.allow_split and args.min_session_minutes is None:
            questions.append({"id": "min_session", "question": "每个分段至少多长？",
                              "options": [f"{value}分钟" for value in (15, 30, 60, 90) if value <= args.daily_minutes]})
        return questions[:4]

    @staticmethod
    def summary(args):
        parts = [f"“{args.title}”，每天目标 {args.daily_minutes} 分钟"]
        parts.append(f"计入用户选定的 {len(set(args.counted_task_ids))} 个旧任务" if args.counted_task_ids else "时长全部新增")
        if args.start_date:
            parts.append("开始日期 " + args.start_date)
        if args.end_date:
            parts.append("截止日期 " + args.end_date)
        if args.windows:
            parts.append("可用时段 " + "、".join(window.start_time + "–" + window.end_time for window in args.windows))
        if args.allow_split is not None:
            parts.append("允许分段" if args.allow_split else "必须连续完成")
        if args.allow_split and args.min_session_minutes:
            parts.append(f"每段至少 {args.min_session_minutes} 分钟")
        return "；".join(parts)

    def preview(self, args):
        start, end = date.fromisoformat(args.start_date), date.fromisoformat(args.end_date)
        if (end - start).days > 30:
            raise ValueError("单次最多规划31天，请先选择一段日期；不会自动无限延长。")
        current = local_now(self.db)
        if start < current.date():
            raise ValueError("新增规划不能从过去的日期开始。")
        counted_tasks = [require(self.db, Task, task_id) for task_id in sorted(set(args.counted_task_ids))]
        if any(task.deleted_at or task.status == "cancelled" for task in counted_tasks):
            raise ValueError("计入目标的旧任务已取消或删除，请重新选择。")
        windows = sorted((minutes(window.start_time), minutes(window.end_time)) for window in args.windows)
        if any(left[1] > right[0] for left, right in zip(windows, windows[1:])):
            raise ValueError("可用时段不能互相重叠。")
        days = []
        day = start
        while day <= end:
            if day.weekday() in args.weekdays:
                existing_minutes = sum(task.estimated_duration for task in counted_tasks if task.date == day.isoformat())
                required = max(0, args.daily_minutes - existing_minutes)
                minimum = args.min_session_minutes if args.allow_split else args.daily_minutes
                if not args.allow_split:
                    minimum = required
                slots, remaining = [], required
                for begin, finish in windows:
                    if not remaining:
                        break
                    if day == current.date():
                        begin = max(begin, current.hour * 60 + current.minute + 1)
                    if begin >= finish:
                        continue
                    free = self.planner.free_slots(day.isoformat(), clock(begin), clock(finish), minimum)
                    for gap in free:
                        duration = min(gap["duration_minutes"], remaining)
                        # Avoid a last fragment shorter than the user allowed.
                        if args.allow_split and 0 < remaining - duration < minimum:
                            duration = remaining - minimum
                        if duration < minimum:
                            continue
                        slots.append({"start_time": gap["start_time"],
                                      "end_time": clock(minutes(gap["start_time"]) + duration),
                                      "duration_minutes": duration})
                        remaining -= duration
                        if not remaining:
                            break
                    if not remaining:
                        break
                days.append({"date": day.isoformat(), "slots": slots,
                             "existing_minutes": existing_minutes,
                             "scheduled_minutes": required - remaining,
                             "shortfall_minutes": remaining})
            day += timedelta(days=1)
        if not days:
            raise ValueError("日期范围内没有选中的星期。")
        return {"title": args.title, "daily_minutes": args.daily_minutes, "days": days,
                "counted_tasks": [{"id": task.id, "version": task.version} for task in counted_tasks],
                "task_count": sum(len(day["slots"]) for day in days)}
