# -*- coding: utf-8 -*-
"""
番茄时钟 —— 桌面悬浮番茄钟（macOS 毛玻璃 · 三态 + 设置页）
====================
三种形态：
  ① 悬浮模式：毛玻璃圆角小窗，可拖动、右下角缩放、置顶
  ② 长条模式：横跨桌面顶端/底端的玻璃长条（吸附桌面边缘）
     - 拖动窗口到屏幕上/下边缘会自动吸附
     - 吸附后按住拖动离开边缘即恢复悬浮
  ③ 迷你模式：缩成一个小番茄图标（右上角 − 按钮 或 右键菜单触发），
     点击小番茄恢复悬浮窗口
设置页（右上角 ⚙ 按钮）：
  · 调整工作/休息时长
  · 选择计时结束铃声（无/系统音/经典铃/自定义 wav）
  · 毛玻璃浅色/深色模式 + 透明度滑块（实时预览，苹果风）
运行：python 番茄时钟.py   |   配置：pomodoro_config.json
"""
import ctypes
import json
import os
import time
import tkinter as tk
from ctypes import wintypes
from tkinter import filedialog, simpledialog

try:
    import winsound
except ImportError:
    winsound = None

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(APP_DIR, "pomodoro_config.json")

DEFAULTS = {
    "work_min": 25,
    "break_min": 5,
    "w": 280,
    "h": 210,
    "x": 120,
    "y": 120,
    "alpha": 0.95,
    "topmost": True,
    "glass_mode": "light",   # light / dark
    "glass_alpha": 45,       # 毛玻璃透明度 0-100（越大越透明）
    "sound": "beep",         # none / system / beep / custom
    "sound_file": "",
}

KEY = "#FE00FE"          # 透明色键：此色像素被抠成透明 -> 四角圆弧
DOCK_H = 58              # 长条模式高度
MINI_S = 52              # 迷你番茄尺寸

# ---- 苹果风配色 ----
C_WORK   = "#FF5A5F"
C_REST   = "#34C759"
C_LEAF   = "#2FA84F"
C_LEAF_E = "#1E7A36"
C_HI     = "#FF9FA3"
APPLE_BLUE = {"light": "#007AFF", "dark": "#0A84FF"}

# ---- 主题：浅色 / 深色 ----
THEMES = {
    "light": {
        "main": "#1D1D1F", "sub": "#6E6E73",
        "btn": "#F2F2F7", "btn_e": "#E0E0E6",
        "handle": "#C7C7CC", "shadow": "#C9C9D2",
        "border": "#FFFFFF", "hi_line": "#F4F4F8",
        "mini_bg": "#E9E9EF",
    },
    "dark": {
        "main": "#FFFFFF", "sub": "#A1A1A6",
        "btn": "#2C2C2E", "btn_e": "#3A3A3C",
        "handle": "#48484A", "shadow": "#1C1C1E",
        "border": "#48484A", "hi_line": "#3A3A3C",
        "mini_bg": "#3A3A3C",
    },
}

BTN_STYLES = {
    "light": {
        "primary_work": {
            "base": "#FF5A5F", "hover": "#FF6B70", "pressed": "#E94B50",
            "gloss": "#FF8A8E", "border": None, "fg": "#FFFFFF"},
        "primary_rest": {
            "base": "#34C759", "hover": "#41D163", "pressed": "#2BB04E",
            "gloss": "#5CDB7F", "border": None, "fg": "#FFFFFF"},
        "secondary": {
            "base": "#F2F2F7", "hover": "#E9E9EF", "pressed": "#DCDCE3",
            "gloss": "#FFFFFF", "border": "#E0E0E6", "fg": "#1D1D1F"},
    },
    "dark": {
        "primary_work": {
            "base": "#FF5A5F", "hover": "#FF6B70", "pressed": "#E94B50",
            "gloss": "#FF8A8E", "border": None, "fg": "#FFFFFF"},
        "primary_rest": {
            "base": "#34C759", "hover": "#41D163", "pressed": "#2BB04E",
            "gloss": "#5CDB7F", "border": None, "fg": "#FFFFFF"},
        "secondary": {
            "base": "#2C2C2E", "hover": "#3A3A3C", "pressed": "#48484A",
            "gloss": "#3A3A3C", "border": "#48484A", "fg": "#FFFFFF"},
    },
}

SOUND_NAMES = [("none", "无声音"), ("system", "系统音"),
               ("beep", "经典铃"), ("custom", "自定义")]


def load_cfg():
    cfg = dict(DEFAULTS)
    try:
        with open(CFG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_cfg(cfg):
    try:
        with open(CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def work_area():
    """返回工作区 (x, y, w, h)，避开任务栏"""
    r = RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
    return (r.left, r.top, r.right - r.left, r.bottom - r.top)


def apply_acrylic(hwnd, tint=0x8CFFFFFF):
    """开启 Windows 亚克力毛玻璃，tint = 0xAABBGGRR"""
    class ACCENT_POLICY(ctypes.Structure):
        _fields_ = [("AccentState", ctypes.c_uint),
                    ("AccentFlags", ctypes.c_uint),
                    ("GradientColor", ctypes.c_uint),
                    ("AnimationId", ctypes.c_uint)]

    class WCA(ctypes.Structure):
        _fields_ = [("Attrib", ctypes.c_int),
                    ("pvData", ctypes.c_void_p),
                    ("cbData", ctypes.c_size_t)]

    accent = ACCENT_POLICY()
    accent.AccentState = 4
    accent.AccentFlags = 2
    accent.GradientColor = tint
    data = WCA(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p),
               ctypes.sizeof(accent))
    ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))


