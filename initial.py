from db.models import Base
from db.database import engine
import asyncio


async def init_db():
    async with engine.begin() as conn:
        # Drop existing tables to ensure clean schema
        await conn.run_sync(Base.metadata.drop_all)
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(init_db())
