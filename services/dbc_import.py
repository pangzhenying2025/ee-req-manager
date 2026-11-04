"""DBC parsing independent of Streamlit and project persistence."""

import os
import tempfile

import cantools


def safe_num(v, cast, default):
    """安全转换数字，转换失败返回默认值"""
    try:
        return cast(v) if v is not None else default
    except (ValueError, TypeError):
        return default


def safe_decode(text):
    """修复DBC中文乱码：Latin-1误读 → GBK还原"""
    try:
        text.encode('ascii')
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    try:
        return text.encode('latin-1').decode('gbk')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return text


def parse_dbc_file(uploaded_file):
    """解析DBC文件，返回信号列表"""
    # 保存到临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix='.dbc') as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    
    try:
        db = cantools.database.load_file(tmp_path)
        signals = []
        
        for msg in db.messages:
            for sig in msg.signals:
                # 解析值描述
                value_desc = ""
                if sig.choices:
                    value_desc = ", ".join([f"{v}:{k}" for k, v in sig.choices.items()][:5])
                    if len(sig.choices) > 5:
                        value_desc += "..."
                
                signals.append({
                    "message_name": msg.name,
                    "message_id": f"0x{msg.frame_id:03X}",
                    "message_id_dec": msg.frame_id,
                    "dlc": msg.length,
                    "signal_name": sig.name,
                    "start_bit": sig.start,
                    "bit_length": sig.length,
                    "byte_order": "Motorola" if sig.byte_order == "big_endian" else "Intel",
                    "value_type": "Signed" if sig.is_signed else "Unsigned",
                    "factor": sig.scale,
                    "offset": sig.offset,
                    "min": safe_num(sig.minimum, float, None),
                    "max": safe_num(sig.maximum, float, None),
                    "unit": sig.unit or "",
                    "comment": safe_decode(sig.comment) if sig.comment else "",
                    "value_desc": value_desc,
                    "senders": ", ".join(msg.senders) if msg.senders else "",
                    "cycle_time": msg.cycle_time if hasattr(msg, 'cycle_time') else None,
                })
        
        return signals, db
    finally:
        os.unlink(tmp_path)
