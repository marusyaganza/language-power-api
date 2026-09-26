# games/service.py
from sqlalchemy import select, or_
from games.models import Game, GameLanguage
from games.schemas import GameOut, GameSessionOut, QuestionOut, QuestionAdditionalInfo
from games.constants import GAME_TYPE_REQUIREMENTS, GAME_TASKS
from words.service import count_saved_words, get_words_for_session
from games.session_store import create_game_session
import logging
from core.database import SessionLocal
from games.models import WordProgress, ReviewLog
from games.spaced_repetition import initialize_progress, update_progress, WordProgressState
from games.scoring import AnswerGrade
logger = logging.getLogger(__name__)


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
    session_id = create_game_session(game.id, game.game_type, answers)

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


def persist_review_result(word_id: int, game_type: str, grade: AnswerGrade) -> None:
    db = SessionLocal()
    try:
        progress = (
            db.query(WordProgress)
            .filter(WordProgress.word_id == word_id, WordProgress.game_type == game_type)
            .first()
        )
        if progress is None:
            initial = initialize_progress()
            progress = WordProgress(
                word_id=word_id,
                game_type=game_type,
                is_learning=initial.is_learning,
                learning_step_index=initial.learning_step_index,
                interval_days=initial.interval_days,
                consecutive_correct=initial.consecutive_correct,
                lapses=initial.lapses,
                next_review_date=initial.next_review_date,
            )
            db.add(progress)
            db.flush()  # assigns progress.id for the ReviewLog FK below

        state = WordProgressState(
            is_learning=progress.is_learning,
            learning_step_index=progress.learning_step_index,
            interval_days=progress.interval_days,
            consecutive_correct=progress.consecutive_correct,
            lapses=progress.lapses,
            next_review_date=progress.next_review_date,
        )
        updated = update_progress(state, grade)

        progress.is_learning = updated.is_learning
        progress.learning_step_index = updated.learning_step_index
        progress.interval_days = updated.interval_days
        progress.consecutive_correct = updated.consecutive_correct
        progress.lapses = updated.lapses
        progress.next_review_date = updated.next_review_date

        db.add(ReviewLog(
            progress=progress,
            grade=grade.value,
            interval_at_review=progress.interval_days,
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to persist review result for word_id=%s, game_type=%s", word_id, game_type)
    finally:
        db.close()