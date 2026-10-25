from sqlalchemy import text

from app.db import engine


async def test_database_connection() -> None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT 1"))

    assert result.scalar_one() == 1

    await engine.dispose()
