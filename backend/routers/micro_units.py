from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from backend.db.engine import get_db
from backend.models.user import User
from backend.models.micro_unit import MicroUnit
from backend.models.micro_unit_channel import MicroUnitChannel
from backend.models.monthly_channel_metric import MonthlyChannelMetric
from backend.models.scrape_run import ScrapeRun
from backend.services.auth_service import get_current_user, require_admin, get_optional_user
from backend.services.monthly_calculation_service import calculate_monthly_metrics

router = APIRouter(prefix="/api/micro-units", tags=["micro-units"])

class MicroUnitCreate(BaseModel):
    unit_number: int
    name: str

class MicroUnitUpdate(BaseModel):
    name: Optional[str] = None
    poc_user_id: Optional[int] = None

from backend.models.profile import Profile

class ChannelAdd(BaseModel):
    username: str
    instagram_id: Optional[str] = None
    creator_name: Optional[str] = None

class MonthCalculation(BaseModel):
    month: int
    snapshot1_run_id: Optional[int] = None
    snapshot2_run_id: Optional[int] = None

class CalculateRequest(BaseModel):
    year: int
    months: List[MonthCalculation]

@router.get("")
async def list_micro_units(db: AsyncSession = Depends(get_db), current_user: Optional[User] = Depends(get_optional_user)):
    result = await db.execute(select(MicroUnit))
    units = result.scalars().all()
    response = []
    for unit in units:
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
            "channels": [{"id": c.id, "instagram_id": c.instagram_id, "username": c.username, "creator_name": c.creator_name} for c in channels]
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

@router.get("/profiles")
async def list_available_profiles(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Profile).order_by(Profile.username.asc()))
    profiles = result.scalars().all()
    return [{"id": p.id, "username": p.username, "creator_name": p.full_name or p.username} for p in profiles]

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
        .group_by(
            MonthlyChannelMetric.year_month,
            MonthlyChannelMetric.snapshot1_run_id,
            MonthlyChannelMetric.snapshot2_run_id
        )
    )
    rows = result.all()
    configured = {}
    for row in rows:
        ym, s1, s2 = row
        try:
            m = int(ym.split("-")[1])
            configured[m] = {
                "snapshot1_run_id": s1,
                "snapshot2_run_id": s2
            }
        except Exception:
            continue
    return configured

@router.post("/{id}/channels")
async def add_channel(id: int, request: ChannelAdd, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    clean_username = request.username.strip().lstrip("@")
    
    instagram_id = request.instagram_id
    creator_name = request.creator_name
    
    profile_result = await db.execute(select(Profile).where(Profile.username.ilike(clean_username)))
    profile = profile_result.scalars().first()
    if profile:
        if not instagram_id:
            instagram_id = profile.id
        if not creator_name:
            creator_name = profile.full_name
            
    if not instagram_id:
        instagram_id = clean_username
        
    channel = MicroUnitChannel(
        micro_unit_id=id,
        instagram_id=instagram_id,
        username=clean_username,
        creator_name=creator_name or clean_username
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

@router.post("/calculate")
async def calculate_metrics(request: CalculateRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    results = []
    for m in request.months:
        if m.snapshot1_run_id is None or m.snapshot2_run_id is None:
            raise HTTPException(status_code=400, detail=f"Both snapshot1_run_id and snapshot2_run_id required for month {m.month}")
        
        res = await calculate_monthly_metrics(db, request.year, m.month, m.snapshot1_run_id, m.snapshot2_run_id)
        results.append({"month": m.month, "result": res})
        
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

    channels_result = await db.execute(select(MicroUnitChannel).where(MicroUnitChannel.micro_unit_id == id))
    channels = channels_result.scalars().all()
    
    available_months = set()
    channels_data = []
    
    for channel in channels:
        metrics_result = await db.execute(
            select(MonthlyChannelMetric)
            .where((MonthlyChannelMetric.instagram_id == channel.instagram_id) & (MonthlyChannelMetric.year_month.startswith(str(year))))
        )
        metrics = metrics_result.scalars().all()
        
        months_data = {}
        for metric in metrics:
            available_months.add(metric.year_month)
            months_data[metric.year_month] = {
                "views": metric.monthly_views,
                "post_count": metric.post_count
            }
            
        channels_data.append({
            "instagram_id": channel.instagram_id,
            "username": channel.username,
            "creator_name": channel.creator_name,
            "months": months_data
        })
        
    return {
        "unit": {"id": unit.id, "name": unit.name, "poc": poc_name},
        "available_months": sorted(list(available_months)),
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