class Pomodoro(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_cfg()
        self.mode = "work"
        self.running = False
        self._job = None
        self.completed = 0
        self.work_min = max(1, int(self.cfg["work_min"]))
        self.break_min = max(1, int(self.cfg["break_min"]))
        self.remaining = self.work_min * 60
        self.glass_mode = self.cfg.get("glass_mode", "light")
        self.glass_alpha = max(0, min(100, int(self.cfg.get("glass_alpha", 45))))
        self.sound = self.cfg.get("sound", "beep")
        self.sound_file = self.cfg.get("sound_file", "")
        self._drag = None
        self._resize = None
        self._press_at = None
        self._pressed_btn = None
        self._hover_btn = None
        self._btn_rect = {}
        self.dock = None            # None / "top" / "bottom"
        self.mini = False           # 迷你模式
        self._settings_win = None   # 设置窗口引用
        self.float_size = (max(200, int(self.cfg["w"])),
                           max(160, int(self.cfg["h"])))
        self.t = THEMES[self.glass_mode]   # 当前主题

        self.title("番茄时钟")
        self.overrideredirect(True)
        self.attributes("-topmost", bool(self.cfg["topmost"]))
        self.attributes("-alpha", float(self.cfg["alpha"]))
        self.attributes("-transparentcolor", KEY)
        w, h = self.float_size
        self.geometry(f"{w}x{h}+{int(self.cfg['x'])}+{int(self.cfg['y'])}")
        self.minsize(200, 160)

        self.cv = tk.Canvas(self, bg=KEY, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", lambda _e: self.redraw())

        self.cv.bind("<ButtonPress-1>", self._on_press)
        self.cv.bind("<B1-Motion>", self._on_motion)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<Motion>", self._on_hover)
        self.cv.bind("<Leave>", lambda _e: self._set_hover(None))
        self.cv.bind("<Button-3>", self._menu)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(120, self._enable_glass)
        self.redraw()

    # ---------- 毛玻璃 ----------
    def _glass_tint(self):
        """根据模式与透明度计算 0xAABBGGRR tint（55..255，默认约195更实）"""
        a = int((100 - self.glass_alpha) / 100 * 200 + 55)  # 55..255
        if self.glass_mode == "dark":
            return (a << 24) | 0x000000
        return (a << 24) | 0xFFFFFF

    def _enable_glass(self):
        apply_acrylic(ctypes.windll.user32.GetParent(self.winfo_id()),
                      self._glass_tint())

    def _apply_glass(self):
        """重新应用毛玻璃（透明度/模式变化时调用）"""
        apply_acrylic(ctypes.windll.user32.GetParent(self.winfo_id()),
                      self._glass_tint())
        if (self._settings_win is not None
                and self._settings_win.top.winfo_exists()):
            self._settings_win._apply_glass()

    # ---------- 设置项 ----------
    def set_work_min(self, v):
        self.work_min = max(1, min(180, v))
        self.cfg["work_min"] = self.work_min
        if not self.running and self.mode == "work":
            self.remaining = self.work_min * 60
            self.redraw()
        save_cfg(self.cfg)

    def set_break_min(self, v):
        self.break_min = max(1, min(60, v))
        self.cfg["break_min"] = self.break_min
        if not self.running and self.mode == "break":
            self.remaining = self.break_min * 60
            self.redraw()
        save_cfg(self.cfg)

    def set_sound(self, kind):
        self.sound = kind
        self.cfg["sound"] = kind
        save_cfg(self.cfg)

    def set_sound_file(self, path):
        self.sound_file = path
        self.cfg["sound_file"] = path
        self.cfg["sound"] = "custom"
        self.sound = "custom"
        save_cfg(self.cfg)

    def set_glass_mode(self, mode):
        if mode not in THEMES:
            return
        self.glass_mode = mode
        self.t = THEMES[mode]
        self.cfg["glass_mode"] = mode
        save_cfg(self.cfg)
        self._apply_glass()
        self.redraw()

    def set_glass_alpha(self, v):
        self.glass_alpha = max(0, min(100, int(v)))
        self.cfg["glass_alpha"] = self.glass_alpha
        save_cfg(self.cfg)
        self._apply_glass()

    def _play_sound(self, kind=None):
        """播放计时结束铃声（kind 为空则用当前设置）"""
        kind = kind or self.sound
        if kind == "none" or not winsound:
            return
        try:
            if kind == "system":
                winsound.PlaySound("SystemNotification",
                                   winsound.SND_ALIAS | winsound.SND_ASYNC)
            elif kind == "beep":
                for _ in range(3):
                    winsound.Beep(880, 180)
                    time.sleep(0.12)
            elif kind == "custom" and self.sound_file:
                winsound.PlaySound(self.sound_file,
                                   winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            winsound.MessageBeep()

    # ---------- 形态切换 ----------
    def _dock_to(self, pos):
        """吸附为顶部/底部玻璃长条"""
        if self.dock is None and not self.mini:
            self.float_size = (self.winfo_width(), self.winfo_height())
        self.dock = pos
        self.mini = False
        self.minsize(1, 1)
        x, y, w, h = work_area()
        if pos == "top":
            self.geometry(f"{w}x{DOCK_H}+{x}+{y}")
        else:
            self.geometry(f"{w}x{DOCK_H}+{x}+{y + h - DOCK_H}")
        self.redraw()
        self._reposition_settings(x, y if pos == "top" else y + h - DOCK_H,
                                  w, DOCK_H)

    def _undock(self, e=None):
        """从长条恢复为悬浮窗口"""
        self.dock = None
        self.mini = False
        self.minsize(200, 160)
        w, h = self.float_size
        if e is not None:
            x = e.x_root - w // 2
            y = e.y_root - 16
        else:
            x, y = self.winfo_x(), self.winfo_y()
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.redraw()
        self._reposition_settings(x, y, w, h)

    def _to_mini(self):
        """缩成迷你番茄图标"""
        if self.dock is None and not self.mini:
            self.float_size = (self.winfo_width(), self.winfo_height())
        self.mini = True
        self.dock = None
        self.minsize(1, 1)
        self.geometry(f"{MINI_S}x{MINI_S}+{self.winfo_x()}+{self.winfo_y()}")
        self.redraw()
        self._reposition_settings(self.winfo_x(), self.winfo_y(), MINI_S, MINI_S)

    def _restore_from_mini(self):
        self.mini = False
        self.minsize(200, 160)
        w, h = self.float_size
        self.geometry(f"{w}x{h}+{self.winfo_x()}+{self.winfo_y()}")
        self.redraw()
        self._reposition_settings(self.winfo_x(), self.winfo_y(), w, h)

    # ---------- 绘制 ----------
    def redraw(self):
        c = self.cv
        c.delete("all")
        W, H = self.winfo_width(), self.winfo_height()
        if W < 10 or H < 10:
            return
        if self.mini:
            self._draw_mini(c, W, H)
            return
        if self.dock:
            self._draw_dock(c, W, H)
            return
        self._draw_float(c, W, H)

    # ---- 悬浮模式 ----
    def _draw_float(self, c, W, H):
        self._btn_rect = {}
        r = min(26, W // 10, H // 8)
        accent = C_WORK if self.mode == "work" else C_REST

        pts = self._round_rect(3, 3, W - 3, H - 3, r)
        c.create_polygon(pts, fill=KEY, outline="")
        c.create_polygon(pts, fill="", outline=self.t["border"], width=2,
                         joinstyle="round")
        # 玻璃反射高光
        hi_pts = self._round_rect(6, 6, W - 6, 16, r + 3)
        c.create_polygon(hi_pts, fill="", outline="#FFFFFF", width=1,
                         joinstyle="round")
        c.create_line(14, 10, W - 14, 10, fill=self.t["hi_line"], width=1)

        # 番茄 + 模式
        cx = W / 2
        tomy = 34 + (6 if H > 170 else 2)
        self._draw_tomato(c, cx, tomy, max(16, min(30, W // 9)))
        mode_txt = "专注" if self.mode == "work" else "休息"
        c.create_text(cx, tomy + max(24, W // 12) + 8,
                      text=f"{mode_txt} · {self.work_min if self.mode=='work' else self.break_min}′",
                      font=("Segoe UI", max(11, W // 26), "bold"), fill=accent)

        # 倒计时
        mm, ss = divmod(max(0, self.remaining), 60)
        txt = f"{mm:02d}:{ss:02d}"
        fs = max(26, int(W // 6.2))
        ty = H * 0.52
        c.create_text(cx + 1, ty + 2, text=txt,
                      font=("Segoe UI", fs, "bold"), fill=self.t["shadow"])
        c.create_text(cx, ty, text=txt,
                      font=("Segoe UI", fs, "bold"), fill=self.t["main"])

        # 右上：计数 + 设置 + 最小化
        c.create_text(W - 66, 14, text=f"🍅×{self.completed}",
                      font=("Segoe UI Emoji", max(10, W // 34)), fill=self.t["sub"],
                      anchor="ne")
        self._draw_gear(c, W - 40, 14, 22)
        self._draw_mini_btn(c, W - 16, 14, 20)

        # 按钮行
        bw1 = max(70, W * 0.30)
        bw2 = max(58, W * 0.22)
        bw3 = max(78, W * 0.28)
        bh = max(30, H * 0.17)
        by = H - bh - 12
        gap = 8
        total = bw1 + bw2 + bw3 + gap * 2
        x0 = (W - total) / 2
        self._draw_btn(c, x0, by, bw1, bh,
                       "暂停" if self.running else "开始",
                       "primary_work" if self.mode == "work" else "primary_rest",
                       "start")
        self._draw_btn(c, x0 + bw1 + gap, by, bw2, bh, "重置", "secondary",
                       "reset")
        self._draw_btn(c, x0 + bw1 + bw2 + gap * 2, by, bw3, bh,
                       "切到休息" if self.mode == "work" else "切到工作",
                       "secondary", "switch")

        # 缩放手柄
        hx, hy = W - 12, H - 10
        c.create_line(hx - 8, hy, hx, hy - 8, fill=self.t["handle"], width=3,
                      capstyle="round")
        c.create_line(hx - 4, hy, hx, hy - 4, fill=self.t["handle"], width=3,
                      capstyle="round")

    # ---- 长条模式 ----
    def _draw_dock(self, c, W, H):
        self._btn_rect = {}
        r = min(24, H // 3)
        accent = C_WORK if self.mode == "work" else C_REST
        cy = H / 2

        pts = self._round_rect(3, 3, W - 3, H - 3, r)
        c.create_polygon(pts, fill=KEY, outline="")
        c.create_polygon(pts, fill="", outline=self.t["border"], width=2,
                         joinstyle="round")
        hi_pts = self._round_rect(6, 6, W - 6, 14, r + 3)
        c.create_polygon(hi_pts, fill="", outline="#FFFFFF", width=1,
                         joinstyle="round")

        # 左侧：小番茄 + 模式
        s = max(14, min(20, H // 3))
        self._draw_tomato(c, 26 + s, cy, s)
        mode_txt = "专注" if self.mode == "work" else "休息"
        c.create_text(26 + s * 2 + 16, cy,
                      text=f"{mode_txt} · {self.work_min if self.mode=='work' else self.break_min}′",
                      font=("Segoe UI", max(12, H // 4), "bold"), fill=accent,
                      anchor="w")

        # 中部：倒计时（大字）
        mm, ss = divmod(max(0, self.remaining), 60)
        txt = f"{mm:02d}:{ss:02d}"
        fs = max(24, H // 2)
        tx = W * 0.40
        c.create_text(tx + 1, cy + 2, text=txt,
                      font=("Segoe UI", fs, "bold"), fill=self.t["shadow"])
        c.create_text(tx, cy, text=txt,
                      font=("Segoe UI", fs, "bold"), fill=self.t["main"])

        # 计数
        c.create_text(tx + max(120, fs * 3), cy, text=f"🍅×{self.completed}",
                      font=("Segoe UI Emoji", max(11, H // 4)), fill=self.t["sub"],
                      anchor="w")

        # 右侧按钮行 + 设置齿轮
        bh = max(30, H - 22)
        gap = 8
        bw1 = max(64, int(W * 0.06))
        bw2 = max(56, int(W * 0.05))
        bw3 = max(76, int(W * 0.07))
        total = bw1 + bw2 + bw3 + gap * 2
        by = (H - bh) / 2
        gear = 26
        x0 = W - total - gear - 14
        self._draw_btn(c, x0, by, bw1, bh,
                       "暂停" if self.running else "开始",
                       "primary_work" if self.mode == "work" else "primary_rest",
                       "start")
        self._draw_btn(c, x0 + bw1 + gap, by, bw2, bh, "重置", "secondary",
                       "reset")
        self._draw_btn(c, x0 + bw1 + bw2 + gap * 2, by, bw3, bh,
                       "切到休息" if self.mode == "work" else "切到工作",
                       "secondary", "switch")
        self._draw_gear(c, x0 + total + 8 + gear / 2, cy, gear)

    # ---- 迷你模式 ----
    def _draw_mini(self, c, W, H):
        r = min(20, W // 3, H // 3)
        pts = self._round_rect(2, 2, W - 2, H - 2, r)
        c.create_polygon(pts, fill=KEY, outline="")
        c.create_polygon(pts, fill="", outline=self.t["border"], width=2,
                         joinstyle="round")
        self._draw_tomato(c, W / 2, H / 2 + 2, min(16, W // 3))
        # 提示小字
        c.create_text(W / 2, H - 8, text="点击恢复", fill=self.t["sub"],
                      font=("Microsoft YaHei UI", 8), anchor="s")
        self._btn_rect = {}

    # ---- 基础绘制件 ----
    def _round_rect(self, x1, y1, x2, y2, r):
        return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]

    def _draw_btn(self, c, x, y, w, h, text, style_key, key):
        st = BTN_STYLES[self.glass_mode][style_key]
        hover = (self._hover_btn == key)
        pressed = (self._pressed_btn == key)
        r = h / 2
        dy = 1 if pressed else 0
        x, y = x, y + dy
        base = st["pressed"] if pressed else (st["hover"] if hover else st["base"])

        def pts(ox, oy, ww, hh):
            return [ox + r, oy, ox + ww - r, oy, ox + ww, oy,
                    ox + ww, oy + r, ox + ww, oy + hh - r, ox + ww, oy + hh,
                    ox + ww - r, oy + hh, ox + r, oy + hh, ox, oy + hh,
                    ox, oy + hh - r, ox, oy + r, ox, oy]

        c.create_polygon(pts(x, y + 1, w, h), smooth=True,
                         fill=st["pressed"], outline="")
        c.create_polygon(pts(x, y, w, h), smooth=True, fill=base, outline="")
        gh = max(4, h * 0.42)
        c.create_polygon(pts(x + 1, y + 1, w - 2, gh), smooth=True,
                         fill=st["gloss"], outline="")
        if st["border"]:
            c.create_polygon(pts(x, y, w, h), smooth=True, fill="",
                             outline=st["border"], width=1)
        c.create_text(x + w / 2, y + h / 2, text=text,
                      font=("Segoe UI", max(11, int(h * 0.42)), "bold"),
                      fill=st["fg"])
        self._btn_rect[key] = (x, y - dy, w, h)

    def _draw_gear(self, c, x, y, size):
        """右上角设置齿轮按钮（⚙）"""
        hover = (self._hover_btn == "settings")
        bg = self.t["btn_e"] if hover else self.t["btn"]
        c.create_oval(x - size / 2, y - size / 2, x + size / 2, y + size / 2,
                      fill=bg, outline="")
        c.create_text(x, y, text="⚙", fill=self.t["sub"],
                      font=("Segoe UI Symbol", max(9, int(size * 0.55))))
        self._btn_rect["settings"] = (x - size, y - size, size * 2, size * 2)

    def _draw_mini_btn(self, c, x, y, size):
        """右上角最小化小按钮 (−)"""
        hover = (self._hover_btn == "minimize")
        bg = self.t["mini_bg"] if hover else self.t["btn"]
        c.create_oval(x - size / 2, y - size / 2, x + size / 2, y + size / 2,
                      fill=bg, outline="")
        c.create_text(x, y, text="−", fill=self.t["main"],
                      font=("Segoe UI", 12, "bold"))
        self._btn_rect["minimize"] = (x - size, y - size, size * 2, size * 2)

    def _draw_tomato(self, c, cx, cy, s):
        c.create_oval(cx - s * 0.7, cy + s * 0.45, cx + s * 0.7,
                      cy + s * 1.05, fill="#B03A3E", outline="")
        c.create_oval(cx - s, cy - s * 0.75, cx + s, cy + s * 0.85,
                      fill=C_WORK, outline="")
        c.create_oval(cx - s * 0.82, cy - s * 0.60, cx + s * 0.82,
                      cy + s * 0.68, fill="#FF6B70", outline="")
        c.create_oval(cx - s * 0.55, cy - s * 0.48, cx - s * 0.05,
                      cy + s * 0.02, fill=C_HI, outline="")
        c.create_arc(cx - s * 0.55, cy - s * 1.05, cx + s * 0.55,
                     cy - s * 0.05, start=180, extent=180,
                     style="arc", outline="#FFFFFF", width=2)
        c.create_polygon(cx, cy - s * 1.0, cx - s * 0.80, cy - s * 1.28,
                         cx - s * 0.15, cy - s * 0.78, smooth=True,
                         fill=C_LEAF, outline=C_LEAF_E)
        c.create_polygon(cx, cy - s * 1.0, cx + s * 0.80, cy - s * 1.28,
                         cx + s * 0.15, cy - s * 0.78, smooth=True,
                         fill=C_LEAF, outline=C_LEAF_E)
        c.create_polygon(cx, cy - s * 1.0, cx - s * 0.32, cy - s * 1.48,
                         cx + s * 0.32, cy - s * 1.48, smooth=True,
                         fill=C_LEAF, outline=C_LEAF_E)

    # ---------- 设置窗口 ----------
    def _open_settings(self):
        if (self._settings_win is not None
                and self._settings_win.top.winfo_exists()):
            self._settings_win.top.lift()
            return
        self._settings_win = SettingsWindow(self)

    def _sync_settings(self, mx=None, my=None):
        """主窗移动/变形后，让设置窗保持相对位置一起移动
        mx/my 为目标主窗位置（geometry 后 winfo_x 尚未刷新时传入）"""
        if self._settings_win is None:
            return
        try:
            if not self._settings_win.top.winfo_exists():
                return
        except Exception:
            return
        ox, oy = self._settings_win._off
        x = (self.winfo_x() if mx is None else mx) + ox
        y = (self.winfo_y() if my is None else my) + oy
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, min(x, sw - self._settings_win.W))
        y = max(0, min(y, sh - self._settings_win.H - 40))
        self._settings_win.top.geometry(f"+{x}+{y}")

    def _reposition_settings(self, mx=None, my=None, mw=None, mh=None):
        """形态切换（dock/undock/mini）后按新位置重新定位设置窗"""
        if self._settings_win is None:
            return
        try:
            if not self._settings_win.top.winfo_exists():
                return
        except Exception:
            return
        self._settings_win.reposition(mx, my, mw, mh)

    # ---------- 交互 ----------
    def _hit(self, e):
        if self.mini:
            return "restore"
        x, y = e.x, e.y
        for key, (bx, by, bw, bh) in self._btn_rect.items():
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return f"btn:{key}"
        W, H = self.winfo_width(), self.winfo_height()
        if not self.dock and x >= W - 26 and y >= H - 26:
            return "resize"
        return "move"

    def _set_hover(self, key):
        if self._hover_btn != key:
            self._hover_btn = key
            self.redraw()

    def _on_hover(self, e):
        hit = self._hit(e)
        key = hit.split(":", 1)[1] if hit.startswith("btn:") else None
        self._set_hover(key)

    def _on_press(self, e):
        self._press_at = self._hit(e)
        if self._press_at.startswith("btn:"):
            self._pressed_btn = self._press_at.split(":", 1)[1]
            self.redraw()
        elif self._press_at == "move":
            self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())
        elif self._press_at == "resize":
            self._resize = (self.winfo_width(), self.winfo_height(),
                            e.x_root, e.y_root)

    def _on_motion(self, e):
        if self._drag and self._press_at == "move":
            # 拖到屏幕上下边缘 -> 自动吸附成长条
            x, y, w, h = work_area()
            if e.y_root <= y + 3:
                self._drag = None
                self._dock_to("top")
                return
            if e.y_root >= y + h - 3:
                self._drag = None
                self._dock_to("bottom")
                return
            if self.dock:
                # 长条模式下拖离边缘 -> 恢复悬浮
                self._drag = None
                self._undock(e)
                return
            self.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")
            self._sync_settings(e.x_root - self._drag[0],
                                e.y_root - self._drag[1])
        elif self._resize and self._press_at == "resize":
            ow, oh, sx, sy = self._resize
            nw = max(200, ow + (e.x_root - sx))
            nh = max(160, oh + (e.y_root - sy))
            self.geometry(f"{nw}x{nh}")

    def _on_release(self, _e):
        if self._press_at == "restore":
            self._restore_from_mini()
        elif self._press_at and self._press_at.startswith("btn:"):
            self._on_btn(self._press_at.split(":", 1)[1])
        self._press_at = None
        self._pressed_btn = None
        self._drag = None
        self._resize = None
        self.redraw()

    # ---------- 计时 ----------
    def _tick(self):
        if not self.running:
            return
        self.remaining -= 1
        if self.remaining <= 0:
            self._finish_phase()
        else:
            self.redraw()
        self._job = self.after(1000, self._tick)

    def _finish_phase(self):
        self._play_sound()
        if self.mode == "work":
            self.mode = "break"
            self.remaining = self.break_min * 60
            self.completed += 1
        else:
            self.mode = "work"
            self.remaining = self.work_min * 60
        self.running = True
        self.redraw()
        self._flash()

    def _flash(self):
        for i in range(3):
            self.after(i * 200, lambda i=i: self.attributes(
                "-alpha", 1.0 if i % 2 == 0 else max(0.5, float(self.cfg["alpha"]))))
        self.after(600, lambda: self.attributes("-alpha", float(self.cfg["alpha"])))

    # ---------- 按钮与菜单 ----------
    def _on_btn(self, name):
        if name == "start":
            self.running = not self.running
            if self.running and self.remaining <= 0:
                self.remaining = self.work_min * 60
            if self.running:
                if self._job is None:
                    self._job = self.after(1000, self._tick)
            else:
                if self._job:
                    self.after_cancel(self._job)
                    self._job = None
        elif name == "reset":
            self.running = False
            if self._job:
                self.after_cancel(self._job)
                self._job = None
            self.remaining = (self.work_min if self.mode == "work"
                              else self.break_min) * 60
        elif name == "switch":
            self.mode = "break" if self.mode == "work" else "work"
            self.remaining = (self.break_min if self.mode == "break"
                              else self.work_min) * 60
        elif name == "minimize":
            self._to_mini()
            return
        elif name == "settings":
            self._open_settings()
            return
        self.redraw()

    def _menu(self, _event=None):
        m = tk.Menu(self, tearoff=0)
        # 形态切换
        if self.dock == "top":
            m.add_command(label="恢复悬浮窗口", command=self._undock)
        elif self.dock == "bottom":
            m.add_command(label="恢复悬浮窗口", command=self._undock)
        elif self.mini:
            m.add_command(label="恢复悬浮窗口", command=self._restore_from_mini)
        else:
            m.add_command(label="吸附顶部（长条）",
                          command=lambda: self._dock_to("top"))
            m.add_command(label="吸附底部（长条）",
                          command=lambda: self._dock_to("bottom"))
            m.add_command(label="最小化（迷你）", command=self._to_mini)
        m.add_separator()
        m.add_command(label="设置…", command=self._open_settings)
        m.add_separator()
        m.add_command(
            label="置顶" + ("  ✓" if self.attributes("-topmost") else ""),
            command=self._toggle_topmost)
        m.add_command(label="透明度", command=self._set_alpha_dialog)
        m.add_separator()
        m.add_command(label="退出", command=self._on_close)
        try:
            m.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            m.grab_release()

    def _toggle_topmost(self):
        v = not self.attributes("-topmost")
        self.attributes("-topmost", v)
        self.cfg["topmost"] = v
        save_cfg(self.cfg)

    def _set_alpha_dialog(self):
        v = simpledialog.askfloat("窗口透明度", "输入 0.5 - 1.0：",
                                  initialvalue=float(self.cfg["alpha"]),
                                  parent=self, minvalue=0.5, maxvalue=1.0)
        if v:
            self.set_alpha(v)

    def set_alpha(self, v):
        """设置窗口整体透明度 0.5-1.0（与右键菜单一致，滑块复用）"""
        v = max(0.5, min(1.0, float(v)))
        self.cfg["alpha"] = v
        self.attributes("-alpha", v)
        save_cfg(self.cfg)

    # ---------- 收尾 ----------
    def _on_close(self):
        if self.dock or self.mini:
            w, h = self.float_size
            self.cfg.update({"w": w, "h": h,
                             "x": self.winfo_x(), "y": self.winfo_y()})
        else:
            self.cfg.update({
                "w": self.winfo_width(), "h": self.winfo_height(),
                "x": self.winfo_x(), "y": self.winfo_y(),
            })
        save_cfg(self.cfg)
        if self._job:
            self.after_cancel(self._job)
        if self._settings_win is not None:
            try:
                self._settings_win.top.destroy()
            except Exception:
                pass
        self.destroy()


class SettingsWindow:
    """设置页：时长 / 铃声 / 毛玻璃（浅深色 + 透明度滑块）"""

    W, H = 340, 478

    def __init__(self, parent):
        self.parent = parent
        self.top = tk.Toplevel(parent)
        self.top.title("番茄时钟设置")
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        self.top.attributes("-transparentcolor", KEY)
        self._off = (self.W + 10, 0)   # 相对主窗偏移（拖动时跟随）
        self.reposition()
        self.top.minsize(self.W, self.H)

        self.cv = tk.Canvas(self.top, bg=KEY, highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.cv.bind("<Configure>", lambda _e: self.redraw())
        self.cv.bind("<ButtonPress-1>", self._on_press)
        self.cv.bind("<B1-Motion>", self._on_motion)
        self.cv.bind("<ButtonRelease-1>", self._on_release)
        self.cv.bind("<Motion>", self._on_hover)
        self.cv.bind("<Leave>", lambda _e: self._set_hover(None))

        self._btn_rect = {}
        self._hover_btn = None
        self._pressed_btn = None
        self._drag_slider = False
        self._slider_x1, self._slider_x2, self._slider_y = 42, self.W - 86, 402

        self.top.protocol("WM_DELETE_WINDOW", self._close)
        self.top.after(120, self._enable_glass)
        self.redraw()

    # ---------- 毛玻璃 ----------
    def reposition(self, px=None, py=None, pw=None, ph=None):
        """按主窗位置重新定位（记录相对偏移供拖动跟随）
        传入目标坐标时用目标值，否则读主窗当前值"""
        px = self.parent.winfo_x() if px is None else px
        py = self.parent.winfo_y() if py is None else py
        pw = self.parent.winfo_width() if pw is None else pw
        ph = self.parent.winfo_height() if ph is None else ph
        x = px + pw + 10
        y = max(0, py + (ph - self.H) // 2)
        sw = self.parent.winfo_screenwidth()
        sh = self.parent.winfo_screenheight()
        if x + self.W > sw:
            x = max(0, px - self.W - 10)
        if y + self.H > sh:
            y = max(0, sh - self.H - 40)
        self._off = (x - px, y - py)
        self.top.geometry(f"{self.W}x{self.H}+{x}+{y}")

    def _enable_glass(self):
        apply_acrylic(ctypes.windll.user32.GetParent(self.top.winfo_id()),
                      self.parent._glass_tint())

    def _apply_glass(self):
        try:
            apply_acrylic(ctypes.windll.user32.GetParent(self.top.winfo_id()),
                          self.parent._glass_tint())
        except Exception:
            pass

    def _close(self):
        self.parent._settings_win = None
        self.top.destroy()

    # ---------- 绘制 ----------
    @property
    def t(self):
        return self.parent.t

    def redraw(self):
        c = self.cv
        c.delete("all")
        W, H = self.W, self.H
        self._btn_rect = {}
        t = self.t
        r = 24

        pts = self.parent._round_rect(2, 2, W - 2, H - 2, r)
        c.create_polygon(pts, fill=KEY, outline="")
        c.create_polygon(pts, fill="", outline=t["border"], width=2,
                         joinstyle="round")
        # 顶部高光
        hi_pts = self.parent._round_rect(5, 5, W - 5, 18, r + 3)
        c.create_polygon(hi_pts, fill="", outline="#FFFFFF", width=1,
                         joinstyle="round")

        # 标题 + 关闭
        c.create_text(24, 26, text="设置", font=("Segoe UI", 17, "bold"),
                      fill=t["main"], anchor="w")
        self._draw_circle_btn(c, W - 28, 24, 15, "✕", "close")
        c.create_line(22, 48, W - 22, 48, fill=t["btn_e"], width=1)

        # ---- 时长 ----
        c.create_text(24, 70, text="时长", font=("Segoe UI", 12, "bold"),
                      fill=t["sub"], anchor="w")
        self._draw_stepper(c, 24, 100, "工作", self.parent.work_min, 1, 180,
                           "work_min")
        self._draw_stepper(c, 24, 142, "休息", self.parent.break_min, 1, 60,
                           "break_min")

        # ---- 铃声 ----
        c.create_text(24, 188, text="计时结束铃声", font=("Segoe UI", 12, "bold"),
                      fill=t["sub"], anchor="w")
        cw, ch = 62, 30
        sx = 24
        for i, (key, label) in enumerate(SOUND_NAMES):
            self._draw_chip(c, sx + i * (cw + 8), 216, cw, ch, label,
                            self.parent.sound == key, f"sound:{key}")
        # 试听 / 选择文件
        self._draw_btn_like(c, 24, 256, 64, 30, "试听", "preview")
        self._draw_btn_like(c, 96, 256, 90, 30, "选择文件…", "pickfile")
        fname = os.path.basename(self.parent.sound_file or "")[:16]
        c.create_text(198, 271, text=fname or "未选择 wav",
                      font=("Segoe UI", 10), fill=t["sub"], anchor="w")

        # ---- 毛玻璃 ----
        c.create_text(24, 306, text="毛玻璃", font=("Segoe UI", 12, "bold"),
                      fill=t["sub"], anchor="w")
        self._draw_chip(c, 24, 334, 70, 30, "浅色",
                        self.parent.glass_mode == "light", "mode:light")
        self._draw_chip(c, 102, 334, 70, 30, "深色",
                        self.parent.glass_mode == "dark", "mode:dark")
        c.create_text(24, 376, text="窗口透明度", font=("Segoe UI", 11),
                      fill=t["main"], anchor="w")
        c.create_text(self.W - 30, 376,
                      text=f"{round(self.parent.cfg['alpha'] * 100)}%",
                      font=("Segoe UI", 11, "bold"), fill=APPLE_BLUE[self.parent.glass_mode],
                      anchor="e")
        alpha_ratio = (self.parent.cfg["alpha"] - 0.5) / 0.5
        self._draw_slider(c, self._slider_x1, self._slider_x2, self._slider_y,
                          max(0.0, min(1.0, alpha_ratio)))

        # 完成
        self._draw_btn_like(c, (W - 120) / 2, H - 52, 120, 34, "完成", "done")

    def _draw_circle_btn(self, c, x, y, size, text, key):
        t = self.t
        hover = (self._hover_btn == key)
        bg = t["mini_bg"] if hover else t["btn"]
        c.create_oval(x - size, y - size, x + size, y + size, fill=bg,
                      outline="")
        c.create_text(x, y, text=text, fill=t["main"],
                      font=("Segoe UI", 11, "bold"))
        self._btn_rect[key] = (x - size - 4, y - size - 4, size * 2 + 8,
                               size * 2 + 8)

    def _draw_stepper(self, c, x, y, label, value, lo, hi, key):
        """[−] 数值 [+] 步进器"""
        t = self.t
        c.create_text(x, y, text=label, font=("Segoe UI", 12), fill=t["main"],
                      anchor="w")
        s = 15
        by = y - s + 2
        # 减号
        self._draw_circle_btn(c, x + 118, y, s, "−", f"{key}:dec")
        # 数值
        c.create_text(x + 160, y, text=f"{value} 分", font=("Segoe UI", 12, "bold"),
                      fill=t["main"])
        # 加号
        self._draw_circle_btn(c, x + 214, y, s, "+", f"{key}:inc")

    def _draw_chip(self, c, x, y, w, h, label, active, key):
        t = self.t
        hover = (self._hover_btn == key)
        accent = APPLE_BLUE[self.parent.glass_mode]
        if active:
            bg, fg = accent, "#FFFFFF"
        elif hover:
            bg, fg = t["btn_e"], t["main"]
        else:
            bg, fg = t["btn"], t["main"]
        r = h / 2
        c.create_polygon([x + r, y, x + w - r, y, x + w, y, x + w, y + r,
                          x + w, y + h - r, x + w, y + h, x + w - r, y + h,
                          x + r, y + h, x, y + h, x, y + h - r, x, y + r,
                          x, y], smooth=True, fill=bg, outline="")
        c.create_text(x + w / 2, y + h / 2, text=label, font=("Segoe UI", 11),
                      fill=fg)
        self._btn_rect[key] = (x, y, w, h)

    def _draw_btn_like(self, c, x, y, w, h, text, key):
        st = BTN_STYLES[self.parent.glass_mode]["secondary"]
        hover = (self._hover_btn == key)
        pressed = (self._pressed_btn == key)
        r = h / 2
        dy = 1 if pressed else 0
        base = st["pressed"] if pressed else (st["hover"] if hover else st["base"])
        pts = [x + r, y + dy, x + w - r, y + dy, x + w, y + dy,
               x + w, y + dy + r, x + w, y + dy + h - r, x + w, y + dy + h,
               x + w - r, y + dy + h, x + r, y + dy + h, x, y + dy + h,
               x, y + dy + h - r, x, y + dy + r, x, y + dy]
        c.create_polygon(pts, smooth=True, fill=base, outline="")
        c.create_polygon(pts, smooth=True, fill="", outline=st["border"],
                         width=1)
        c.create_text(x + w / 2, y + dy + h / 2, text=text,
                      font=("Segoe UI", 11, "bold"), fill=st["fg"])
        self._btn_rect[key] = (x, y, w, h)

    def _draw_slider(self, c, x1, x2, y, ratio):
        t = self.t
        accent = APPLE_BLUE[self.parent.glass_mode]
        hx = x1 + (x2 - x1) * ratio
        # 轨道
        c.create_line(x1, y, x2, y, fill=t["btn_e"], width=5, capstyle="round")
        # 已选部分
        c.create_line(x1, y, hx, y, fill=accent, width=5, capstyle="round")
        # 手柄
        c.create_oval(hx - 10, y - 10, hx + 10, y + 10, fill="#FFFFFF",
                      outline=t["btn_e"], width=2)
        # 刻度标注
        c.create_text(x1, y + 16, text="50%", font=("Segoe UI", 9),
                      fill=t["sub"], anchor="w")
        c.create_text(x2, y + 16, text="100%", font=("Segoe UI", 9),
                      fill=t["sub"], anchor="e")
        self._slider_hx = hx

    # ---------- 交互 ----------
    def _hit(self, e):
        x, y = e.x, e.y
        for key, (bx, by, bw, bh) in self._btn_rect.items():
            if bx <= x <= bx + bw and by <= y <= by + bh:
                return f"btn:{key}"
        # 滑块区域
        if (self._slider_x1 - 15 <= x <= self._slider_x2 + 15
                and self._slider_y - 18 <= y <= self._slider_y + 18):
            return "slider"
        return None

    def _set_hover(self, key):
        if self._hover_btn != key:
            self._hover_btn = key
            self.redraw()

    def _on_hover(self, e):
        hit = self._hit(e)
        key = hit.split(":", 1)[1] if hit and hit.startswith("btn:") else None
        self._set_hover(key)

    def _on_press(self, e):
        hit = self._hit(e)
        if hit == "slider":
            self._drag_slider = True
            self._move_slider(e.x)
        elif hit and hit.startswith("btn:"):
            self._pressed_btn = hit.split(":", 1)[1]
            self.redraw()

    def _on_motion(self, e):
        if self._drag_slider:
            self._move_slider(e.x)

    def _on_release(self, _e):
        if self._drag_slider:
            self._drag_slider = False
        elif self._pressed_btn:
            name = self._pressed_btn
            self._pressed_btn = None
            self._on_btn(name)
            # close/done 已销毁窗口，直接返回避免对已销毁 canvas 重绘
            if name in ("close", "done") or not self.top.winfo_exists():
                return
        else:
            self._pressed_btn = None
        self.redraw()

    def _move_slider(self, x):
        x1, x2 = self._slider_x1, self._slider_x2
        ratio = max(0.0, min(1.0, (x - x1) / (x2 - x1)))
        # 滑块 0-100% -> 窗口整体透明度 0.5-1.0（与右键菜单一致）
        self.parent.set_alpha(round(0.5 + ratio * 0.5, 2))
        self.redraw()

    # ---------- 动作 ----------
    def _on_btn(self, name):
        p = self.parent
        if name == "close" or name == "done":
            self._close()
        elif name == "preview":
            p._play_sound()
        elif name == "pickfile":
            path = filedialog.askopenfilename(
                title="选择铃声（wav）",
                filetypes=[("WAV 音频", "*.wav"), ("音频文件", "*.wav *.mp3")])
            if path:
                p.set_sound_file(path)
                self.redraw()
        elif name.startswith("sound:"):
            kind = name.split(":", 1)[1]
            if kind == "custom" and not p.sound_file:
                path = filedialog.askopenfilename(
                    title="选择铃声（wav）",
                    filetypes=[("WAV 音频", "*.wav")])
                if path:
                    p.set_sound_file(path)
                else:
                    return
            p.set_sound(kind)
            self.redraw()
        elif name.startswith("mode:"):
            p.set_glass_mode(name.split(":", 1)[1])
            self.redraw()
        elif name.startswith("work_min:"):
            delta = 1 if name.endswith(":inc") else -1
            p.set_work_min(p.work_min + delta)
            self.redraw()
        elif name.startswith("break_min:"):
            delta = 1 if name.endswith(":inc") else -1
            p.set_break_min(p.break_min + delta)
            self.redraw()


if __name__ == "__main__":
    app = Pomodoro()
    app.mainloop()
