from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
import os, uuid, logging
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

# Logger
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

Base = declarative_base()

# Create engine
try:
    engine = create_async_engine(DATABASE_URL, echo=False, connect_args=connect_args)
except Exception as e:
    logger.error(f"Database engine error: {str(e)}")
    raise

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_db_and_tables():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.error(f"Database tables error: {str(e)}")
        raise

async def get_async_session():
    try:
        async with AsyncSessionLocal() as session:
            yield session
    except Exception as e:
        logger.error(f"Session error: {str(e)}")
        raise

# Models
class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

class Stock(Base):
    __tablename__ = "stocks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    symbol = Column(String, nullable=False)

class PasswordReset(Base):
    __tablename__ = "password_resets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    token = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.now) 