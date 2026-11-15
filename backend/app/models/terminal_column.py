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
    {"name": "VWAP",      "col_key": "vwap",       "col_type": "default", "col_order": 4,  "width": 90,  "color_rules": None,                               "formula": None},
    {"name": "VOLUME",    "col_key": "volume",     "col_type": "default", "col_order": 5,  "width": 80,  "color_rules": None,                               "formula": None},
    {"name": "OI",        "col_key": "oi",         "col_type": "default", "col_order": 6,  "width": 70,  "color_rules": None,                               "formula": None},
    {"name": "LTP",       "col_key": "ltp",        "col_type": "default", "col_order": 7,  "width": 100, "color_rules": None,                               "formula": None},
    {"name": "%CHG",      "col_key": "change_pct", "col_type": "default", "col_order": 8,  "width": 75,  "color_rules": '{"positive":"green","negative":"red"}', "formula": None},
]

# Batch: Fibonacci Formula presets
FIBONACCI_FORMULA_COLUMNS = [
    {"name": "TREND", "formula": '=IF((high+low+close)/3>ltp,"DOWN","UP")', "col_order": 9, "width": 80, "color_rules": '{"UP":"green","DOWN":"red"}'},
    {"name": "HCG", "formula": "=(high+close)/2", "col_order": 10, "width": 80, "color_rules": "{}"},
    {"name": "OCG", "formula": "=(open+close)/2", "col_order": 11, "width": 80, "color_rules": "{}"},
    {"name": "LCG", "formula": "=(low+close)/2", "col_order": 12, "width": 80, "color_rules": "{}"},
    {"name": "KD", "formula": "=-(ltp-low)/(low-high)*100", "col_order": 13, "width": 80, "color_rules": "{}"},
    {"name": "GANN", "formula": "=(high+low)/2", "col_order": 14, "width": 80, "color_rules": "{}"},
    {"name": "SIGNAL", "formula": '=IF(ltp>open,"BUY","SELL")', "col_order": 15, "width": 85, "color_rules": '{"BUY":"green","SELL":"red"}'},
    {"name": "SSIG", "formula": '=IFERROR(IF(AND(open>close,ltp>open),"BUY",IF(AND(open<close,ltp<open),"SELL","")),"")', "col_order": 16, "width": 85, "color_rules": '{"BUY":"green","SELL":"red"}'},
    {"name": "ENTRY", "formula": '=IF(AND(open=0,high=0,low=0)," ",IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0),IF(signal="SELL",ROUND(((SQRT(open)-0.015)^2),0)," ")))', "col_order": 17, "width": 85, "color_rules": "{}"},
    {"name": "SL", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)-(ROUND(((SQRT(open)+0.015)^2),0)*0.5%),ROUND(((SQRT(open)-0.015)^2),0)+(ROUND(((SQRT(open)-0.015)^2),0)*0.5%))', "col_order": 18, "width": 85, "color_rules": "{}"},
    {"name": "T11.8", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.118%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.118%))', "col_order": 19, "width": 80, "color_rules": "{}"},
    {"name": "T23.8", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.238%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.238%))', "col_order": 20, "width": 80, "color_rules": "{}"},
    {"name": "T38.2", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.382%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.382%))', "col_order": 21, "width": 80, "color_rules": "{}"},
    {"name": "T50", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.5%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.5%))', "col_order": 22, "width": 80, "color_rules": "{}"},
    {"name": "T61.8", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.618%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.618%))', "col_order": 23, "width": 80, "color_rules": "{}"},
    {"name": "T78.6", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*0.786%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*0.786%))', "col_order": 24, "width": 80, "color_rules": "{}"},
    {"name": "T100", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*1%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*1%))', "col_order": 25, "width": 80, "color_rules": "{}"},
    {"name": "T1.618", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*1.618%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*1.618%))', "col_order": 26, "width": 80, "color_rules": "{}"},
    {"name": "T2.618", "formula": '=IF(signal="BUY",ROUND(((SQRT(open)+0.015)^2),0)+(ROUND(((SQRT(open)+0.015)^2),0)*2.618%),ROUND(((SQRT(open)-0.015)^2),0)-(ROUND(((SQRT(open)-0.015)^2),0)*2.618%))', "col_order": 27, "width": 80, "color_rules": "{}"},
]

