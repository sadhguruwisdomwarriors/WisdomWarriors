from sqlalchemy import Column, Integer, Text, DateTime, UniqueConstraint, func
from backend.db.base import Base


class ProfileHandleHistory(Base):
    __tablename__ = "profile_handle_history"
    __table_args__ = (
        UniqueConstraint("profile_id", "handle", name="uq_profile_handle_history_profile_id_handle"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(Text, nullable=False, index=True)  # Soft ref to Profile.id (Instagram numeric ID)
    handle = Column(Text, nullable=False, index=True)      # Lowercased normalized handle
    created_at = Column(DateTime(timezone=True), server_default=func.now())
