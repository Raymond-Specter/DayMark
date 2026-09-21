from .permissions import ToolPermission as P
from .tool_arguments import (
    CreateRoutineArgs, CreateTaskArgs, DeleteTaskArgs, EmptyArgs, GetCalendarArgs,
    GetFreeSlotsArgs, GetTasksArgs, ReplanDayArgs, RescheduleTaskArgs, RoutineIdArgs,
    ScheduleTaskArgs, TaskIdArgs, UpcomingArgs, UpdateRoutineArgs, UpdateTaskArgs,
)
from .tool_registry import ToolDefinition, ToolRegistry


def build_registry():
    registry = ToolRegistry()
    definitions = [
        ("get_today_tasks", "读取今天的全部真实任务。", EmptyArgs, P.READ, "正在读取今天的任务…"),
        ("get_tasks", "按日期、项目或状态查询真实任务。date/start_date/end_date 使用 YYYY-MM-DD。", GetTasksArgs, P.READ, "正在查询任务…"),
        ("get_calendar", "读取指定日期范围的任务和独立日历事项。", GetCalendarArgs, P.READ, "正在读取日历…"),
        ("get_free_slots", "用确定性代码计算某天空闲时间。time 使用 HH:MM。", GetFreeSlotsArgs, P.READ, "正在检查空闲时间…"),
        ("get_routines", "读取全部有效重复任务。", EmptyArgs, P.READ, "正在读取重复任务…"),
        ("get_upcoming_deadlines", "读取未来若干天的截止事项。", UpcomingArgs, P.READ, "正在读取临近截止事项…"),
        ("create_task", "在规划系统中创建任务。用户给出明确开始时间时必须使用本工具并原样保留该时间；会检测冲突。date 为 YYYY-MM-DD，time 为 HH:MM。", CreateTaskArgs, P.WRITE, "正在创建任务…"),
        ("update_task", "修改指定任务的字段；需要先查询任务取得精确 task_id。", UpdateTaskArgs, P.WRITE, "正在更新任务…"),
        ("reschedule_task", "更改指定任务日期和时间并检测冲突。", RescheduleTaskArgs, P.WRITE, "正在重新安排任务…"),
        ("complete_task", "将指定任务标记为完成。", TaskIdArgs, P.WRITE, "正在完成任务…"),
        ("cancel_task", "取消指定任务但保留记录。", TaskIdArgs, P.WRITE, "正在取消任务…"),
        ("create_routine", "创建重复任务规则并生成计划实例。", CreateRoutineArgs, P.WRITE, "正在创建重复任务…"),
        ("update_routine", "修改指定重复任务。", UpdateRoutineArgs, P.WRITE, "正在更新重复任务…"),
        ("pause_routine", "暂停指定重复任务。", RoutineIdArgs, P.WRITE, "正在暂停重复任务…"),
        ("schedule_task", "仅当用户没有给出明确开始时间、要求‘找个时间’时，在指定范围中寻找空闲时段并创建任务。明确时间必须用 create_task。", ScheduleTaskArgs, P.WRITE, "正在寻找时间并安排任务…"),
        ("replan_day", "将与明确占用时段冲突的任务尽量重新安排到当天其他空闲时间。", ReplanDayArgs, P.WRITE, "正在重新安排冲突任务…"),
        ("undo_last_action", "撤销当前会话最近一次可撤销的任务操作。", EmptyArgs, P.WRITE, "正在撤销最近操作…"),
        ("delete_task", "永久从正常视图删除指定任务；必须由用户确认保存的原始动作。", DeleteTaskArgs, P.DESTRUCTIVE, "正在准备删除任务…"),
    ]
    for name, description, arguments, permission, status in definitions:
        registry.register(ToolDefinition(name, description, arguments, permission, status, name))
    return registry
