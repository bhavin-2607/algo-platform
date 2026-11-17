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
    book        = Column(String, nullable=False, default="equity")  # shared, equity, option
    created_at  = Column(DateTime, default=datetime.utcnow)


# Default column definitions seeded on first visit
DEFAULT_COLUMNS = [
    {"name": "OPEN",      "col_key": "open",       "col_type": "default", "col_order": 0,  "width": 90,  "color_rules": None,                               "formula": None},
    {"name": "HIGH",      "col_key": "high",       "col_type": "default", "col_order": 1,  "width": 90,  "color_rules": '{"field":"high","style":"green"}',  "formula": None},
    {"name": "LOW",       "col_key": "low",        "col_type": "default", "col_order": 2,  "width": 90,  "color_rules": '{"field":"low","style":"red"}',     "formula": None},
    {"name": "CLOSE",     "col_key": "close",      "col_type": "default", "col_order": 3,  "width": 90,  "color_rules": None,                               "formula": None},
    {"name": "P.HIGH",    "col_key": "p_high",     "col_type": "default", "col_order": 4,  "width": 90,  "color_rules": '{"field":"p_high","style":"green"}', "formula": None},
    {"name": "P.LOW",     "col_key": "p_low",      "col_type": "default", "col_order": 5,  "width": 90,  "color_rules": '{"field":"p_low","style":"red"}',   "formula": None},
    {"name": "P.CLOSE",   "col_key": "p_close",    "col_type": "default", "col_order": 6,  "width": 90,  "color_rules": None,                               "formula": None},
    {"name": "VWAP",      "col_key": "vwap",       "col_type": "default", "col_order": 7,  "width": 90,  "color_rules": None,                               "formula": None},
    {"name": "VOLUME",    "col_key": "volume",     "col_type": "default", "col_order": 8,  "width": 80,  "color_rules": None,                               "formula": None},
    {"name": "OI",        "col_key": "oi",         "col_type": "default", "col_order": 9,  "width": 70,  "color_rules": None,                               "formula": None},
    {"name": "LTP",       "col_key": "ltp",        "col_type": "default", "col_order": 10, "width": 100, "color_rules": None,                               "formula": None},
    {"name": "%CHG",      "col_key": "change_pct", "col_type": "default", "col_order": 11, "width": 75,  "color_rules": '{"positive":"green","negative":"red"}', "formula": None},
]

# Batch: Fibonacci Formula presets
FIBONACCI_FORMULA_COLUMNS = [
    {"name": "TREND", "formula": '=IF((high+low+close)/3>ltp,"DOWN","UP")', "col_order": 12, "width": 80, "color_rules": '{"UP":"green","DOWN":"red"}'},
    {"name": "HCG", "formula": "=(high+close)/2", "col_order": 13, "width": 80, "color_rules": "{}"},
    {"name": "OCG", "formula": "=(open+close)/2", "col_order": 14, "width": 80, "color_rules": "{}"},
    {"name": "LCG", "formula": "=(low+close)/2", "col_order": 15, "width": 80, "color_rules": "{}"},
    {"name": "KD", "formula": "=-(ltp-low)/(low-high)*100", "col_order": 16, "width": 80, "color_rules": "{}"},
    {"name": "GANN", "formula": "=(high+low)/2", "col_order": 17, "width": 80, "color_rules": "{}"},
    {"name": "SIGNAL", "formula": '=IF(ltp>open,"BUY","SELL")', "col_order": 18, "width": 85, "color_rules": '{"BUY":"green","SELL":"red"}'},
    {"name": "SSIG", "formula": '=IFERROR(IF(AND(open>close,ltp>open),"BUY",IF(AND(open<close,ltp<open),"SELL","")),"")', "col_order": 19, "width": 85, "color_rules": '{"BUY":"green","SELL":"red"}'},
    {"name": "ENTRY", "formula": '=IF(AND(open=0,high=0,low=0)," ",IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),2),IF(signal="SELL",ROUND(((SQRT(open)-0.015)^2),2)," ")))', "col_order": 20, "width": 85, "color_rules": "{}"},
    {"name": "SL", "formula": '=IF(signal="BUY",ROUND(entry-(entry*0.5%),2),ROUND(entry+(entry*0.5%),2))', "col_order": 21, "width": 85, "color_rules": "{}"},
    {"name": "T11.8", "formula": '=IF(signal="BUY",ROUND(entry+(entry*0.118%),2),ROUND(entry-(entry*0.118%),2))', "col_order": 22, "width": 80, "color_rules": "{}"},
    {"name": "T23.8", "formula": '=IF(signal="BUY",ROUND(entry+(entry*0.238%),2),ROUND(entry-(entry*0.238%),2))', "col_order": 23, "width": 80, "color_rules": "{}"},
    {"name": "T38.2", "formula": '=IF(signal="BUY",ROUND(entry+(entry*0.382%),2),ROUND(entry-(entry*0.382%),2))', "col_order": 24, "width": 80, "color_rules": "{}"},
    {"name": "T50", "formula": '=IF(signal="BUY",ROUND(entry+(entry*0.5%),2),ROUND(entry-(entry*0.5%),2))', "col_order": 25, "width": 80, "color_rules": "{}"},
    {"name": "T61.8", "formula": '=IF(signal="BUY",ROUND(entry+(entry*0.618%),2),ROUND(entry-(entry*0.618%),2))', "col_order": 26, "width": 80, "color_rules": "{}"},
    {"name": "T78.6", "formula": '=IF(signal="BUY",ROUND(entry+(entry*0.786%),2),ROUND(entry-(entry*0.786%),2))', "col_order": 27, "width": 80, "color_rules": "{}"},
    {"name": "T100", "formula": '=IF(signal="BUY",ROUND(entry+(entry*1%),2),ROUND(entry-(entry*1%),2))', "col_order": 28, "width": 80, "color_rules": "{}"},
    {"name": "T1.618", "formula": '=IF(signal="BUY",ROUND(entry+(entry*1.618%),2),ROUND(entry-(entry*1.618%),2))', "col_order": 29, "width": 80, "color_rules": "{}"},
    {"name": "T2.618", "formula": '=IF(signal="BUY",ROUND(entry+(entry*2.618%),2),ROUND(entry-(entry*2.618%),2))', "col_order": 30, "width": 80, "color_rules": "{}"},
]


