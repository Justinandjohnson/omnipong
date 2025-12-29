import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from models import Base, RatingHistory

DATABASE_URL = "sqlite+aiosqlite:///./omnipong.db"
engine = create_async_engine(DATABASE_URL)

async def migrate():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Migration complete: rating_history table created.")

if __name__ == "__main__":
    asyncio.run(migrate())
