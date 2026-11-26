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
    book        = Column(String, nullable=False, default="equity")  # shared, equity, option, mcx
    created_at  = Column(DateTime, default=datetime.utcnow)


# Complete 47-column header sequence and standard formulas
STANDARD_FORMULA_COLUMNS = [
    {"name": "SYMBOL",              "col_key": "symbol",              "col_type": "default", "col_order": 0,  "width": 120, "color_rules": None, "formula": None, "is_visible": True},
    {"name": "TREND",               "col_key": "trend",               "col_type": "custom",  "col_order": 1,  "width": 80,  "color_rules": '{"UP":"green","DOWN":"red"}', "formula": '=IF((p_high+p_low+p_close)/3>ltp,"DOWN","UP")', "is_visible": True},
    {"name": "LTP",                 "col_key": "ltp",                 "col_type": "default", "col_order": 2,  "width": 135, "color_rules": None, "formula": None, "is_visible": True},
    {"name": "OPEN",                "col_key": "open",                "col_type": "default", "col_order": 3,  "width": 85,  "color_rules": None, "formula": None, "is_visible": True},
    {"name": "HIGH",                "col_key": "high",                "col_type": "default", "col_order": 4,  "width": 85,  "color_rules": '{"field":"high","style":"green"}', "formula": None, "is_visible": True},
    {"name": "LOW",                 "col_key": "low",                 "col_type": "default", "col_order": 5,  "width": 85,  "color_rules": '{"field":"low","style":"red"}', "formula": None, "is_visible": True},
    {"name": "P_CLOSE",             "col_key": "p_close",             "col_type": "default", "col_order": 6,  "width": 85,  "color_rules": None, "formula": None, "is_visible": True},
    {"name": "GANN",                "col_key": "gann",                "col_type": "custom",  "col_order": 7,  "width": 80,  "color_rules": "{}", "formula": '=(high+low)/2', "is_visible": True},
    {"name": "OHLSIGNAL",           "col_key": "ohlsignal",           "col_type": "custom",  "col_order": 8,  "width": 85,  "color_rules": '{"BUY":"green","SELL":"red"}', "formula": '=IF(open=low,"BUY",IF(open=high,"SELL",""))', "is_visible": True},
    {"name": "SUPERSIGNAL",         "col_key": "supersignal",         "col_type": "custom",  "col_order": 9,  "width": 90,  "color_rules": '{"BUY":"green","SELL":"red"}', "formula": '=IFERROR(IF(AND(open>p_close,ltp>open),"BUY",IF(AND(open<p_close,ltp<open),"SELL","")),"")', "is_visible": True},
    {"name": "INTRASIGNAL",         "col_key": "intrasignal",         "col_type": "custom",  "col_order": 10, "width": 90,  "color_rules": '{"BUY":"green","SELL":"red"}', "formula": '=IF(ltp>open,"BUY","SELL")', "is_visible": True},
    {"name": "ENTRY",               "col_key": "entry",               "col_type": "custom",  "col_order": 11, "width": 85,  "color_rules": "{}", "formula": '=IF(AND(open=0,high=0,low=0),"",IF(ltp>open,ROUND(((SQRT(open)+0.025)^2),0),IF(ltp<open,ROUND(((SQRT(open)-0.025)^2),0),IF(open<>high<>low,""))))', "is_visible": True},
    {"name": "SL",                  "col_key": "sl",                  "col_type": "custom",  "col_order": 12, "width": 85,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",$entry-($entry*0.5%),IF(intrasignal="SELL",entry+(entry*0.5%),"")),"")', "is_visible": True},
    {"name": "TGT1",                "col_key": "tgt1",                "col_type": "custom",  "col_order": 13, "width": 80,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",bt1,IF(intrasignal="SELL",st1,"")),"")', "is_visible": True},
    {"name": "TGT2",                "col_key": "tgt2",                "col_type": "custom",  "col_order": 14, "width": 80,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",bt2,IF(intrasignal="SELL",st2,"")),"")', "is_visible": True},
    {"name": "TGT3",                "col_key": "tgt3",                "col_type": "custom",  "col_order": 15, "width": 80,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",bt3,IF(intrasignal="SELL",st3,"")),"")', "is_visible": True},
    {"name": "TGT4",                "col_key": "tgt4",                "col_type": "custom",  "col_order": 16, "width": 80,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",bt4,IF(intrasignal="SELL",st4,"")),"")', "is_visible": True},
    {"name": "TGT5",                "col_key": "tgt5",                "col_type": "custom",  "col_order": 17, "width": 80,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",bt5,IF(intrasignal="SELL",st5,"")),"")', "is_visible": True},
    {"name": "P_HIGH",              "col_key": "p_high",              "col_type": "default", "col_order": 18, "width": 85,  "color_rules": '{"field":"p_high","style":"green"}', "formula": None, "is_visible": True},
    {"name": "P_LOW",               "col_key": "p_low",               "col_type": "default", "col_order": 19, "width": 85,  "color_rules": '{"field":"p_low","style":"red"}', "formula": None, "is_visible": True},
    {"name": "DIFF",                "col_key": "diff",                "col_type": "custom",  "col_order": 20, "width": 80,  "color_rules": "{}", "formula": '=p_high-p_low', "is_visible": True},
    {"name": "BT1",                 "col_key": "bt1",                 "col_type": "custom",  "col_order": 21, "width": 80,  "color_rules": "{}", "formula": '=(open+0.1)+(diff/3)', "is_visible": True},
    {"name": "BT2",                 "col_key": "bt2",                 "col_type": "custom",  "col_order": 22, "width": 80,  "color_rules": "{}", "formula": '=(bt1+0.1)+(diff/2)', "is_visible": True},
    {"name": "BT3",                 "col_key": "bt3",                 "col_type": "custom",  "col_order": 23, "width": 80,  "color_rules": "{}", "formula": '=(bt2+0.1)+(diff/2)', "is_visible": True},
    {"name": "BT4",                 "col_key": "bt4",                 "col_type": "custom",  "col_order": 24, "width": 80,  "color_rules": "{}", "formula": '=(bt3+0.1)+(diff/2)', "is_visible": True},
    {"name": "BT5",                 "col_key": "bt5",                 "col_type": "custom",  "col_order": 25, "width": 80,  "color_rules": "{}", "formula": '=(bt4+0.1)+(diff/2)', "is_visible": True},
    {"name": "ST1",                 "col_key": "st1",                 "col_type": "custom",  "col_order": 26, "width": 80,  "color_rules": "{}", "formula": '=(open-0.1)-(diff/3)', "is_visible": True},
    {"name": "ST2",                 "col_key": "st2",                 "col_type": "custom",  "col_order": 27, "width": 80,  "color_rules": "{}", "formula": '=(st1-0.1)-(diff/2)', "is_visible": True},
    {"name": "ST3",                 "col_key": "st3",                 "col_type": "custom",  "col_order": 28, "width": 80,  "color_rules": "{}", "formula": '=(st2-0.1)-(diff/2)', "is_visible": True},
    {"name": "ST4",                 "col_key": "st4",                 "col_type": "custom",  "col_order": 29, "width": 80,  "color_rules": "{}", "formula": '=(st3-0.1)-(diff/2)', "is_visible": True},
    {"name": "ST5",                 "col_key": "st5",                 "col_type": "custom",  "col_order": 30, "width": 80,  "color_rules": "{}", "formula": '=(st4-0.1)-(diff/2)', "is_visible": True},
    {"name": "PP",                  "col_key": "pp",                  "col_type": "custom",  "col_order": 31, "width": 80,  "color_rules": "{}", "formula": '=(p_high+p_low+p_close)/3', "is_visible": True},
    {"name": "VWAP",                "col_key": "vwap",                "col_type": "custom",  "col_order": 32, "width": 85,  "color_rules": None, "formula": '=AVERAGE.WEIGHTED((high+low+ltp)/3,volume)', "is_visible": True},
    {"name": "VOLUME",              "col_key": "volume",              "col_type": "default", "col_order": 33, "width": 90,  "color_rules": None, "formula": None, "is_visible": True},
    {"name": "KD",                  "col_key": "kd",                  "col_type": "custom",  "col_order": 34, "width": 80,  "color_rules": "{}", "formula": '=(ltp-low)/(high-low)*100', "is_visible": True},
    {"name": "P_VWAP",              "col_key": "p_vwap",              "col_type": "default", "col_order": 35, "width": 85,  "color_rules": None, "formula": None, "is_visible": True},
    {"name": "P_VOLUME",            "col_key": "p_volume",            "col_type": "default", "col_order": 36, "width": 90,  "color_rules": None, "formula": None, "is_visible": True},
    {"name": "VWAPSIGNAL",          "col_key": "vwapsignal",          "col_type": "custom",  "col_order": 37, "width": 85,  "color_rules": '{"BUY":"green","SELL":"red"}', "formula": '=IF(ltp>vwap,"BUY",IF(ltp<vwap,"SELL",""))', "is_visible": True},
    {"name": "BELOWSELL-ABOVEBUY",  "col_key": "belowsell_abovebuy",  "col_type": "custom",  "col_order": 38, "width": 95,  "color_rules": "{}", "formula": '=(p_high-(p_high*0.1%))', "is_visible": True},
    {"name": "ABOVEBUY-BELOWSELL",  "col_key": "abovebuy_belowsell",  "col_type": "custom",  "col_order": 39, "width": 95,  "color_rules": "{}", "formula": '=(p_low+(p_low*0.1%))', "is_visible": True},
    {"name": "POSSIBLE_TGT",        "col_key": "possible_tgt",        "col_type": "custom",  "col_order": 40, "width": 95,  "color_rules": "{}", "formula": '=IFERROR(IF(intrasignal="BUY",r1+(r1*0.005%-2),IF(intrasignal="SELL",s1-(s1*0.005%+1),"")),"")', "is_visible": True},
    {"name": "S3",                  "col_key": "s3",                  "col_type": "custom",  "col_order": 41, "width": 80,  "color_rules": "{}", "formula": '=p_low-2*(p_high-pp)', "is_visible": True},
    {"name": "S2",                  "col_key": "s2",                  "col_type": "custom",  "col_order": 42, "width": 80,  "color_rules": "{}", "formula": '=pp-(r1-s1)', "is_visible": True},
    {"name": "S1",                  "col_key": "s1",                  "col_type": "custom",  "col_order": 43, "width": 80,  "color_rules": "{}", "formula": '=2*pp-p_high', "is_visible": True},
    {"name": "R1",                  "col_key": "r1",                  "col_type": "custom",  "col_order": 44, "width": 80,  "color_rules": "{}", "formula": '=2*pp-p_low', "is_visible": True},
    {"name": "R2",                  "col_key": "r2",                  "col_type": "custom",  "col_order": 45, "width": 80,  "color_rules": "{}", "formula": '=pp+(r1-s1)', "is_visible": True},
    {"name": "R3",                  "col_key": "r3",                  "col_type": "custom",  "col_order": 46, "width": 80,  "color_rules": "{}", "formula": '=p_high+2*(pp-p_low)', "is_visible": True},
]

# Default market columns aligned with the standard sequence
DEFAULT_COLUMNS = [c for c in STANDARD_FORMULA_COLUMNS if c["col_type"] == "default"]
