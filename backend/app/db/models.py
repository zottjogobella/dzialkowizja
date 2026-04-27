from __future__ import annotations

import uuid
from datetime import datetime, time

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, LargeBinary, Numeric, SmallInteger, String, Text, Time, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# Postgres enum is owned by the migration (CREATE TYPE there); we reference
# the existing type by name and disable create/drop in the metadata.
USER_ROLE = Enum(
    "super_admin", "admin", "handlowiec", "prawnik", name="user_role", create_type=False
)

# Tiers that admins can hide fields from. super_admin/admin always see everything.
RESTRICTABLE_ROLES: tuple[str, ...] = ("handlowiec", "prawnik")


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    stats_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    members: Mapped[list[User]] = relationship(
        back_populates="organization",
        primaryjoin="Organization.id==User.organization_id",
    )
    restricted_fields: Mapped[list[RestrictedField]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    login_hours: Mapped[list[OrganizationLoginHours]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    role_policies: Mapped[list[OrganizationRolePolicy]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_organization", "organization_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role: Mapped[str] = mapped_column(USER_ROLE, nullable=False, default="handlowiec")
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=True
    )
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list[Session]] = relationship(back_populates="user", cascade="all, delete-orphan")
    search_history: Mapped[list[SearchHistory]] = relationship(back_populates="user", cascade="all, delete-orphan")
    organization: Mapped[Organization | None] = relationship(
        back_populates="members",
        foreign_keys=[organization_id],
    )


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


class RestrictedField(Base):
    """A field hidden from a specific user-tier role inside this organization.

    Presence of a row means *hidden* for that role. ``role`` is one of
    ``RESTRICTABLE_ROLES`` (handlowiec/prawnik); admin/super_admin are
    never affected. The registry of legal ``field_key`` values lives in
    ``app/permissions/fields.py``.
    """

    __tablename__ = "restricted_fields"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    field_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="restricted_fields")


class ActivityLog(Base):
    """Auditable log of every data-access event (search, plot view, etc.).

    Distinct from ``SearchHistory`` — that table powers the user-facing
    sidebar of recent searches and is shaped around that UI. ActivityLog is
    the operator-facing audit trail with IP and per-org filtering.
    """

    __tablename__ = "activity_log"
    __table_args__ = (
        Index("ix_activity_log_user_time", "user_id", "created_at"),
        Index("ix_activity_log_org_time", "organization_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    # Prior valuation from the CSV's ``wycena_old`` column — shown alongside
    # the current value so users can see how the figure changed.
    wartosc_dzialki_old: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    # Land registry number + owners, read straight from the CSV for the plots
    # covered by the sheet. Nullable so rows loaded before the columns existed
    # stay queryable.
    kw: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entities: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Ownership-complication flags from the CSV — surfaced as badges in the
    # search dropdown. Nullable so older rows stay queryable until the next
    # ingest fills them in.
    has_sluzebnosci: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_10_or_more_owners: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_state_owner: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class WycenaSupplemental(Base):
    """Supplemental plot valuations (fallback when not in ``roszczenia``).

    Loaded from ``wyceny_5_5M_union3_dedup_without_old_combined_ids.csv``
    by ``backend/scripts/ingest_wycena_supplemental_csv.py``. The sheet
    covers many more plots than ``roszczenia`` but lacks KW / owner data,
    so it's used purely to surface a valuation for plots the main sheet
    doesn't cover. ``roszczenia`` always wins when both have a row.
    """

    __tablename__ = "wycena_supplemental"
    __table_args__ = (Index("ix_wycena_supplemental_lot", "id_dzialki", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_dzialki: Mapped[str] = mapped_column(String(255), nullable=False)
    wartosc_dzialki: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    cena_m2: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    pow_dzialki: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    pow_buforu: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    segment_rynku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pewnosc: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)


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


class OrganizationLoginHours(Base):
    """Per-day login window for a (org, role) pair.

    Exactly 7 rows per (org, role), so 14 rows per org once both
    handlowiec and prawnik are seeded. ``closed=TRUE`` means no access on
    that day for that role; otherwise ``start_time`` / ``end_time`` define
    an inclusive-start, exclusive-end window interpreted in Europe/Warsaw.
    """

    __tablename__ = "organization_login_hours"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="login_hours")


class OrganizationRolePolicy(Base):
    """Per-role org policy: login-hours toggle + daily search limit.

    Replaces the three legacy columns on ``organizations`` so admins can
    enforce different limits on handlowiec vs prawnik. One row per
    (org, role); admins/super_admins are unaffected.
    """

    __tablename__ = "organization_role_policy"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(String(32), primary_key=True)
    login_hours_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    daily_search_limit_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    daily_search_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=40, server_default="40"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    organization: Mapped[Organization] = relationship(back_populates="role_policies")
