# games/service.py
from sqlalchemy import select, or_
from games.models import Game, GameLanguage
from games.schemas import GameOut, GameSessionOut, QuestionOut, QuestionAdditionalInfo
from games.constants import GAME_TYPE_REQUIREMENTS, GAME_TASKS
from words.service import count_saved_words, get_words_for_session
from games.session_store import create_game_session

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

def start_word_recall_session(session, user_id: int, game, language: str) -> GameSessionOut:
    words_per_session = game.default_config.get("words_per_session", 10)
    requirements = GAME_TYPE_REQUIREMENTS.get(game.game_type, {})

    words = get_words_for_session(session, user_id, language, words_per_session, **requirements)

    answers = [{"word_id": w.id, "answer": w.name} for w in words]
    session_id = create_game_session(answers)

    questions = [
        QuestionOut(
            id=w.id,
            question=w.defs[:3],
            additional_info=QuestionAdditionalInfo(
                audio_url=w.audio_url,
                img_url=w.img_url,
                examples=w.examples or None,
            ),
        )
        for w in words
    ]

    result = GameSessionOut(task=GAME_TASKS[game.game_type], session_id=session_id, questions=questions)

    print(result)

    return result