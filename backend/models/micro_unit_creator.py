from sqlalchemy import Column, Text, Integer, DateTime, func, ForeignKey
from sqlalchemy.orm import relationship
from backend.db.base import Base

class MicroUnitCreator(Base):
    __tablename__ = "micro_unit_creators"
    id = Column(Integer, primary_key=True, autoincrement=True)
    micro_unit_id = Column(Integer, ForeignKey("micro_units.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
