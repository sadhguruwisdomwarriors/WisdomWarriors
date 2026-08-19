from sqlalchemy import Column, Text, Integer, DateTime, func
from backend.db.base import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(Text, unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False)
    role = Column(Text, default="POC")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
