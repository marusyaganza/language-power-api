# games/seed.py
from sqlalchemy import select
from core.database import SessionLocal  # or wherever your session factory lives
from games.models import Game, GameLanguage
from games.seed_data import GAME_DEFINITIONS

def sync_games(session) -> None:
    for definition in GAME_DEFINITIONS:
        all_languages = definition["all_languages"]
        languages = definition["languages"]
        game = session.scalar(select(Game).where(Game.slug == definition["slug"]))

        if game is None:
            game = Game(
                slug=definition["slug"],
                title=definition["title"],
                description=definition["description"],
                game_type=definition["game_type"],
                order_num=definition["order_num"],
                all_languages=all_languages,
                default_config=definition["default_config"],
            )
            session.add(game)
            session.flush()
        else:
            game.title = definition["title"]
            game.description = definition["description"]
            game.order_num = definition["order_num"]
            game.all_languages = all_languages
            game.default_config = definition["default_config"]

        wanted_langs = set() if all_languages else set(languages)
        existing_langs = {gl.language for gl in game.languages}

        for lang in wanted_langs - existing_langs:
            session.add(GameLanguage(game_id=game.id, language=lang))
        for gl in list(game.languages):
            if gl.language not in wanted_langs:
                session.delete(gl)

    session.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        sync_games(session)
        print(f"Synced {len(GAME_DEFINITIONS)} games.")