from sqlalchemy import Column, Integer, String, DateTime, Text, BigInteger, ForeignKey, TIMESTAMP, func, Sequence, UniqueConstraint, JSON, Boolean
from datetime import datetime
from .declarative_base import Base

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

class Admin(Base):
    __tablename__ = 'admins'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    role = Column(String, nullable=False)

class MessageLog(Base):
    __tablename__ = 'message_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    user_id = Column(BigInteger, nullable=False)
    topic_id = Column(BigInteger, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    text = Column(Text, nullable=True)
    message_type = Column(String, nullable=True) # e.g., 'text', 'photo', 'voice'
    reply_to_message_id = Column(BigInteger, nullable=True)
    replies_count = Column(Integer, default=0, nullable=False) # Count of replies to this message
    entities = Column(Text, nullable=True) # Store JSON string of entities

    def __repr__(self):
        return f"<MessageLog(chat_id={self.chat_id}, user_id={self.user_id}, topic_id={self.topic_id}, message_type='{self.message_type}')>"

class Membership(Base):
    __tablename__ = 'memberships'
    event_id = Column(Integer, Sequence('memberships_event_id_seq'), primary_key=True)
    user_id = Column(BigInteger)
    chat_id = Column(BigInteger)
    event_type = Column(Text) # e.g., 'join', 'leave', 'ban', 'unban', 'mute', 'unmute'
    date = Column(TIMESTAMP)

    def __repr__(self):
        return f"<Membership(event_id={self.event_id}, user_id={self.user_id}, event_type='{self.event_type}')>"

class UserEventLog(Base):
    __tablename__ = 'user_event_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    event_type = Column(String, nullable=False) # e.g., 'join', 'leave', 'ban', 'unban', 'mute'
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

class ReactionLog(Base):
    __tablename__ = 'reaction_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False) # User who sent the reaction
    chat_id = Column(BigInteger, nullable=False)
    message_id = Column(BigInteger, nullable=False) # Message to which reaction was sent
    emoji = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

class PollLog(Base):
    __tablename__ = 'poll_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    poll_id = Column(String, nullable=False) # Telegram's poll ID
    user_id = Column(BigInteger, nullable=False) # User who voted
    chat_id = Column(BigInteger, nullable=False)
    option_id = Column(Integer, nullable=False) # Index of the chosen option
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

class ChatInfo(Base):
    __tablename__ = 'chat_info'
    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False)
    topic_id = Column(BigInteger, nullable=True)
    topic_name = Column(String, nullable=True)  # Store topic name for better UX
    __table_args__ = (UniqueConstraint('chat_id', 'topic_id', name='_chat_topic_uc'),)

class ScheduledPost(Base):
    __tablename__ = 'scheduled_posts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    chat_id = Column(BigInteger, nullable=False) # Chat where the post will be sent
    topic_id = Column(BigInteger, nullable=True) # Topic ID, if it's a forum topic
    publish_time = Column(TIMESTAMP, nullable=False) # When the post should be published
    text = Column(Text, nullable=True) # Text of the post
    media_file_id = Column(Text, nullable=True) # Telegram file_id for photo, video, document, etc.
    media_type = Column(Text, nullable=True) # e.g., 'photo', 'video', 'document'
    status = Column(Text, default='pending') # 'pending', 'published', 'failed', 'deleted'
    created_at = Column(TIMESTAMP, server_default=func.now()) # When the post was scheduled
    published_at = Column(TIMESTAMP, nullable=True) # When the post was actually published
    published_by = Column(BigInteger, nullable=True) # Telegram ID of the admin who published the post
    telegram_message_id = Column(BigInteger, nullable=True) # ID of the published message in Telegram
    buttons_json = Column(Text, nullable=True) # JSON string storing inline keyboard buttons

    def __repr__(self):
        return f"<ScheduledPost(id={self.id}, chat_id={self.chat_id}, publish_time={self.publish_time}, status='{self.status}')>"


class PluginSettings(Base):
    """Таблица для хранения настроек плагинов"""
    __tablename__ = 'plugin_settings'
    
    plugin_name = Column(String(50), primary_key=True, nullable=False)
    settings = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<PluginSettings(plugin_name='{self.plugin_name}', updated_at={self.updated_at})>"


class InviteLink(Base):
    """Таблица для хранения информации об инвайт-ссылках"""
    __tablename__ = 'invite_links'
    
    id = Column(Integer, primary_key=True)
    link_url = Column(String, unique=True, nullable=False)
    name = Column(String)
    creator_id = Column(Integer)
    first_click = Column(DateTime, nullable=False)
    last_click = Column(DateTime, nullable=False)
    total_clicks = Column(Integer, default=0)
    left_count = Column(Integer, default=0)
    is_archived = Column(Boolean, default=False)
    
    def __repr__(self):
        return f"<InviteLink(id={self.id}, link_url='{self.link_url}', total_clicks={self.total_clicks})>"


class InviteClick(Base):
    """Таблица для хранения кликов по инвайт-ссылкам"""
    __tablename__ = 'invite_clicks'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    link_url = Column(String, ForeignKey('invite_links.link_url'), nullable=False)
    join_date = Column(DateTime, nullable=False)
    left_date = Column(DateTime)
    first_message_date = Column(DateTime)
    
    def __repr__(self):
        return f"<InviteClick(id={self.id}, user_id={self.user_id}, link_url='{self.link_url}')>"


class Trigger(Base):
    __tablename__ = 'triggers'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger_text = Column(String, nullable=False)  # Текст триггера (может содержать | для множественных)
    response_text = Column(Text, nullable=False)   # Ответ бота
    is_active = Column(Boolean, default=True, nullable=False)  # Включен/выключен
    trigger_count = Column(Integer, default=0, nullable=False)  # Количество срабатываний
    last_triggered = Column(DateTime, nullable=True)  # Последнее срабатывание
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<Trigger(id={self.id}, trigger_text='{self.trigger_text}', is_active={self.is_active})>"

class Warning(Base):
    __tablename__ = 'warnings'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    admin_id = Column(BigInteger, nullable=False)  # ID администратора, выдавшего предупреждение
    reason = Column(Text, nullable=True)  # Причина предупреждения
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<Warning(id={self.id}, user_id={self.user_id}, chat_id={self.chat_id})>"

