from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
from backend.config import get_settings
from backend.db.engine import AsyncSessionLocal, create_tables
from backend.repositories.scrape_profile_repo import ensure_scrape_profiles_seeded
from backend.repositories.scrape_run_repo import fail_incomplete_runs
from backend.services.scheduler.setup import start_scheduler, stop_scheduler
from backend.services.scheduler.jobs import load_all_schedules
from backend.services.scrape_service import resume_incomplete_runs_on_startup
from backend.routers import scrape, schedules, profiles, posts, analytics, chat, auth, micro_units


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    settings = get_settings()
    try:
        with open(settings.profiles_file, encoding="utf-8") as f:
            usernames = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        usernames = []
    async with AsyncSessionLocal() as db:
        await ensure_scrape_profiles_seeded(db, usernames)
        # Ensure default admin user
        from sqlalchemy import select
        from backend.models.user import User
        from backend.services.auth_service import hash_password
        admin_res = await db.execute(select(User).where(User.email == "sadhguruwisdomwarriors@gmail.com"))
        if not admin_res.scalars().first():
            old_admin = await db.execute(select(User).where(User.email == "admin@wisdomwarriors.com"))
            old_user = old_admin.scalars().first()
            if old_user:
                old_user.email = "sadhguruwisdomwarriors@gmail.com"
            else:
                default_admin = User(
                    email="sadhguruwisdomwarriors@gmail.com",
                    password_hash=hash_password("admin123"),
                    full_name="Admin",
                    role="ADMIN"
                )
                db.add(default_admin)
        await db.commit()

    resumed_runs = 0
    if settings.resume_incomplete_scrapes_on_startup:
        resumed_runs = await resume_incomplete_runs_on_startup()
        if resumed_runs:
            logger.info("Queued %d incomplete scrape run(s) for auto-resume.", resumed_runs)
    else:
        async with AsyncSessionLocal() as db:
            await fail_incomplete_runs(db, "Server restarted while scrape was in progress")
            await db.commit()

    start_scheduler()
    await load_all_schedules()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Instagram Analytics API", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in [scrape.router, schedules.router, profiles.router, posts.router, analytics.router, chat.router, auth.router, micro_units.router]:
        app.include_router(router)
    return app


app = create_app()
