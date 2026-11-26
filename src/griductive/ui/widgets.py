"""Tkinter controls for cards and animated command buttons."""

from __future__ import annotations

from collections.abc import Callable
import time
import tkinter as tk

from griductive.ui.theme import AUTO_SOLVE_LABEL, CHECK_BOARD_LABEL, LOGS_LABEL, THEME


class RoundedCard(tk.Frame):
    """Fixed-layout frame with a canvas-drawn rounded background and border."""

    def __init__(self, master, **kwargs):
        self._fill = kwargs.pop("bg", THEME["bg_card"])
        self._stroke = kwargs.pop("highlightbackground", THEME["border_card"])
        self._stroke_width = kwargs.pop("highlightthickness", 2)
        super().__init__(master, bg=THEME["bg_root"], highlightthickness=0, **kwargs)
        self._surface = tk.Canvas(self, bg=THEME["bg_root"], highlightthickness=0)
        self._surface.place(x=0, y=0, relwidth=1, relheight=1, bordermode="ignore")
        self._surface.tk.call("lower", self._surface._w)
        self.bind("<Configure>", self._paint)

    def config(self, cnf=None, **kwargs):
        self._fill = kwargs.pop("bg", self._fill)
        self._stroke = kwargs.pop("highlightbackground", self._stroke)
        self._stroke_width = kwargs.pop("highlightthickness", self._stroke_width)
        result = super().config(cnf, **kwargs)
        self._paint()
        return result

    configure = config

    def _paint(self, event=None):
        self._paint_outline(2, 2, self._stroke, self._stroke_width)

    def _paint_outline(self, inset: int, top: int, color: str, width: int) -> None:
        right, bottom = self.winfo_width() - inset, self.winfo_height() - inset
        if right <= inset or bottom <= top:
            return
        radius = min(14, (right - inset) // 2, (bottom - top) // 2)
        points = (
            inset + radius, top, right - radius, top, right, top, right, top + radius,
            right, bottom - radius, right, bottom, right - radius, bottom,
            inset + radius, bottom, inset, bottom, inset, bottom - radius,
            inset, top + radius, inset, top, inset + radius, top,
        )
        self._surface.delete("all")
        self._surface.create_polygon(points, smooth=True, splinesteps=24,
                                     fill=self._fill, outline=color, width=width)


class CharacterCard(RoundedCard):
    """Animate the border inside the fixed grid slot."""

    def __init__(self, master: tk.Misc, *, scale: Callable[[float], int],
                 reduced_motion: Callable[[], bool], **kwargs) -> None:
        super().__init__(master, **kwargs)
        self._scale = scale
        self._reduced_motion = reduced_motion
        self._pointer_inside = False
        self._dimmed = False
        self._hover_amount = 0.0
        self._hover_timer: str | None = None
        self.bind("<Destroy>", self._cancel_hover)

    def bind_hover(self) -> None:
        """Treat the portrait, clue text and labels as one pointer target."""
        pending = [self]
        while pending:
            widget = pending.pop()
            widget.bind("<Enter>", self._enter_card, add="+")
            widget.bind("<Leave>", self._leave_card, add="+")
            pending.extend(widget.winfo_children())

    def set_dimmed(self, dimmed: bool) -> None:
        """Keep muted cards in the background during Hint spotlight."""
        if self._dimmed != dimmed:
            self._dimmed = dimmed
            self._animate_hover()

    def _enter_card(self, event) -> None:
        if not self._pointer_inside:
            self._pointer_inside = True
            self._animate_hover()

    def _leave_card(self, event) -> None:
        x = event.x_root - self.winfo_rootx()
        y = event.y_root - self.winfo_rooty()
        if 0 <= x < self.winfo_width() and 0 <= y < self.winfo_height():
            return
        if self._pointer_inside:
            self._pointer_inside = False
            self._animate_hover()

    def _cancel_hover(self, event=None) -> None:
        if self._hover_timer is not None:
            self.after_cancel(self._hover_timer)
            self._hover_timer = None

    def _animate_hover(self) -> None:
        self._cancel_hover()
        target = float(self._pointer_inside and not self._dimmed)
        start = self._hover_amount
        if self._dimmed or self._reduced_motion() or start == target:
            self._hover_amount = target
            self._paint()
            return

        started = time.perf_counter()

        def tick() -> None:
            self._hover_timer = None
            progress = min(1.0, (time.perf_counter() - started) / 0.15)
            self._hover_amount = start + (target - start) * (1 - (1 - progress) ** 3)
            self._paint()
            if progress < 1:
                self._hover_timer = self.after(15, tick)

        tick()

    def _paint(self, event=None) -> None:
        amount = 0.0 if self._dimmed else self._hover_amount
        motion = 0.0 if self._reduced_motion() else amount
        px = self._scale
        inset = max(2, px(3) - round(px(2) * motion))
        top = max(2, inset - round(px(1) * motion))
        base = self.winfo_rgb(self._stroke)
        light = self.winfo_rgb(THEME["text_primary"])
        color = "#" + "".join(
            f"{round((channel + (bright - channel) * amount * 0.72) / 257):02x}"
            for channel, bright in zip(base, light)
        )
        self._paint_outline(inset, top, color, self._stroke_width + round(px(1) * amount))


class GameButton(tk.Frame):
    """Animate the face inside a fixed target, using a native button for input."""

    ICONS = {
        "Hint": "✧", "Reveal": "◎", "Clear": "×", LOGS_LABEL: "≡",
        AUTO_SOLVE_LABEL: "▷", "Pause": "Ⅱ", CHECK_BOARD_LABEL: "◇",
        "Puzzles": "▤", "Restart": "↻", "Settings": "⚙",
        "Innocent": "✓", "Criminal": "!", "Cancel": "×", "Close": "×",
    }

    def __init__(self, parent, label, command, *, colors, scale, reduced_motion):
        background = parent._fill if isinstance(parent, RoundedCard) else parent.cget("bg")
        super().__init__(parent, bg=background, cursor="hand2", takefocus=True)
        self._scale = scale
        self._reduced_motion = reduced_motion
        self._base, foreground, self._hover, self._edge = colors
        self._timer = None
        self._amount = self._from = self._target = 0.0
        self._pressed = False
        self._hovered = False
        self._label = label
        self._art = tk.Canvas(self, bg=self.cget("bg"), bd=0, highlightthickness=0)
        self._art.place(relwidth=1, relheight=1)
        self._face = self._art.create_polygon(0, 0, 1, 0, 1, 1, smooth=True)
        self._button = tk.Button(
            self, text=label, command=command,
            font=("Trebuchet MS", 10, "bold"), fg=foreground, bg=self._base,
            activeforeground=foreground, activebackground=self._hover, relief=tk.FLAT,
            overrelief=tk.FLAT, bd=0, highlightthickness=0, padx=0, pady=0,
            takefocus=False, cursor="hand2",
        )
        self._icon = self._art.create_text(0, 0, font=("Segoe UI Symbol", 9), fill=foreground)
        self._button.place(x=0, y=0)
        # Reserve room for both resting and hovered frames, including the border.
        if label == "Hint":
            self._button.config(text="Reveal")
        label_width = self._button.winfo_reqwidth()
        self._button.config(text=label)
        super().config(width=label_width + scale(34),
                       height=self._button.winfo_reqheight() + scale(20))
        self.bind("<Configure>", self._paint)
        for target in (self, self._art, self._button):
            target.bind("<Enter>", self._enter)
            target.bind("<Leave>", self._leave)
        self.bind("<Destroy>", self._dispose)
        self.bind("<FocusIn>", self._paint)
        self.bind("<FocusOut>", self._paint)
        for key in ("Return", "space"):
            self.bind(f"<KeyRelease-{key}>", self._invoke_key)
        self._button.bind("<ButtonPress-1>", self._press)
        self._button.bind("<ButtonRelease-1>", self._activate_border)
        self._art.bind("<ButtonPress-1>", self._press)
        self._art.bind("<ButtonRelease-1>", self._activate_border)

    def _invoke_key(self, event):
        self._button.invoke()
        return "break"

    def config(self, cnf=None, **kwargs):
        if "text" in kwargs:
            self._label = kwargs.pop("text")
            self._button.config(text=self._label)
            self._paint()
        return super().config(cnf, **kwargs)

    configure = config

    def cget(self, key):
        return self._label if key == "text" else super().cget(key)

    def _enter(self, event):
        if self._hovered:
            return
        self._hovered = True
        self._ease_to(1.0)

    def _leave(self, event):
        # The pointer may have moved from the border to the native child.
        x, y = event.x_root, event.y_root
        if (0 <= x - self.winfo_rootx() < self.winfo_width()
                and 0 <= y - self.winfo_rooty() < self.winfo_height()):
            return
        if not self._hovered:
            return
        self._hovered = False
        self._pressed = False
        self._ease_to(0.0)

    def _press(self, event):
        self._pressed = True
        self.focus_set()
        self._paint()
        return "break"

    def _release(self, event):
        self._pressed = False
        self._paint()

    def _activate_border(self, event):
        armed = self._pressed
        self._release(event)
        x = event.x_root - self.winfo_rootx()
        y = event.y_root - self.winfo_rooty()
        if armed and 0 <= x < self.winfo_width() and 0 <= y < self.winfo_height():
            self._button.invoke()
        return "break"

    def _dispose(self, event):
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None

    def _ease_to(self, target):
        if self._timer is not None:
            self.after_cancel(self._timer)
            self._timer = None
        self._target = target
        self._from = self._amount
        if self._reduced_motion():
            self._amount = target
            self._paint()
            return
        self._started = time.perf_counter()
        self._tick()

    def _tick(self):
        self._timer = None
        progress = min(1.0, (time.perf_counter() - self._started) / 0.15)
        eased = 1 - (1 - progress) ** 3
        self._amount = self._from + (self._target - self._from) * eased
        self._paint()
        if progress < 1:
            self._timer = self.after(15, self._tick)

    def _paint(self, event=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 10 or height < 10:
            return
        px = self._scale
        amount = 0.0 if self._reduced_motion() else self._amount
        inset = px(5) - round(px(3) * amount)
        top = inset - round(px(2) * amount) + px(1 if self._pressed else 0)
        top = max(2, top)
        right, bottom = width - inset, height - inset - round(px(1) * amount)
        radius = min(px(8), (bottom - top) // 2)
        fill = self._hover if self._hovered or self._pressed else self._base
        edge = THEME["border_selected"] if self.focus_get() == self else (
            THEME["text_secondary"] if self._hovered else self._edge
        )
        points = (
            inset + radius, top, right - radius, top, right, top, right, top + radius,
            right, bottom - radius, right, bottom, right - radius, bottom,
            inset + radius, bottom, inset, bottom, inset, bottom - radius,
            inset, top + radius, inset, top, inset + radius, top,
        )
        self._art.coords(self._face, *points)
        self._art.itemconfig(self._face, fill=fill, outline=edge, width=px(2 if self._hovered else 1))
        self._art.itemconfig(self._icon, text=self.ICONS.get(self._label, ""))
        icon_width = px(12) if self._label in self.ICONS else 0
        gap = px(6) if icon_width else 0
        text_width = self._button.winfo_reqwidth()
        left = (width - text_width - icon_width - gap) // 2
        center_y = (top + bottom) // 2
        self._art.coords(self._icon, left + icon_width / 2, center_y)
        self._button.config(bg=fill)
        text_height = self._button.winfo_reqheight()
        self._button.place(x=left + icon_width + gap, y=center_y - text_height // 2,
                           width=text_width, height=text_height)