# Batch: BSA Formula presets (28 columns in exact sequence A=SYMBOL to AB=VOLUME)
BSA_FORMULA_COLUMNS = [
    {"name": "SYMBOL",      "col_key": "symbol",      "col_type": "default", "col_order": 0,  "width": 130, "color_rules": None, "formula": None},
    {"name": "OPEN",        "col_key": "open",        "col_type": "default", "col_order": 1,  "width": 85,  "color_rules": None, "formula": None},
    {"name": "HIGH",        "col_key": "high",        "col_type": "default", "col_order": 2,  "width": 85,  "color_rules": '{"field":"high","style":"green"}', "formula": None},
    {"name": "LOW",         "col_key": "low",         "col_type": "default", "col_order": 3,  "width": 85,  "color_rules": '{"field":"low","style":"red"}', "formula": None},
    {"name": "P.CLOSE",     "col_key": "p_close",     "col_type": "default", "col_order": 4,  "width": 85,  "color_rules": None, "formula": None},
    {"name": "P.HIGH",      "col_key": "p_high",      "col_type": "default", "col_order": 5,  "width": 85,  "color_rules": None, "formula": None},
    {"name": "P.LOW",       "col_key": "p_low",       "col_type": "default", "col_order": 6,  "width": 85,  "color_rules": None, "formula": None},
    {"name": "LTP",         "col_key": "ltp",         "col_type": "default", "col_order": 7,  "width": 95,  "color_rules": None, "formula": None},
    {"name": "TREND",       "col_key": "trend",       "col_type": "custom",  "col_order": 8,  "width": 85,  "color_rules": '{"UP":"green","DOWN":"red"}', "formula": '=IF((high+low+p_close)/3>ltp,"DOWN","UP")'},
    {"name": "GANN",        "col_key": "gann",        "col_type": "custom",  "col_order": 9,  "width": 85,  "color_rules": "{}", "formula": '=(high+low)/2'},
    {"name": "KD",          "col_key": "kd",          "col_type": "custom",  "col_order": 10, "width": 80,  "color_rules": "{}", "formula": '=(ltp-low)/(high-low)*100'},
    {"name": "S-SIGNAL",    "col_key": "s_signal",    "col_type": "custom",  "col_order": 11, "width": 90,  "color_rules": '{"BUY":"green","SELL":"red"}', "formula": '=IFERROR(IF(AND(open>p_close,ltp>open),"BUY",IF(AND(open<p_close,ltp<open),"SELL","")),"")'},
    {"name": "OHLSIG",      "col_key": "ohlsig",      "col_type": "custom",  "col_order": 12, "width": 85,  "color_rules": '{"BUY":"green","SELL":"red"}', "formula": '=IF(open=low,"BUY",IF(open=high,"SELL",""))'},
    {"name": "INTRASIGNAL", "col_key": "intrasignal", "col_type": "custom",  "col_order": 13, "width": 95,  "color_rules": '{"BUY":"green","SELL":"red"}', "formula": '=IF(ltp>open,"BUY","SELL")'},
    {"name": "ENTRY",       "col_key": "entry",       "col_type": "custom",  "col_order": 14, "width": 85,  "color_rules": "{}", "formula": '=IF(AND(open=0,high=0,low=0)," ",IF(ltp>open,ROUND(((SQRT(open)+0.025)^2),0),IF(ltp<open,ROUND(((SQRT(open)-0.025)^2),0)," ")))'},
    {"name": "SL",          "col_key": "sl",          "col_type": "custom",  "col_order": 15, "width": 85,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",entry-(entry*0.5%),IF(intrasignal="SELL",entry+(entry*0.5%),"")),"")'},
    {"name": "TGT1",        "col_key": "tgt1",        "col_type": "custom",  "col_order": 16, "width": 85,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",bt1,IF(intrasignal="SELL",st1,"")),"")'},
    {"name": "TGT2",        "col_key": "tgt2",        "col_type": "custom",  "col_order": 17, "width": 85,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",bt2,IF(intrasignal="SELL",st2,"")),"")'},
    {"name": "TGT3",        "col_key": "tgt3",        "col_type": "custom",  "col_order": 18, "width": 85,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",bt3,IF(intrasignal="SELL",st3,"")),"")'},
    {"name": "BT1",         "col_key": "bt1",         "col_type": "custom",  "col_order": 19, "width": 85,  "color_rules": "{}", "formula": '=(open+0.5)+(diff/3)'},
    {"name": "BT2",         "col_key": "bt2",         "col_type": "custom",  "col_order": 20, "width": 85,  "color_rules": "{}", "formula": '=(open+0.01)+(diff/2)'},
    {"name": "BT3",         "col_key": "bt3",         "col_type": "custom",  "col_order": 21, "width": 85,  "color_rules": "{}", "formula": '=(open+0.5)+diff'},
    {"name": "DIFF",        "col_key": "diff",        "col_type": "custom",  "col_order": 22, "width": 85,  "color_rules": "{}", "formula": '=p_high-p_low'},
    {"name": "ST1",         "col_key": "st1",         "col_type": "custom",  "col_order": 23, "width": 85,  "color_rules": "{}", "formula": '=(open-0.55)-(diff/3)'},
    {"name": "ST2",         "col_key": "st2",         "col_type": "custom",  "col_order": 24, "width": 85,  "color_rules": "{}", "formula": '=(open-0.55)-(diff/2)'},
    {"name": "ST3",         "col_key": "st3",         "col_type": "custom",  "col_order": 25, "width": 85,  "color_rules": "{}", "formula": '=(open-0.55)-diff'},
    {"name": "VWAP",        "col_key": "vwap",        "col_type": "default", "col_order": 26, "width": 85,  "color_rules": None, "formula": None},
    {"name": "VOLUME",      "col_key": "volume",      "col_type": "default", "col_order": 27, "width": 90,  "color_rules": None, "formula": None},
]
