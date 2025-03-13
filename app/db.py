from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
import os
import uuid
import logging
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime

# Get logger
logger = logging.getLogger(__name__)

# Get database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

# Log the database configuration
if DATABASE_URL.startswith("sqlite"):
    logger.info(f"Using SQLite database: {DATABASE_URL}")
    # SQLite specific configuration
    connect_args = {"check_same_thread": False}
else:
    logger.info(f"Using PostgreSQL database (connection string hidden for security)")
    # PostgreSQL doesn't need special connect_args
    connect_args = {}

Base = declarative_base()

# Create engine with appropriate configuration
try:
    engine = create_async_engine(
        DATABASE_URL, 
        echo=False,
        connect_args=connect_args
    )
    logger.info("Database engine created successfully")
except Exception as e:
    logger.error(f"Error creating database engine: {str(e)}")
    raise

AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def create_db_and_tables():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {str(e)}")
        raise

async def get_async_session():
    try:
        async with AsyncSessionLocal() as session:
            yield session
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        raise

# User Model
class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"
    # Additional fields can be added here if desired

# Stock Model
class Stock(Base):
    __tablename__ = "stocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    symbol = Column(String, nullable=False)

# Password Reset Model
class PasswordReset(Base):
    __tablename__ = "password_resets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    token = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.now) 