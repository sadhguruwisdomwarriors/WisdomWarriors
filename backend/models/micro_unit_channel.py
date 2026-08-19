from sqlalchemy import Column, Text, Integer, DateTime, func, ForeignKey
from backend.db.base import Base

class MicroUnitChannel(Base):
    __tablename__ = "micro_unit_channels"
    id = Column(Integer, primary_key=True, autoincrement=True)
    micro_unit_id = Column(Integer, ForeignKey("micro_units.id", ondelete="CASCADE"), nullable=False, index=True)
    instagram_id = Column(Text, nullable=False)
    username = Column(Text, nullable=False)
    creator_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
