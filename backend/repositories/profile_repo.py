from typing import Optional, Sequence
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.profile import Profile
from backend.models.profile_snapshot import ProfileSnapshot
from backend.models.profile_handle_history import ProfileHandleHistory


async def record_handle_history(db: AsyncSession, profile_id: str, handle: str) -> None:
    clean_handle = (handle or "").strip().lstrip("@").lower()
    if not clean_handle or not profile_id:
        return
    existing = await db.execute(
        select(ProfileHandleHistory)
        .where(ProfileHandleHistory.profile_id == profile_id)
        .where(func.lower(ProfileHandleHistory.handle) == clean_handle)
        .limit(1)
    )
    if existing.scalar_one_or_none() is None:
        db.add(ProfileHandleHistory(profile_id=profile_id, handle=clean_handle))
        await db.flush()


async def upsert_profile(db: AsyncSession, data: dict) -> Profile:
    profile_id = str(data.get("id", "")).strip()
    new_username = data.get("username", "").strip()

    profile = await db.get(Profile, profile_id) if profile_id else None
    if profile is None:
        profile = Profile(**data)
        db.add(profile)
    else:
        old_username = profile.username
        for k, v in data.items():
            setattr(profile, k, v)
        if old_username:
            await record_handle_history(db, profile_id, old_username)

    await db.flush()
    if profile_id and new_username:
        await record_handle_history(db, profile_id, new_username)
    return profile


async def get_profile_by_username(db: AsyncSession, username: str) -> Optional[Profile]:
    clean_name = (username or "").strip().lstrip("@").lower()
    result = await db.execute(select(Profile).where(func.lower(Profile.username) == clean_name))
    return result.scalar_one_or_none()


async def get_profile_by_handle_or_history(db: AsyncSession, handle: str) -> Optional[Profile]:
    clean_handle = (handle or "").strip().lstrip("@").lower()
    if not clean_handle:
        return None

    # First check profiles.username
    direct_match = await get_profile_by_username(db, clean_handle)
    if direct_match is not None:
        return direct_match

    # Second check profile_handle_history table
    history_match = await db.execute(
        select(ProfileHandleHistory.profile_id)
        .where(func.lower(ProfileHandleHistory.handle) == clean_handle)
        .limit(1)
    )
    profile_id = history_match.scalar_one_or_none()
    if profile_id:
        return await db.get(Profile, profile_id)
    return None


async def list_profiles(
    db: AsyncSession,
    search: Optional[str] = None,
    verified: Optional[bool] = None,
    business: Optional[bool] = None,
    followers_min: Optional[int] = None,
    followers_max: Optional[int] = None,
    category: Optional[str] = None,
    sort: str = "followers_count",
    limit: int = 50,
    offset: int = 0,
) -> tuple[Sequence[Profile], int]:
    q = select(Profile)
    if search:
        term = f"%{search}%"
        q = q.where(or_(Profile.username.ilike(term), Profile.full_name.ilike(term)))
    if verified is not None:
        q = q.where(Profile.is_verified == verified)
    if business is not None:
        q = q.where(Profile.is_business_account == business)
    if followers_min is not None:
        q = q.where(Profile.followers_count >= followers_min)
    if followers_max is not None:
        q = q.where(Profile.followers_count <= followers_max)
    if category:
        q = q.where(Profile.business_category == category)

    count_result = await db.execute(select(func.count()).select_from(q.subquery()))
    total = count_result.scalar_one()

    sort_col = getattr(Profile, sort, Profile.followers_count)
    q = q.order_by(sort_col.desc()).limit(limit).offset(offset)
    result = await db.execute(q)
    return result.scalars().all(), total


async def get_snapshots(db: AsyncSession, profile_id: str) -> Sequence[ProfileSnapshot]:
    result = await db.execute(
        select(ProfileSnapshot)
        .where(ProfileSnapshot.profile_id == profile_id)
        .order_by(ProfileSnapshot.scraped_at)
    )
    return result.scalars().all()


async def insert_snapshot(db: AsyncSession, data: dict) -> ProfileSnapshot:
    snap = ProfileSnapshot(**data)
    db.add(snap)
    await db.flush()
    return snap
