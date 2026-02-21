from db.base import engine, Base
from db.models import UserSession, SavedMessage

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
