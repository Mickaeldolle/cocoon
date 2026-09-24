from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class FamilyRole(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class FamilySpace(Base):
    __tablename__ = "family_spaces"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    avatar_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list["FamilySpaceMember"]] = relationship(
        back_populates="family_space", cascade="all, delete-orphan"
    )


class FamilySpaceMember(Base):
    __tablename__ = "family_space_members"
    __table_args__ = (
        UniqueConstraint("family_space_id", "user_id", name="uq_family_space_member"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    family_space_id: Mapped[UUID] = mapped_column(
        ForeignKey("family_spaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[FamilyRole] = mapped_column(
        SqlEnum(FamilyRole, native_enum=False), default=FamilyRole.MEMBER
    )
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    family_space: Mapped[FamilySpace] = relationship(back_populates="members")
