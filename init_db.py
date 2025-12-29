import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from models import Base
import os

DATABASE_URL = "sqlite+aiosqlite:///./omnipong.db"

async def init_db():
    engine = create_async_engine(DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Database initialized successfully at omnipong.db")

if __name__ == "__main__":
    asyncio.run(init_db())
