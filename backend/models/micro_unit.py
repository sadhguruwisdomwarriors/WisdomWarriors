from sqlalchemy import Column, Text, Integer, DateTime, func, ForeignKey
from backend.db.base import Base

class MicroUnit(Base):
    __tablename__ = "micro_units"
    id = Column(Integer, primary_key=True, autoincrement=True)
    unit_number = Column(Integer, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    poc_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(Text, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
