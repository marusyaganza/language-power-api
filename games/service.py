# games/service.py
from sqlalchemy import select, or_
from games.models import Game, GameLanguage
from games.schemas import GameOut
from games.constants import GAME_TYPE_REQUIREMENTS
from words.service import count_saved_words

def list_games_for_language(session, user_id, language) -> list[GameOut]:
    games = session.scalars(
        select(Game)
        .where(
            or_(
                Game.all_languages.is_(True),
                Game.id.in_(
                    select(GameLanguage.game_id).where(GameLanguage.language == language)
                ),
            )
        )
        .order_by(Game.order_num)
    ).all()

    result = []
    for g in games:
        requirements = GAME_TYPE_REQUIREMENTS.get(g.game_type, {})
        print('requirements', requirements)
        word_count = count_saved_words(session, user_id, language, **requirements)
        result.append(
            GameOut(
                id=g.id,
                slug=g.slug,
                title=g.title,
                description=g.description,
                game_type=g.game_type,
                available_word_count=word_count,
                is_enabled=word_count > 0,
            )
        )
    return result