from sqlalchemy import Column, Text, Integer, Float, DateTime, func, UniqueConstraint
from backend.db.base import Base

class MonthlyChannelMetric(Base):
    __tablename__ = "monthly_channel_metrics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    instagram_id = Column(Text, nullable=False, index=True)
    username = Column(Text, nullable=False, index=True)
    year_month = Column(Text, nullable=False, index=True)
    monthly_views = Column(Float, default=0.0)
    previous_monthly_views = Column(Float, nullable=True)
    growth_percent = Column(Float, nullable=True)
    post_count = Column(Integer, default=0)
    views_per_post = Column(Float, nullable=True)
    snapshot1_run_id = Column(Integer, nullable=False)
    snapshot2_run_id = Column(Integer, nullable=False)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("instagram_id", "year_month", name="uq_channel_month"),
    )
