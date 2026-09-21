from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from collections import defaultdict
from backend.db.engine import get_db
from backend.models.user import User
from backend.models.micro_unit import MicroUnit
from backend.models.micro_unit_creator import MicroUnitCreator
from backend.models.micro_unit_channel import MicroUnitChannel
from backend.models.monthly_channel_metric import MonthlyChannelMetric
from backend.models.scrape_run import ScrapeRun
from backend.models.profile import Profile
from backend.models.scrape_profile import ScrapeProfile
from backend.services.auth_service import get_current_user, require_admin, get_optional_user
from backend.services.monthly_calculation_service import calculate_monthly_metrics
from backend.services.youtube_read_service import fetch_available_youtube_channels, calculate_youtube_monthly_metrics

router = APIRouter(prefix="/api/micro-units", tags=["micro-units"])

class MicroUnitCreate(BaseModel):
    unit_number: int
    name: str

class MicroUnitUpdate(BaseModel):
    name: Optional[str] = None
    poc_user_id: Optional[int] = None

class CreatorAdd(BaseModel):
    name: str

class ChannelAdd(BaseModel):
    creator_id: Optional[int] = None
    platform: Optional[str] = "INSTAGRAM" # "INSTAGRAM" or "YOUTUBE"
    username: str
    instagram_id: Optional[str] = None
    creator_name: Optional[str] = None
    channel_title: Optional[str] = None

class MonthCalculation(BaseModel):
    month: int
    snapshot1_run_id: Optional[int] = None
    snapshot2_run_id: Optional[int] = None

class CalculateRequest(BaseModel):
    year: int
    months: List[MonthCalculation]

@router.get("")
async def list_micro_units(db: AsyncSession = Depends(get_db), current_user: Optional[User] = Depends(get_optional_user)):
    result = await db.execute(select(MicroUnit).order_by(MicroUnit.unit_number.asc()))
    units = result.scalars().all()
    response = []
    for unit in units:
        # Fetch creators
        creators_res = await db.execute(
            select(MicroUnitCreator).where(MicroUnitCreator.micro_unit_id == unit.id).order_by(MicroUnitCreator.name.asc())
        )
        creators = creators_res.scalars().all()

        channels_result = await db.execute(select(MicroUnitChannel).where(MicroUnitChannel.micro_unit_id == unit.id))
        channels = channels_result.scalars().all()
        
        poc = None
        poc_name = None
        if unit.poc_user_id:
            user_result = await db.execute(select(User).where(User.id == unit.poc_user_id))
            user = user_result.scalars().first()
            if user:
                poc_name = user.full_name
                poc = {"id": user.id, "full_name": user.full_name, "email": user.email}
        
        response.append({
            "id": unit.id,
            "unit_number": unit.unit_number,
            "name": unit.name,
            "status": unit.status,
            "poc_user_id": unit.poc_user_id,
            "poc_name": poc_name,
            "poc": poc,
            "creators": [{"id": cr.id, "name": cr.name} for cr in creators],
            "channels": [
                {
                    "id": c.id,
                    "creator_id": getattr(c, "creator_id", None),
                    "platform": getattr(c, "platform", "INSTAGRAM") or "INSTAGRAM",
                    "instagram_id": c.instagram_id,
                    "username": c.username,
                    "channel_title": getattr(c, "channel_title", None) or c.username,
                    "creator_name": c.creator_name or c.username
                } 
                for c in channels
            ]
        })
    return response

