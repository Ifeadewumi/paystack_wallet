from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from datetime import datetime
import enum
from app.database import Base


class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    picture = Column(String, nullable=True)
    google_id = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    reference = Column(String, unique=True, index=True, nullable=False)
    user_id = Column(String, nullable=True)  # Optional: link to user
    amount = Column(Integer, nullable=False)  # Amount in kobo
    status = Column(SQLEnum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    authorization_url = Column(String, nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
