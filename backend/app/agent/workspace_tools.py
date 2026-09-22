import hashlib
import shutil
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from ..learning_schemas import LearningEntryIn, LearningEntryPatch
from ..ai_schemas import ModelSettings
from ..models import (AISettings, CalendarEvent, ChatAttachment, DailyReview, Goal, KnowledgeDocument,
                      LearningEntry, Milestone, Notification, Project, Routine, Task, now_iso)
from ..schemas import EventIn, GoalIn, MilestoneIn, ProjectIn, ReviewIn, SettingsIn
from ..services.attachments import attachment_path, safe_filename
from ..services.common import live_tasks, raw, require, settings, today
from ..services.knowledge import KNOWLEDGE_DIR, document_dict, entry_dict, validate_entry_links
from ..services.planner import PlannerService
from ..services.statistics import StatisticsService


class WorkspaceTools:
    """Tool handlers for the page features outside task scheduling."""

    def _organization_rows(self, model, status):
        rows = list(self.db.scalars(select(model).order_by(model.created_at)))
        return [raw(row) for row in rows if not status or row.status == status]

    def get_goals(self, args):
        rows = self._organization_rows(Goal, args.status)
        return self.ok(f"找到 {len(rows)} 个目标。", rows)

    def create_goal(self, args):
        checked = GoalIn(**args.model_dump())
        row = Goal(**checked.model_dump())
        self.db.add(row); self.db.flush()
        return self.ok(f"已创建目标“{row.name}”。", raw(row),
                       [{"type": "goal", "id": row.id}], None, raw(row))

    def update_goal(self, args):
        row = require(self.db, Goal, args.record_id); before = raw(row)
        values = {key: getattr(row, key) for key in GoalIn.model_fields}
        values.update(args.model_dump(exclude_unset=True, exclude={"record_id"}))
        checked = GoalIn(**values)
        for key, value in checked.model_dump().items(): setattr(row, key, value)
        self.db.flush()
        return self.ok(f"已更新目标“{row.name}”。", raw(row),
                       [{"type": "goal", "id": row.id}], before, raw(row))

    def delete_goal(self, args):
        row = require(self.db, Goal, args.record_id); before = raw(row)
        if self.db.scalar(select(Project).where(Project.goal_id == row.id)):
            raise HTTPException(409, "目标下还有项目，请先移走项目，或将目标归档")
        self.db.delete(row); self.db.flush()
        return self.ok(f"已删除目标“{row.name}”。", {"deleted": True},
                       [{"type": "goal", "id": row.id}], before, {"id": row.id, "deleted": True})

    def get_projects(self, args):
        rows = self._organization_rows(Project, args.status)
        return self.ok(f"找到 {len(rows)} 个项目。", rows)

    def create_project(self, args):
        checked = ProjectIn(**args.model_dump())
        if checked.goal_id: require(self.db, Goal, checked.goal_id)
        row = Project(**checked.model_dump())
        self.db.add(row); self.db.flush()
        return self.ok(f"已创建项目“{row.name}”。", raw(row),
                       [{"type": "project", "id": row.id}], None, raw(row))

    def update_project(self, args):
        row = require(self.db, Project, args.record_id); before = raw(row)
        values = {key: getattr(row, key) for key in ProjectIn.model_fields}
        values.update(args.model_dump(exclude_unset=True, exclude={"record_id"}))
        checked = ProjectIn(**values)
        if checked.goal_id: require(self.db, Goal, checked.goal_id)
        for key, value in checked.model_dump().items(): setattr(row, key, value)
        self.db.flush()
        return self.ok(f"已更新项目“{row.name}”。", raw(row),
                       [{"type": "project", "id": row.id}], before, raw(row))

    def delete_project(self, args):
        row = require(self.db, Project, args.record_id); before = raw(row)
        related = any(self.db.scalar(select(model).where(model.project_id == row.id))
                      for model in (Milestone, Task, Routine, LearningEntry, KnowledgeDocument))
        allocated = any(row.id in review.project_minutes for review in self.db.scalars(select(DailyReview)))
        if related or allocated:
            raise HTTPException(409, "项目有关联内容或时间记录，请将项目归档以保留记录")
        self.db.delete(row); self.db.flush()
        return self.ok(f"已删除项目“{row.name}”。", {"deleted": True},
                       [{"type": "project", "id": row.id}], before, {"id": row.id, "deleted": True})

    def get_milestones(self, args):
        rows = self._organization_rows(Milestone, args.status)
        return self.ok(f"找到 {len(rows)} 个里程碑。", rows)

    def create_milestone(self, args):
        checked = MilestoneIn(**args.model_dump()); require(self.db, Project, checked.project_id)
        row = Milestone(**checked.model_dump())
        self.db.add(row); self.db.flush()
        return self.ok(f"已创建里程碑“{row.name}”。", raw(row),
                       [{"type": "milestone", "id": row.id}], None, raw(row))

    def update_milestone(self, args):
        row = require(self.db, Milestone, args.record_id); before = raw(row)
        values = {key: getattr(row, key) for key in MilestoneIn.model_fields}
        values.update(args.model_dump(exclude_unset=True, exclude={"record_id"}))
        checked = MilestoneIn(**values); require(self.db, Project, checked.project_id)
        if row.project_id != checked.project_id and any(
                self.db.scalar(select(model).where(model.milestone_id == row.id)) for model in (Task, Routine)):
            raise HTTPException(409, "阶段已有任务，请先移动任务再更改所属项目")
        for key, value in checked.model_dump().items(): setattr(row, key, value)
        self.db.flush()
        return self.ok(f"已更新里程碑“{row.name}”。", raw(row),
                       [{"type": "milestone", "id": row.id}], before, raw(row))

    def delete_milestone(self, args):
        row = require(self.db, Milestone, args.record_id); before = raw(row)
        if any(self.db.scalar(select(model).where(model.milestone_id == row.id)) for model in (Task, Routine)):
            raise HTTPException(409, "阶段下仍有任务或重复规则，请先修改关联，或将阶段归档")
        self.db.delete(row); self.db.flush()
        return self.ok(f"已删除里程碑“{row.name}”。", {"deleted": True},
                       [{"type": "milestone", "id": row.id}], before, {"id": row.id, "deleted": True})

    def create_event(self, args):
        checked = EventIn(**args.model_dump()); row = CalendarEvent(**checked.model_dump())
        self.db.add(row); self.db.flush()
        return self.ok(f"已创建日历事项“{row.title}”。", raw(row),
                       [{"type": "event", "id": row.id}], None, raw(row))

    def update_event(self, args):
        row = require(self.db, CalendarEvent, args.event_id)
        if row.task_id: raise HTTPException(409, "任务关联日历项请通过任务接口修改")
        before = raw(row)
        values = {key: getattr(row, key) for key in EventIn.model_fields}
        values.update(args.model_dump(exclude_unset=True, exclude={"event_id"}))
        checked = EventIn(**values)
        for key, value in checked.model_dump().items(): setattr(row, key, value)
        self.db.flush()
        return self.ok(f"已更新日历事项“{row.title}”。", raw(row),
                       [{"type": "event", "id": row.id}], before, raw(row))

    def delete_event(self, args):
        row = require(self.db, CalendarEvent, args.event_id)
        if row.task_id: raise HTTPException(409, "任务关联日历项请通过任务接口删除")
        before = raw(row); self.db.delete(row); self.db.flush()
        return self.ok(f"已删除日历事项“{row.title}”。", {"deleted": True},
                       [{"type": "event", "id": row.id}], before, {"id": row.id, "deleted": True})

    def get_learning_entries(self, args):
        query = select(LearningEntry).where(LearningEntry.deleted_at.is_(None))
        if args.date: query = query.where(LearningEntry.date == args.date)
        if args.start_date: query = query.where(LearningEntry.date >= args.start_date)
        if args.end_date: query = query.where(LearningEntry.date <= args.end_date)
        if args.project_id: query = query.where(LearningEntry.project_id == args.project_id)
        if args.entry_type: query = query.where(LearningEntry.entry_type == args.entry_type)
        if args.status: query = query.where(LearningEntry.status == args.status)
        rows = list(self.db.scalars(query.order_by(LearningEntry.date.desc()).limit(200)))
        return self.ok(f"找到 {len(rows)} 条学习记录。", [entry_dict(self.db, row) for row in rows])

    def create_learning_entry(self, args):
        checked = LearningEntryIn(**args.model_dump())
        row = LearningEntry(**validate_entry_links(self.db, checked.model_dump()))
        self.db.add(row); self.db.flush()
        return self.ok(f"已创建学习记录“{row.title}”。", entry_dict(self.db, row),
                       [{"type": "learning_entry", "id": row.id}], None, raw(row))

    def update_learning_entry(self, args):
        row = require(self.db, LearningEntry, args.record_id)
        if row.deleted_at: raise HTTPException(404, "学习记录不存在")
        before = raw(row)
        changes = args.model_dump(exclude_unset=True, exclude={"record_id"})
        checked = LearningEntryPatch(version=row.version, **changes)
        merged = validate_entry_links(self.db, {"project_id": row.project_id, "task_id": row.task_id,
                                                 **checked.model_dump(exclude_unset=True, exclude={"version"})})
        for key, value in changes.items(): setattr(row, key, value)
        row.project_id, row.task_id = merged.get("project_id"), merged.get("task_id")
        row.version += 1; row.updated_at = now_iso(); self.db.flush()
        return self.ok(f"已更新学习记录“{row.title}”。", entry_dict(self.db, row),
                       [{"type": "learning_entry", "id": row.id}], before, raw(row))

    def delete_learning_entry(self, args):
        row = require(self.db, LearningEntry, args.record_id)
        if row.deleted_at: raise HTTPException(404, "学习记录不存在")
        before = raw(row); row.deleted_at = now_iso(); row.updated_at = row.deleted_at; row.version += 1
        self.db.flush()
        return self.ok(f"已删除学习记录“{row.title}”。", {"deleted": True},
                       [{"type": "learning_entry", "id": row.id}], before, raw(row))

    def get_documents(self, args):
        query = select(KnowledgeDocument).where(KnowledgeDocument.deleted_at.is_(None))
        if args.date: query = query.where(KnowledgeDocument.knowledge_date == args.date)
        if args.start_date: query = query.where(KnowledgeDocument.knowledge_date >= args.start_date)
        if args.end_date: query = query.where(KnowledgeDocument.knowledge_date <= args.end_date)
        if args.project_id: query = query.where(KnowledgeDocument.project_id == args.project_id)
        if args.document_type: query = query.where(KnowledgeDocument.document_type == args.document_type)
        if args.is_output is not None: query = query.where(KnowledgeDocument.is_output == args.is_output)
        rows = list(self.db.scalars(query.order_by(KnowledgeDocument.knowledge_date.desc()).limit(200)))
        return self.ok(f"找到 {len(rows)} 份知识文档。", [document_dict(self.db, row) for row in rows])

    def save_attachment_to_knowledge(self, args):
        filename = safe_filename(args.filename)
        attachment = self.db.scalar(select(ChatAttachment).where(
            ChatAttachment.conversation_id == self.conversation_id,
            ChatAttachment.filename == filename,
        ).order_by(ChatAttachment.created_at.desc()))
        if not attachment: raise HTTPException(404, "当前对话中没有找到这个附件，请先上传文件")
        if args.project_id: require(self.db, Project, args.project_id)
        source = attachment_path(attachment.storage_name)
        if not source.is_file(): raise HTTPException(404, "附件原文件不存在，请重新上传")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        if self.db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.sha256 == digest)):
            raise HTTPException(409, "该文件已经保存在知识库中")
        document_id = str(uuid4()); extension = Path(filename).suffix.lower()
        relative = Path(digest[:2]) / f"{document_id}{extension}"
        destination = KNOWLEDGE_DIR / relative; destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        row = KnowledgeDocument(
            id=document_id, title=args.title or Path(filename).stem[:200], source_type="file",
            original_filename=filename, storage_path=relative.as_posix(), file_type=extension.lstrip("."),
            mime_type=attachment.media_type, file_size=attachment.size_bytes, sha256=digest,
            project_id=args.project_id, knowledge_date=args.knowledge_date, upload_date=today(self.db).isoformat(),
            document_type=args.document_type, is_output=args.is_output, processing_status="ready",
            parser_name="chat-attachment", parser_version="1", extracted_text=attachment.extracted_text,
            extracted_at=now_iso(), description=args.description,
        )
        self.db.add(row); self.db.flush()
        return self.ok(f"已将“{filename}”保存到知识库。", document_dict(self.db, row),
                       [{"type": "document", "id": row.id}], None, raw(row))

    def update_document(self, args):
        row = require(self.db, KnowledgeDocument, args.record_id)
        if row.deleted_at: raise HTTPException(404, "文档不存在")
        before = raw(row); changes = args.model_dump(exclude_unset=True, exclude={"record_id"})
        if changes.get("project_id"): require(self.db, Project, changes["project_id"])
        for key, value in changes.items(): setattr(row, key, value)
        row.version += 1; row.updated_at = now_iso(); self.db.flush()
        return self.ok(f"已更新知识文档“{row.title}”。", document_dict(self.db, row),
                       [{"type": "document", "id": row.id}], before, raw(row))

    def delete_document(self, args):
        row = require(self.db, KnowledgeDocument, args.record_id)
        if row.deleted_at: raise HTTPException(404, "文档不存在")
        before = raw(row); row.deleted_at = now_iso(); row.updated_at = row.deleted_at; row.version += 1
        self.db.flush()
        return self.ok(f"已从知识库删除“{row.title}”，原文件仍保留。", {"deleted": True},
                       [{"type": "document", "id": row.id}], before, raw(row))

    def get_daily_review(self, args):
        row = self.db.scalar(select(DailyReview).where(DailyReview.date == args.date))
        return self.ok(f"已读取 {args.date} 的每日复盘。", StatisticsService(self.db).review(args.date, row))

    def save_daily_review(self, args):
        if date.fromisoformat(args.date) > today(self.db): raise HTTPException(422, "每日回顾不能记录未来日期")
        checked = ReviewIn(**args.model_dump(exclude={"date"}))
        for project_id in checked.project_minutes: require(self.db, Project, project_id)
        row = self.db.scalar(select(DailyReview).where(DailyReview.date == args.date))
        before = raw(row) if row else None
        if row is None: row = DailyReview(date=args.date); self.db.add(row)
        snapshot = StatisticsService(self.db).review(args.date)
        for key, value in checked.model_dump().items(): setattr(row, key, value)
        row.completed_tasks, row.unfinished_tasks = snapshot["completed_tasks"], snapshot["unfinished_tasks"]
        self.db.flush()
        return self.ok(f"已保存 {args.date} 的每日复盘。", {**raw(row), "saved": True},
                       [{"type": "daily_review", "id": row.id}], before, raw(row))

    def get_statistics(self, args):
        current = today(self.db)
        start = date.fromisoformat(args.date or args.start_date) if (args.date or args.start_date) else current - timedelta(days=current.weekday())
        end = date.fromisoformat(args.date or args.end_date) if (args.date or args.end_date) else current
        if end < start or (end - start).days > 366: raise HTTPException(422, "统计范围必须为 1–367 天")
        return self.ok(f"已读取 {start} 至 {end} 的统计。", StatisticsService(self.db).statistics(start, end))

    def get_progress(self, _):
        return self.ok("已读取目标与项目进度。", StatisticsService(self.db).progress())

    def get_settings(self, _):
        return self.ok("已读取偏好设置。", raw(settings(self.db)))

    def update_settings(self, args):
        row = settings(self.db); before = raw(row)
        values = {"timezone": row.timezone, "day_start": row.day_start}
        values.update(args.model_dump(exclude_unset=True))
        checked = SettingsIn(**values); changed = checked.timezone != row.timezone or checked.day_start != row.day_start
        row.timezone, row.day_start = checked.timezone, checked.day_start
        self.db.flush()
        if changed:
            planner = PlannerService(self.db)
            for task in live_tasks(self.db):
                if task.status not in {"completed", "cancelled"} and task.reminder is not None:
                    planner.mutate(task, {}, task.version, "settings_updated", exception=False)
        return self.ok("已更新偏好设置。", raw(row),
                       [{"type": "settings", "id": str(row.id)}], before, raw(row))

    def get_notifications(self, _):
        rows = [raw(row) for row in self.db.scalars(select(Notification).order_by(Notification.created_at.desc()).limit(200))]
        return self.ok(f"找到 {len(rows)} 条通知。", rows)

    def mark_notification_read(self, args):
        row = require(self.db, Notification, args.notification_id); before = raw(row)
        row.read_at = row.read_at or now_iso(); self.db.flush()
        return self.ok("已将通知标记为已读。", raw(row),
                       [{"type": "notification", "id": row.id}], before, raw(row))

    def get_ai_settings(self, _):
        row = self.db.get(AISettings, 1)
        data = ({"mode": row.mode, "model": row.model, "num_ctx": row.num_ctx,
                 "temperature": float(row.temperature), "think": row.think}
                if row else ModelSettings().model_dump())
        return self.ok("已读取模型设置；API Key 不会返回。", data)

    def update_ai_settings(self, args):
        row = self.db.get(AISettings, 1)
        before = (raw(row) if row else None)
        values = ({"mode": row.mode, "model": row.model, "num_ctx": row.num_ctx,
                   "temperature": float(row.temperature), "think": row.think}
                  if row else ModelSettings().model_dump())
        values.update(args.model_dump(exclude_unset=True))
        checked = ModelSettings(**values)
        if checked.model.endswith(":cloud") or "cloud" in checked.model.split(":")[-1]:
            raise HTTPException(422, "Local Model 只能选择本地 Ollama 模型")
        if row is None:
            row = AISettings(id=1); self.db.add(row)
        row.mode, row.model, row.num_ctx = checked.mode, checked.model, checked.num_ctx
        row.temperature, row.think = str(checked.temperature), checked.think
        self.db.flush()
        after = {"mode": row.mode, "model": row.model, "num_ctx": row.num_ctx,
                 "temperature": float(row.temperature), "think": row.think}
        return self.ok("已更新模型设置，将从下一次对话请求开始生效。", after,
                       [{"type": "ai_settings", "id": "1"}], before, after)

    def prepare_data_export(self, _):
        filename = f"daymark-backup-{today(self.db).isoformat()}.json"
        return self.ok("数据导出已经准备好，请打开返回的下载地址。",
                       {"download_url": "/api/export", "filename": filename})
