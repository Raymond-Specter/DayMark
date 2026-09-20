"""One-shot entry point for Task Scheduler/cron. Exits after one transaction."""
from .database import SessionLocal
from .services.reminder import ReminderService
from .services.scheduler import SchedulerService


def main():
    with SessionLocal() as db:
        created = SchedulerService(db).materialize()
        delivered = ReminderService(db).dispatch()
        db.commit()
        print(f"Created {created} tasks; queued {delivered} in-app notifications.")


if __name__ == "__main__":
    main()
