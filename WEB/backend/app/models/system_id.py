"""System Identifier (SID) audit log model.

Each time a 255-char SID is generated or regenerated for a user, a row
is appended here.  The table is append-only — SIDs are never modified
once assigned.  Mirrors the FLOWSHEET portal's ``user_identity_sid_log``.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SystemIdLog(Base):
    """Immutable audit record for every SID generation event."""

    __tablename__ = "system_id_log"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Full 255-char SID
    system_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Decoded segments
    seg_version: Mapped[str] = mapped_column(String(4), nullable=False)    # "S1"
    seg_fn3: Mapped[str] = mapped_column(String(3), nullable=False)        # First 3 chars of first name
    seg_ln3: Mapped[str] = mapped_column(String(3), nullable=False)        # First 3 chars of last name
    seg_dob8: Mapped[str] = mapped_column(String(8), nullable=False)       # YYYYMMDD
    seg_gen1: Mapped[str] = mapped_column(String(1), nullable=False)       # M/F/X/U
    seg_epoch10: Mapped[str] = mapped_column(String(10), nullable=False)   # 10-digit epoch

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
