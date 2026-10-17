"""Create or update the rows in `games` / `game_languages` from `GAME_DEFINITIONS`.

Run with `python -m games.seed`. Safe to run repeatedly.
"""
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import AsyncSessionLocal, engine
from games.models import Game, GameLanguage
from games.seed_data import GAME_DEFINITIONS

# Relationships between models are resolved by class name across modules, so
# every model module must be imported before the first query.
import users.models  # noqa: F401
import words.models  # noqa: F401


async def sync_games(db: AsyncSession) -> None:
    for definition in GAME_DEFINITIONS:
        all_languages = definition["all_languages"]
        languages = definition["languages"]
        game = await db.scalar(
            select(Game)
            .options(selectinload(Game.languages))
            .where(Game.slug == definition["slug"])
        )

        if game is None:
            game = Game(
                slug=definition["slug"],
                title=definition["title"],
                description=definition["description"],
                game_type=definition["game_type"],
                order_num=definition["order_num"],
                all_languages=all_languages,
                default_config=definition["default_config"],
                # Set explicitly so the collection counts as loaded; otherwise
                # reading it after the flush would lazy-load.
                languages=[],
            )
            db.add(game)
            await db.flush()
        else:
            game.title = definition["title"]
            game.description = definition["description"]
            game.order_num = definition["order_num"]
            game.all_languages = all_languages
            game.default_config = definition["default_config"]

        wanted_langs = set() if all_languages else set(languages)
        existing_langs = {gl.language for gl in game.languages}

        for lang in wanted_langs - existing_langs:
            db.add(GameLanguage(game_id=game.id, language=lang))
        for gl in list(game.languages):
            if gl.language not in wanted_langs:
                await db.delete(gl)

    await db.commit()


async def main() -> None:
    async with AsyncSessionLocal() as db:
        await sync_games(db)
    await engine.dispose()
    print(f"Synced {len(GAME_DEFINITIONS)} games.")


if __name__ == "__main__":
    asyncio.run(main())
