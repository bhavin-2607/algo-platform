"""
Terminal Column
===============
Stores ALL terminal columns per user — both default and custom.
Admin can set hidden formulas. Users can show/hide/reorder any column.
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
from datetime import datetime
import uuid


class TerminalColumn(Base):
    __tablename__ = "terminal_columns"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name        = Column(String, nullable=False)
    col_key     = Column(String, nullable=True)
    formula     = Column(String, nullable=True)       # NULL for default cols, set for formula cols
    col_type    = Column(String, default="custom")    # "default", "formula", or "custom"
    col_order   = Column(Integer, default=0)
    width       = Column(Integer, default=80)
    is_visible  = Column(Boolean, default=True)
    color_rules = Column(String, nullable=True)       # JSON {"UP":"green"}
    created_at  = Column(DateTime, default=datetime.utcnow)


# Default column definitions seeded on first visit
DEFAULT_COLUMNS = [
    {"name": "OPEN",      "col_key": "open",       "col_type": "default", "col_order": 0,  "width": 90,  "color_rules": None,                               "formula": None},
    {"name": "HIGH",      "col_key": "high",       "col_type": "default", "col_order": 1,  "width": 90,  "color_rules": '{"field":"high","style":"green"}',  "formula": None},
    {"name": "LOW",       "col_key": "low",        "col_type": "default", "col_order": 2,  "width": 90,  "color_rules": '{"field":"low","style":"red"}',     "formula": None},
    {"name": "CLOSE",     "col_key": "close",      "col_type": "default", "col_order": 3,  "width": 90,  "color_rules": None,                               "formula": None},
    {"name": "VWAP",      "col_key": "vwap",       "col_type": "default", "col_order": 4,  "width": 90,  "color_rules": None,                               "formula": None},
    {"name": "VOLUME",    "col_key": "volume",     "col_type": "default", "col_order": 5,  "width": 80,  "color_rules": None,                               "formula": None},
    {"name": "OI",        "col_key": "oi",         "col_type": "default", "col_order": 6,  "width": 70,  "color_rules": None,                               "formula": None},
    {"name": "LTP",       "col_key": "ltp",        "col_type": "default", "col_order": 7,  "width": 100, "color_rules": None,                               "formula": None},
    {"name": "%CHG",      "col_key": "change_pct", "col_type": "default", "col_order": 8,  "width": 75,  "color_rules": '{"positive":"green","negative":"red"}', "formula": None},
]
