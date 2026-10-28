from pathlib import Path
import os

ROOT=Path(__file__).resolve().parents[2]
APP_NAME='斗牛犬'

def apply_brand(root,subtitle='象棋助手'):
    root.title(f'{APP_NAME} · {subtitle}')
    if os.name=='nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('BulldogXiangqi.Desktop')
    try:root.iconbitmap(str(ROOT/'assets/bulldog.ico'))
    except Exception:pass
