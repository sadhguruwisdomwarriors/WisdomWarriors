from sqlalchemy import Column, Text, Integer, DateTime, func, ForeignKey
from backend.db.base import Base

class MicroUnitChannel(Base):
    __tablename__ = "micro_unit_channels"
    id = Column(Integer, primary_key=True, autoincrement=True)
    micro_unit_id = Column(Integer, ForeignKey("micro_units.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(Text, default="INSTAGRAM", nullable=False) # "INSTAGRAM" or "YOUTUBE"
    instagram_id = Column(Text, nullable=True)
    username = Column(Text, nullable=False) # IG handle or YouTube channel ID / handle
    channel_title = Column(Text, nullable=True) # Display title for YouTube channel or creator
    creator_name = Column(Text, nullable=True) # Grouping creator name (e.g. Sanjeev Yogii)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
