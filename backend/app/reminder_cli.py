"""One-shot entry point for Task Scheduler/cron. Exits after one transaction."""
from .database import SessionLocal, tenant_factory
from .runtime import cloud_enabled
from .services.reminder import ReminderService
from .services.scheduler import SchedulerService


def main():
    factories = [SessionLocal]
    if cloud_enabled():
        from .accounts import user_ids
        factories = [tenant_factory(user_id) for user_id in user_ids()]
    for factory in factories:
        with factory() as db:
            created = SchedulerService(db).materialize()
            delivered = ReminderService(db).dispatch()
            db.commit()
            print(f"Created {created} tasks; queued {delivered} in-app notifications.")


if __name__ == "__main__":
    main()
