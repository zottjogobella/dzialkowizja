from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, LargeBinary, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list[Session]] = relationship(back_populates="user", cascade="all, delete-orphan")
    search_history: Mapped[list[SearchHistory]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user", "user_id"),
        Index("ix_sessions_expires", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(String(64))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="sessions")


class SearchHistory(Base):
    __tablename__ = "search_history"
    __table_args__ = (Index("ix_search_history_user_time", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    query_text: Mapped[str] = mapped_column(String(500))
    query_type: Mapped[str] = mapped_column(String(20))  # 'id_dzialki' | 'address' | 'numer'
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    top_result_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="search_history")


class PlotSnapshot(Base):
    __tablename__ = "plot_snapshots"
    __table_args__ = (
        Index("ix_plot_snapshots_dzialki_type", "id_dzialki", "snapshot_type", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_dzialki: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_type: Mapped[str] = mapped_column(String(20), nullable=False)
    image_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Roszczenie(Base):
    """Plot valuations loaded from the roszczenia.csv spreadsheet.

    Minimal two-column mapping ``id_dzialki → wartosc_dzialki``. Despite
    the file being named ``roszczenia.csv``, the stored value is the
    total plot valuation (``cena_m2 × pow_dzialki``) — the actual claim
    is derived live on the frontend as
    ``wartosc_dzialki × 0.5 × (pow_buforu / pow_dzialki)`` so the slider
    buffer rescales the result.

    Only rows owned by legal entities (``os prawna``/``panstwo``) are
    imported — individuals are filtered out during ingest. Stored in the
    app DB so the data stays local to this project and is not touched in
    gruntomat.
    """

    __tablename__ = "roszczenia"
    __table_args__ = (Index("ix_roszczenia_lot", "id_dzialki"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_dzialki: Mapped[str] = mapped_column(String(255), nullable=False)
    wartosc_dzialki: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
