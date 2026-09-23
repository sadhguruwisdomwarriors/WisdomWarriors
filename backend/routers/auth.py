from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from backend.db.engine import get_db
from backend.models.user import User
from backend.models.micro_unit import MicroUnit
from backend.services.auth_service import hash_password, verify_password, create_access_token, get_current_user, require_admin, get_optional_user

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = None
    full_name: str
    role: str = "POC"
    status: str = "ACTIVE"

class ApproveUserRequest(BaseModel):
    micro_unit_id: Optional[int] = None

@router.post("/register")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    clean_email = request.email.strip().lower()
    clean_name = request.full_name.strip()
    
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")
    if not clean_name:
        raise HTTPException(status_code=400, detail="Full name is required")

    result = await db.execute(select(User).where(User.email == clean_email))
    existing_user = result.scalars().first()
    
    if existing_user:
        user_status = getattr(existing_user, "status", "ACTIVE")
        if user_status == "PENDING":
            raise HTTPException(
                status_code=400,
                detail="A registration request with this email is already submitted and awaiting Admin approval."
            )
        raise HTTPException(status_code=400, detail="Email is already registered. Please log in.")

    hashed_password = hash_password(request.password)
    new_user = User(
        email=clean_email,
        password_hash=hashed_password,
        full_name=clean_name,
        role="POC",
        status="PENDING"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    return {
        "status": "pending_approval",
        "message": "Registration successful! Your request has been sent to the Admin for approval. Once approved, you will be able to log in.",
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role,
            "status": new_user.status
        }
    }

@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    clean_email = request.email.strip().lower()
    result = await db.execute(select(User).where(User.email == clean_email))
    user = result.scalars().first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    
    user_status = getattr(user, "status", "ACTIVE")
    if user_status == "PENDING":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your registration request is pending Admin approval. You will be able to log in once an Admin approves your account."
        )
    if user_status == "REJECTED":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account registration request was declined by the Admin."
        )

    access_token = create_access_token(data={"sub": user.email})
    return {
        "access_token": access_token, 
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "status": user_status
        }
    }

@router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "status": getattr(current_user, "status", "ACTIVE")
    }

@router.get("/pending-registrations")
async def list_pending_registrations(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    result = await db.execute(select(User).where(User.status == "PENDING").order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "status": u.status,
            "created_at": u.created_at.isoformat() if u.created_at else None
        } for u in users
    ]

@router.post("/approve-user/{id}")
async def approve_user(id: int, request: ApproveUserRequest = ApproveUserRequest(), db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.status = "ACTIVE"
    
    # If a micro unit was chosen, assign this POC to the unit
    assigned_unit_name = None
    if request.micro_unit_id:
        unit_res = await db.execute(select(MicroUnit).where(MicroUnit.id == request.micro_unit_id))
        unit = unit_res.scalars().first()
        if unit:
            unit.poc_user_id = user.id
            assigned_unit_name = unit.name

    await db.commit()
    await db.refresh(user)
    
    return {
        "status": "approved",
        "message": f"User {user.full_name} ({user.email}) has been approved and activated!",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "status": user.status
        },
        "assigned_unit": assigned_unit_name
    }

@router.post("/reject-user/{id}")
async def reject_user(id: int, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.status = "REJECTED"
    await db.commit()
    return {"status": "rejected", "message": f"Registration request for {user.email} declined."}

@router.post("/users")
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    clean_email = user.email.strip().lower()
    result = await db.execute(select(User).where(User.email == clean_email))
    if result.scalars().first():
        raise HTTPException(status_code=400, detail="Email already registered")
    
    import secrets
    raw_password = user.password.strip() if user.password and user.password.strip() else secrets.token_urlsafe(16)
    hashed_password = hash_password(raw_password)
    new_user = User(
        email=clean_email,
        password_hash=hashed_password,
        full_name=user.full_name.strip(),
        role=user.role,
        status="ACTIVE"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return {
        "id": new_user.id,
        "email": new_user.email,
        "full_name": new_user.full_name,
        "role": new_user.role,
        "status": new_user.status
    }

@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    result = await db.execute(select(User).where(User.status != "REJECTED").order_by(User.full_name.asc()))
    users = result.scalars().all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role,
            "status": getattr(u, "status", "ACTIVE")
        } for u in users
    ]

class PasswordResetRequest(BaseModel):
    email: str
    new_password: str

@router.post("/reset-password")
async def reset_user_password(req: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    clean_email = req.email.strip().lower()
    result = await db.execute(select(User).where(User.email == clean_email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="No user found with this email address")
    user.password_hash = hash_password(req.new_password)
    await db.commit()
    return {"status": "password_updated", "email": user.email}
