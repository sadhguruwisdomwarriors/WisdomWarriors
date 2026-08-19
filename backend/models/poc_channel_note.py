from sqlalchemy import Column, Text, Integer, DateTime, func, ForeignKey
from backend.db.base import Base

class PocChannelNote(Base):
    __tablename__ = "poc_channel_notes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    micro_unit_id = Column(Integer, ForeignKey("micro_units.id"), nullable=False)
    instagram_id = Column(Text, nullable=False)
    year_month = Column(Text, nullable=False)
    observation = Column(Text, nullable=True)
    action = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
