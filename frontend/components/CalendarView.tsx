"use client";
import { browserLocale, getLanguage, uiText, uiFormat } from "@/lib/i18n";
import { useCallback, useEffect, useRef, useState } from "react";
import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import zhLocale from "@fullcalendar/core/locales/zh-cn";
import type { EventApi, EventInput } from "@fullcalendar/core";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { api, send, taskPayload, zonedInput } from "@/lib/api";
import type {
  Bootstrap,
  CalendarEventRecord,
  EditorState,
  Task,
} from "@/lib/types";
import "./calendar-dark.css";

export default function CalendarView({
  data,
  revision,
  edit,
  changed,
  notify,
}: {
  data: Bootstrap;
  revision: number;
  edit: (editor: EditorState) => void;
  changed: () => Promise<void>;
  notify: (message: string, error?: boolean) => void;
}) {
  const calendar = useRef<FullCalendar>(null);
  const [view, setView] = useState("timeGridWeek");
  const [title, setTitle] = useState("");
  const fetchEvents = useCallback(async (
    info: { startStr: string; endStr: string },
    success: (events: EventInput[]) => void,
    failure: (error: Error) => void,
  ) => {
    try {
      success(await api<EventInput[]>(`/calendar?start=${info.startStr.slice(0, 10)}&end=${info.endStr.slice(0, 10)}`));
    } catch (e) {
      failure(e as Error);
      notify((e as Error).message, true);
    }
  }, [notify]);
  useEffect(() => {
    calendar.current?.getApi().refetchEvents();
  }, [revision]);
  const switchView = (next: string) => {
    setView(next);
    calendar.current?.getApi().changeView(next);
  };

  async function move({
    event,
    revert,
  }: {
    event: EventApi;
    revert: () => void;
  }) {
    try {
      const task = event.extendedProps.task as Task | null;
      if (task) {
        if (
          event.endStr &&
          !event.allDay &&
          event.startStr.slice(0, 10) !== event.endStr.slice(0, 10)
        )
          throw new Error(uiText("任务暂不支持跨天，请在同一天安排开始和结束时间"));
        await send(
          `/tasks/${task.id}`,
          {
            ...taskPayload(task),
            date: event.startStr.slice(0, 10),
            start_time: event.allDay ? null : event.startStr.slice(11, 16),
            end_time: event.allDay ? null : event.endStr?.slice(11, 16) || null,
          },
          "PUT",
        );
      } else {
        const id =
          event.extendedProps.event_id || event.id.replace(/^event-/, "");
        await send(
          `/events/${id}`,
          {
            title: event.title,
            start: event.allDay
              ? event.startStr.slice(0, 10)
              : event.startStr.slice(0, 19),
            end: event.allDay
              ? event.endStr.slice(0, 10)
              : event.endStr.slice(0, 19),
            all_day: event.allDay,
            color: event.backgroundColor,
            description: event.extendedProps.description || "",
          },
          "PUT",
        );
      }
      notify(uiText("日程已更新"));
      await changed();
    } catch (e) {
      revert();
      notify((e as Error).message, true);
    }
  }

  return (
    <div className="calendar-panel panel">
      <div className="calendar-toolbar">
        <div className="calendar-controls">
          <div className="calendar-title">
            <h2>{title}</h2>
          </div>
          <button
            className="icon-button"
            aria-label={uiText("上一个日期范围")}
            onClick={() => calendar.current?.getApi().prev()}
          >
            <ChevronLeft size={19} />
          </button>
          <button
            className="icon-button"
            aria-label={uiText("下一个日期范围")}
            onClick={() => calendar.current?.getApi().next()}
          >
            <ChevronRight size={19} />
          </button>
          <button
            className="button secondary small"
            onClick={() => calendar.current?.getApi().gotoDate(data.today)}
          >
            {uiText("今天")}
          </button>
        </div>
        <div className="calendar-controls">
          <div className="segmented">
            {[
              ["dayGridMonth", uiText("月")],
              ["timeGridWeek", uiText("周")],
              ["timeGridDay", uiText("日")],
            ].map(([value, text]) => (
              <button
                key={value}
                className={view === value ? "active" : ""}
                onClick={() => switchView(value)}
              >
                {uiText(text)}
              </button>
            ))}
          </div>
          <button
            className="button secondary small"
            onClick={() => edit({ kind: "event" })}
          >
            <Plus size={16} />
            {uiText("日历事件")}
          </button>
        </div>
      </div>
      <div className={`calendar-stage calendar-stage-${view}`}>
      <FullCalendar
        ref={calendar}
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        locale={getLanguage() === "zh" ? zhLocale : "en"}
        firstDay={1}
        initialDate={data.today}
        initialView="timeGridWeek"
        headerToolbar={false}
        height={view === "dayGridMonth" ? "auto" : 740}
        dayMaxEvents={3}
        editable
        selectable
        nowIndicator
        now={zonedInput(new Date().toISOString(), data.settings.timezone)}
        eventStartEditable
        eventDurationEditable
        fixedWeekCount={false}
        slotMinTime="00:00:00"
        slotMaxTime="24:00:00"
        scrollTime="06:00:00"
        slotDuration="00:30:00"
        slotLabelInterval="01:00:00"
        slotLabelFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
        allDayText={uiText("全天")}
        dayHeaderContent={(info) =>
          info.view.type === "dayGridMonth" ? (
            info.text
          ) : (
            <span className={`calendar-day-head${info.isToday ? " is-today" : ""}`}>
              <span>{new Intl.DateTimeFormat(browserLocale(), { weekday: "short" }).format(info.date)}</span>
              <span className="calendar-day-number">{info.date.getDate()}</span>
            </span>
          )
        }
        buttonText={{ today: uiText("今天"), month: uiText("月"), week: uiText("周"), day: uiText("日") }}
        eventTimeFormat={{ hour: "2-digit", minute: "2-digit", hour12: false }}
        datesSet={(info) => setTitle(info.view.title)}
        events={fetchEvents}
        dateClick={(info) =>
          edit({
            kind: "task",
            defaults: {
              date: info.dateStr.slice(0, 10),
              start_time: info.allDay ? "" : info.dateStr.slice(11, 16),
            },
          })
        }
        eventClick={(info) => {
          const task = info.event.extendedProps.task as Task | null;
          if (task) edit({ kind: "task", item: task });
          else {
            const event: CalendarEventRecord = {
              id:
                info.event.extendedProps.event_id ||
                info.event.id.replace(/^event-/, ""),
              title: info.event.title,
              start: info.event.allDay
                ? info.event.startStr.slice(0, 10)
                : info.event.startStr.slice(0, 16),
              end: info.event.allDay
                ? info.event.endStr.slice(0, 10)
                : info.event.endStr.slice(0, 16),
              all_day: info.event.allDay,
              description: info.event.extendedProps.description || "",
              color: info.event.backgroundColor || "#acbcf7",
            };
            edit({ kind: "event", item: event });
          }
        }}
        eventDrop={move}
        eventResize={move}
        eventDidMount={(info) => {
          info.el.style.setProperty(
            "--calendar-accent",
            info.event.backgroundColor || "#acbcf7",
          );
        }}
        eventClassNames={(info) =>
          info.event.extendedProps.task?.status === "completed"
            ? ["calendar-completed"]
            : info.event.extendedProps.task?.status === "cancelled"
              ? ["calendar-cancelled"]
              : []
        }
      />
      </div>
    </div>
  );
}
