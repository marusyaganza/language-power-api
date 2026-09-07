"""initial schema

Revision ID: baf6518ba7a3
Revises: 
Create Date: 2026-08-28 19:39:59.997684

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'baf6518ba7a3'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('hashed_password', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    op.create_table('words',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('uuid', sa.String(), nullable=True),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('language', sa.String(), nullable=False),
    sa.Column('fl', sa.String(), nullable=False),
    sa.Column('stems', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
    sa.Column('defs', postgresql.ARRAY(sa.String()), server_default='{}', nullable=False),
    sa.Column('audio_url', sa.String(), nullable=True),
    sa.Column('transcription', sa.String(), nullable=True),
    sa.Column('img_url', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'uuid', name='uq_user_word_uuid')
    )
    op.create_index(op.f('ix_words_id'), 'words', ['id'], unique=False)
    op.create_index(op.f('ix_words_language'), 'words', ['language'], unique=False)
    op.create_index(op.f('ix_words_name'), 'words', ['name'], unique=False)
    op.create_index(op.f('ix_words_user_id'), 'words', ['user_id'], unique=False)
    op.create_index(op.f('ix_words_uuid'), 'words', ['uuid'], unique=False)
    op.create_table('word_examples',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('word_id', sa.Integer(), nullable=False),
    sa.Column('text', sa.String(), nullable=False),
    sa.Column('translation', sa.String(), nullable=False),
    sa.ForeignKeyConstraint(['word_id'], ['words.id'], ondelete='CASCADE'),    
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_word_examples_id'), 'word_examples', ['id'], unique=False)
    op.create_index(op.f('ix_word_examples_word_id'), 'word_examples', ['word_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_word_examples_word_id'), table_name='word_examples')
    op.drop_index(op.f('ix_word_examples_id'), table_name='word_examples')
    op.drop_table('word_examples')
    op.drop_index(op.f('ix_words_uuid'), table_name='words')
    op.drop_index(op.f('ix_words_user_id'), table_name='words')
    op.drop_index(op.f('ix_words_name'), table_name='words')
    op.drop_index(op.f('ix_words_language'), table_name='words')
    op.drop_index(op.f('ix_words_id'), table_name='words')
    op.drop_table('words')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_id'), table_name='users')
    op.drop_table('users')
    # ### end Alembic commands ###