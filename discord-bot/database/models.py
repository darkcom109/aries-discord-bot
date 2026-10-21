from sqlalchemy import String, Text, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)

class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    due_at: Mapped[int] = mapped_column(Integer)
    repeat: Mapped[str] = mapped_column(String)
    sent: Mapped[bool] = mapped_column(Boolean, default=False)

class ReminderDelivery(Base):
    __tablename__ = "reminder_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(Integer)
    guild_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

class SavedItem(Base):
    __tablename__ = "saved_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    guild_id: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_id: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String(100))
    content: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[int] = mapped_column(Integer)


class TflWatch(Base):
    __tablename__ = "tfl_watches"
    __table_args__ = (UniqueConstraint("user_id", "line_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    channel_id: Mapped[str] = mapped_column(String)
    line_id: Mapped[str] = mapped_column(String(80))
    line_name: Mapped[str] = mapped_column(String(100))
    last_status: Mapped[str] = mapped_column(String(64))


class AutonomyState(Base):
    __tablename__ = "autonomy_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    allow_actions: Mapped[bool] = mapped_column(Boolean, default=False)
    owner_id: Mapped[str] = mapped_column(String)
    guild_id: Mapped[str] = mapped_column(String)
    channel_id: Mapped[str] = mapped_column(String)
    goal: Mapped[str] = mapped_column(Text)
    memory: Mapped[str] = mapped_column(Text, default="")
    interval_minutes: Mapped[int] = mapped_column(Integer, default=15)
    next_run_at: Mapped[int] = mapped_column(Integer, default=0)
    last_run_at: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class AutonomyAction(Base):
    __tablename__ = "autonomy_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[int] = mapped_column(Integer, index=True)
    owner_id: Mapped[str] = mapped_column(String, index=True)
    channel_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String(50))
    detail: Mapped[str] = mapped_column(Text)
    signature: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
