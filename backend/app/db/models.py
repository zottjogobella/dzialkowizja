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
    # Land registry number + owners, read straight from the CSV for the plots
    # covered by the sheet. Nullable so rows loaded before the columns existed
    # stay queryable.
    kw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entities: Mapped[str | None] = mapped_column(Text, nullable=True)


class Argumentacja(Base):
    """Valuation arguments loaded from roszczenia_argumentacja.csv.

    1:1 with roszczenia by id_dzialki. Stores confidence score, model
    price, and up to 15 weighted text arguments explaining the valuation.
    """

    __tablename__ = "argumentacja"
    __table_args__ = (Index("ix_argumentacja_lot", "id_dzialki", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_dzialki: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pow_m2: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    pow_buforu: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    procent_pow: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    cena_ensemble: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    wartosc_total: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    cena_m2_roszczenie_orig: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    wartosc_roszczenia_orig: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    pewnosc_0_100: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pewnosc_kategoria: Mapped[str | None] = mapped_column(String(20), nullable=True)
    liczba_argumentow: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 15 argument + weight pairs (sparse — most plots have < 15)
    argument_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_1_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_2_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_3: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_3_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_4: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_4_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_5: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_5_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_6: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_6_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_7: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_7_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_8: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_8_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_9: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_9_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_10: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_10_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_11: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_11_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_12: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_12_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_13: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_13_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_14: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_14_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
    argument_15: Mapped[str | None] = mapped_column(Text, nullable=True)
    argument_15_waga: Mapped[int | None] = mapped_column(Integer, nullable=True)