@router.post("")
async def create_micro_unit(request: MicroUnitCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    unit = MicroUnit(unit_number=request.unit_number, name=request.name)
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return unit

@router.put("/{id}")
async def update_micro_unit(id: int, request: MicroUnitUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    result = await db.execute(select(MicroUnit).where(MicroUnit.id == id))
    unit = result.scalars().first()
    if not unit:
        raise HTTPException(status_code=404, detail="Micro Unit not found")
    
    if request.name is not None:
        unit.name = request.name
    if request.poc_user_id is not None:
        unit.poc_user_id = request.poc_user_id
    await db.commit()
    return {"status": "updated"}

@router.delete("/{id}")
async def delete_micro_unit(id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    result = await db.execute(select(MicroUnit).where(MicroUnit.id == id))
    unit = result.scalars().first()
    if not unit:
        raise HTTPException(status_code=404, detail="Micro Unit not found")
    
    await db.delete(unit)
    await db.commit()
    return {"status": "deleted"}

@router.post("/{id}/creators")
async def add_creator(id: int, request: CreatorAdd, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    clean_name = request.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Creator name cannot be empty")
    creator = MicroUnitCreator(micro_unit_id=id, name=clean_name)
    db.add(creator)
    await db.commit()
    await db.refresh(creator)
    return {"id": creator.id, "name": creator.name, "micro_unit_id": creator.micro_unit_id}

@router.delete("/{id}/creators/{creator_id}")
async def delete_creator(id: int, creator_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    result = await db.execute(select(MicroUnitCreator).where(MicroUnitCreator.id == creator_id, MicroUnitCreator.micro_unit_id == id))
    creator = result.scalars().first()
    if not creator:
        raise HTTPException(status_code=404, detail="Creator not found")
    # Delete channels associated with this creator
    await db.execute(delete(MicroUnitChannel).where(MicroUnitChannel.creator_id == creator_id))
    await db.delete(creator)
    await db.commit()
    return {"status": "deleted"}

@router.get("/profiles")
async def list_available_profiles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Profile).order_by(Profile.username.asc()))
    profiles = result.scalars().all()
    profiles_dict = {
        p.username.lower(): {
            "id": p.id,
            "username": p.username,
            "creator_name": p.full_name or p.username
        }
        for p in profiles
    }
    
    sp_result = await db.execute(select(ScrapeProfile).order_by(ScrapeProfile.username.asc()))
    for sp in sp_result.scalars().all():
        u_key = sp.username.lower()
        if u_key not in profiles_dict:
            profiles_dict[u_key] = {
                "id": sp.instagram_id or sp.username,
                "username": sp.username,
                "creator_name": sp.username
            }
            
    return sorted(list(profiles_dict.values()), key=lambda x: x["username"].lower())

@router.get("/youtube-channels")
async def list_available_yt_channels():
    return await fetch_available_youtube_channels()

@router.get("/configured-runs")
async def get_configured_runs(year: int = Query(...), db: AsyncSession = Depends(get_db)):
    prefix = f"{year}-"
    result = await db.execute(
        select(
            MonthlyChannelMetric.year_month,
            MonthlyChannelMetric.snapshot1_run_id,
            MonthlyChannelMetric.snapshot2_run_id
        )
        .where(MonthlyChannelMetric.year_month.startswith(prefix))
        .order_by(MonthlyChannelMetric.calculated_at.desc())
    )
    rows = result.all()
    configured = {}
    for row in rows:
        ym, s1, s2 = row
        try:
            m = int(ym.split("-")[1])
            if m not in configured and s1 is not None and s2 is not None:
                configured[m] = {
                    "snapshot1_run_id": s1,
                    "snapshot2_run_id": s2
                }
        except Exception:
            continue
    return configured

@router.post("/{id}/channels")
async def add_channel(id: int, request: ChannelAdd, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    platform = (request.platform or "INSTAGRAM").upper()
    clean_username = request.username.strip()
    if platform == "INSTAGRAM":
        clean_username = clean_username.lstrip("@")
    
    instagram_id = request.instagram_id
    creator_name = request.creator_name
    creator_id = request.creator_id
    channel_title = request.channel_title
    
    # If creator_id is provided, get the creator name
    if creator_id:
        cr_res = await db.execute(select(MicroUnitCreator).where(MicroUnitCreator.id == creator_id))
        cr_obj = cr_res.scalars().first()
        if cr_obj:
            creator_name = cr_obj.name
    elif creator_name and creator_name.strip():
        # Check if creator already exists by name in this micro unit
        clean_cr_name = creator_name.strip()
        cr_res = await db.execute(select(MicroUnitCreator).where(MicroUnitCreator.micro_unit_id == id, MicroUnitCreator.name.ilike(clean_cr_name)))
        cr_obj = cr_res.scalars().first()
        if not cr_obj:
            cr_obj = MicroUnitCreator(micro_unit_id=id, name=clean_cr_name)
            db.add(cr_obj)
            await db.flush()
        creator_id = cr_obj.id
        creator_name = cr_obj.name
    
    if platform == "INSTAGRAM":
        profile_result = await db.execute(select(Profile).where(Profile.username.ilike(clean_username)))
        profile = profile_result.scalars().first()
        if profile:
            if not instagram_id:
                instagram_id = profile.id
            if not creator_name:
                creator_name = profile.full_name
            if not channel_title:
                channel_title = f"@{profile.username}"
                
        if not instagram_id:
            instagram_id = clean_username
        if not channel_title:
            channel_title = f"@{clean_username}"
    else:
        # YouTube
        if not channel_title:
            channel_title = clean_username
        if not instagram_id:
            instagram_id = clean_username

    channel = MicroUnitChannel(
        micro_unit_id=id,
        creator_id=creator_id,
        platform=platform,
        instagram_id=instagram_id,
        username=clean_username,
        channel_title=channel_title or clean_username,
        creator_name=creator_name or channel_title or clean_username
    )
    db.add(channel)
    await db.commit()
    await db.refresh(channel)
    return channel

@router.delete("/{id}/channels/{channel_id}")
async def remove_channel(id: int, channel_id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    result = await db.execute(select(MicroUnitChannel).where(MicroUnitChannel.id == channel_id, MicroUnitChannel.micro_unit_id == id))
    channel = result.scalars().first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")
    
    await db.delete(channel)
    await db.commit()
    return {"status": "deleted"}

@router.delete("/calculations")
async def clear_calculations(year: int = Query(...), month: Optional[int] = Query(None), db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    if month:
        year_month_str = f"{year}-{month:02d}"
        await db.execute(delete(MonthlyChannelMetric).where(MonthlyChannelMetric.year_month == year_month_str))
    else:
        prefix = f"{year}-"
        await db.execute(delete(MonthlyChannelMetric).where(MonthlyChannelMetric.year_month.startswith(prefix)))
    await db.commit()
    return {"status": "cleared"}

@router.post("/calculate")
async def calculate_metrics(request: CalculateRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    submitted_months = set()
    results = []
    for m in request.months:
        if m.snapshot1_run_id is not None and m.snapshot2_run_id is not None:
            submitted_months.add(m.month)
            res = await calculate_monthly_metrics(db, request.year, m.month, m.snapshot1_run_id, m.snapshot2_run_id)
            results.append({"month": m.month, "result": res})
        elif (m.snapshot1_run_id is not None and m.snapshot2_run_id is None) or (m.snapshot1_run_id is None and m.snapshot2_run_id is not None):
            raise HTTPException(status_code=400, detail=f"Both snapshot1_run_id and snapshot2_run_id required for month {m.month}")
        
    # Delete records for any months of this year that are NOT in submitted_months
    for month_idx in range(1, 13):
        if month_idx not in submitted_months:
            year_month_str = f"{request.year}-{month_idx:02d}"
            await db.execute(
                delete(MonthlyChannelMetric).where(MonthlyChannelMetric.year_month == year_month_str)
            )
            
    await db.commit()
    return {"status": "completed", "results": results}

@router.get("/{id}/dashboard")
async def get_dashboard(id: int, year: int = Query(...), db: AsyncSession = Depends(get_db), current_user: Optional[User] = Depends(get_optional_user)):
    unit_result = await db.execute(select(MicroUnit).where(MicroUnit.id == id))
    unit = unit_result.scalars().first()
    if not unit:
        raise HTTPException(status_code=404, detail="Micro Unit not found")
        
    poc_name = None
    if unit.poc_user_id:
        user_result = await db.execute(select(User).where(User.id == unit.poc_user_id))
        user = user_result.scalars().first()
        if user:
            poc_name = user.full_name

    # Fetch explicit creators
    creators_res = await db.execute(
        select(MicroUnitCreator).where(MicroUnitCreator.micro_unit_id == id).order_by(MicroUnitCreator.name.asc())
    )
    explicit_creators = creators_res.scalars().all()

    channels_result = await db.execute(select(MicroUnitChannel).where(MicroUnitChannel.micro_unit_id == id))
    channels = channels_result.scalars().all()
    
    # Identify available months from Instagram calculations
    available_months_set = set()
    prefix = f"{year}-"
    ig_metrics_res = await db.execute(
        select(MonthlyChannelMetric).where(MonthlyChannelMetric.year_month.startswith(prefix))
    )
    ig_all_metrics = ig_metrics_res.scalars().all()
    ig_metrics_map = defaultdict(dict) # [instagram_id][year_month] -> metric
    for m in ig_all_metrics:
        available_months_set.add(m.year_month)
        ig_metrics_map[m.instagram_id][m.year_month] = m

    available_months = sorted(list(available_months_set)) if available_months_set else []

    # Identify YouTube channels in this unit
    yt_channels = [c for c in channels if (getattr(c, "platform", "INSTAGRAM") or "INSTAGRAM").upper() == "YOUTUBE"]
    yt_channel_ids = [c.username for c in yt_channels]

    # Pre-calculate YouTube monthly metrics on-the-fly for available months
    yt_metrics_cache = {} # [year_month][channel_username] -> {views, video_count, title}
    for ym in available_months:
        try:
            m_num = int(ym.split("-")[1])
            yt_res = await calculate_youtube_monthly_metrics(yt_channel_ids, year, m_num)
            yt_metrics_cache[ym] = yt_res
        except Exception:
            yt_metrics_cache[ym] = {}

    # Group channels by creator
    # If explicit creators exist, initialize them
    creator_groups = {}
    for cr in explicit_creators:
        creator_groups[cr.name] = []

    # Assign channels to creator groups
    for c in channels:
        c_name = (c.creator_name or c.channel_title or c.username or "Unassigned Creator").strip()
        if c_name not in creator_groups:
            creator_groups[c_name] = []
        creator_groups[c_name].append(c)

    creators_data = []
    unit_totals = defaultdict(lambda: {"total_views": 0.0, "yt_views": 0.0, "ig_views": 0.0, "reels": 0, "videos": 0})

    for creator_name, c_list in creator_groups.items():
        months_dict = {}
        for ym in available_months:
            yt_ch_data = []
            ig_ch_data = []
            creator_yt_views = 0.0
            creator_ig_views = 0.0
            creator_videos = 0
            creator_reels = 0

            for ch in c_list:
                platform = (getattr(ch, "platform", "INSTAGRAM") or "INSTAGRAM").upper()
                if platform == "YOUTUBE":
                    yt_metric = yt_metrics_cache.get(ym, {}).get(ch.username, {})
                    v_views = float(yt_metric.get("views", 0.0) or 0.0)
                    v_count = int(yt_metric.get("video_count", 0) or 0)
                    title = yt_metric.get("title") or getattr(ch, "channel_title", None) or ch.username
                    creator_yt_views += v_views
                    creator_videos += v_count
                    yt_ch_data.append({
                        "id": ch.id,
                        "channel_id": ch.username,
                        "title": title,
                        "views": v_views,
                        "videos": v_count,
                    })
                else:
                    # Instagram
                    metric = ig_metrics_map.get(ch.instagram_id, {}).get(ym)
                    if not metric:
                        metric = ig_metrics_map.get(ch.username, {}).get(ym)
                    
                    ig_views = float(metric.monthly_views if metric else 0.0)
                    ig_reels = int((metric.reels_count if metric and metric.reels_count is not None else (metric.post_count if metric else 0)) or 0)
                    creator_ig_views += ig_views
                    creator_reels += ig_reels
                    ig_ch_data.append({
                        "id": ch.id,
                        "username": ch.username,
                        "creator_name": ch.creator_name or ch.username,
                        "views": ig_views,
                        "reels": ig_reels,
                    })

            total_views = creator_yt_views + creator_ig_views
            months_dict[ym] = {
                "total_views": total_views,
                "yt_views": creator_yt_views,
                "ig_views": creator_ig_views,
                "videos": creator_videos,
                "reels": creator_reels,
                "yt_channels": yt_ch_data,
                "ig_channels": ig_ch_data,
            }

            # Accumulate to unit totals
            unit_totals[ym]["total_views"] += total_views
            unit_totals[ym]["yt_views"] += creator_yt_views
            unit_totals[ym]["ig_views"] += creator_ig_views
            unit_totals[ym]["videos"] += creator_videos
            unit_totals[ym]["reels"] += creator_reels

        creators_data.append({
            "creator_name": creator_name,
            "channels_count": len(c_list),
            "months": months_dict
        })

    # Legacy channels array for backwards compatibility
    channels_data = []
    for channel in channels:
        platform = (getattr(channel, "platform", "INSTAGRAM") or "INSTAGRAM").upper()
        months_data = {}
        for ym in available_months:
            if platform == "YOUTUBE":
                yt_m = yt_metrics_cache.get(ym, {}).get(channel.username, {})
                months_data[ym] = {
                    "views": float(yt_m.get("views", 0.0) or 0.0),
                    "post_count": int(yt_m.get("video_count", 0) or 0),
                    "reels_count": int(yt_m.get("video_count", 0) or 0),
                    "static_post_count": 0,
                }
            else:
                metric = ig_metrics_map.get(channel.instagram_id, {}).get(ym)
                r_count = getattr(metric, "reels_count", None) if metric else 0
                s_count = getattr(metric, "static_post_count", None) if metric else 0
                if r_count is None and metric:
                    r_count = metric.post_count or 0
                months_data[ym] = {
                    "views": (metric.monthly_views if metric else 0.0) or 0.0,
                    "post_count": (metric.post_count if metric else 0) or 0,
                    "reels_count": r_count or 0,
                    "static_post_count": s_count or 0,
                }
                
        channels_data.append({
            "id": channel.id,
            "platform": platform,
            "instagram_id": channel.instagram_id,
            "username": channel.username,
            "channel_title": getattr(channel, "channel_title", None) or channel.username,
            "creator_name": channel.creator_name or channel.username,
            "months": months_data
        })
        
    return {
        "unit": {"id": unit.id, "name": unit.name, "poc": poc_name},
        "available_months": available_months,
        "unit_totals": dict(unit_totals),
        "creators": creators_data,
        "channels": channels_data
    }

@router.get("/my-unit")
async def get_my_unit(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    result = await db.execute(select(MicroUnit).where(MicroUnit.poc_user_id == current_user.id))
    unit = result.scalars().first()
    if not unit:
        raise HTTPException(status_code=404, detail="No unit assigned")
    return {"id": unit.id, "name": unit.name}

@router.get("/scrape-runs")
async def list_scrape_runs(db: AsyncSession = Depends(get_db), current_user: Optional[User] = Depends(get_optional_user)):
    result = await db.execute(select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(50))
    runs = result.scalars().all()
    return [{"id": r.id, "started_at": r.started_at, "status": r.status} for r in runs]
