#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Dict, List, Optional, Tuple

Cell = Tuple[int, int]


@dataclass(frozen=True)
class Operator:
    key: str
    name: str
    shifts: Tuple[Cell, ...]


CROSS = ((-1, 0), (1, 0), (0, -1), (0, 1))
DIAG = ((-1, -1), (-1, 1), (1, -1), (1, 1))
OPERATORS: Dict[str, Operator] = {
    "cross": Operator("cross", "Вверх-вниз-вправо-вліво", CROSS),
    "diag": Operator("diag", "По діагоналях", DIAG),
    "combined": Operator("combined", "Комбінований (хрест + діагоналі)", CROSS + DIAG),
}


class Maze:
    def __init__(self, rows: int, cols: int, start: Optional[Cell] = None,
                 target: Optional[Cell] = None) -> None:
        self.rows, self.cols = rows, cols
        self.start = start or (0, 0)
        self.target = target or (rows - 1, cols - 1)
        self.grid: List[List[int]] = [[0] * cols for _ in range(rows)]

    @classmethod
    def generate(cls, rows: int, cols: int, density_percent: int, seed: int) -> "Maze":
        m = cls(rows, cols)
        state = (seed * 2654435761 + 12345) % (2 ** 32)
        for r in range(rows):
            for c in range(cols):
                state = (1103515245 * state + 12345) % (2 ** 31)
                if (state >> 8) % 100 < density_percent:
                    m.grid[r][c] = -1
        m.grid[m.start[0]][m.start[1]] = 0
        m.grid[m.target[0]][m.target[1]] = 0
        return m

    def is_wall(self, cell: Cell) -> bool:
        return self.grid[cell[0]][cell[1]] == -1

    def set_wall(self, cell: Cell, value: bool) -> None:
        self.grid[cell[0]][cell[1]] = -1 if value else 0

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def wall_percent(self) -> float:
        walls = sum(row.count(-1) for row in self.grid)
        return 100.0 * walls / (self.rows * self.cols)

    def empty_wave(self) -> List[List[int]]:
        return [[-1 if v == -1 else 0 for v in row] for row in self.grid]


@dataclass
class SearchResult:
    algorithm: str
    found: bool = False
    path: List[Cell] = field(default_factory=list)
    frames: List[Tuple[str, List[Cell]]] = field(default_factory=list)
    wave_a: List[List[int]] = field(default_factory=list)
    wave_b: Optional[List[List[int]]] = None
    meeting: Optional[Tuple[Cell, Cell]] = None
    cycles: int = 0
    expanded: int = 0
    marked: int = 0
    time_ms: float = 0.0

    @property
    def vertices(self) -> int:      
        return len(self.path)


class WaveSearch:
    name = "?"

    def __init__(self, maze: Maze, operator: Operator) -> None:
        self.maze, self.op = maze, operator

    def _trace(self, wave: List[List[int]], cell: Cell) -> List[Cell]:
        out = [cell]
        while wave[cell[0]][cell[1]] > 1:
            r, c = cell
            for dr, dc in self.op.shifts:
                nr, nc = r + dr, c + dc
                if self.maze.in_bounds(nr, nc) and wave[nr][nc] == wave[r][c] - 1 and wave[nr][nc] > 0:
                    cell = (nr, nc)
                    break
            out.append(cell)
        return out

    def search(self) -> SearchResult:
        raise NotImplementedError


class UnidirectionalWave(WaveSearch):
    name = "unidirectional"

    def search(self) -> SearchResult:
        m, res = self.maze, SearchResult(self.name)
        t0 = time.perf_counter()
        wave = m.empty_wave()
        s, t = m.start, m.target
        wave[s[0]][s[1]] = 1
        front, res.frames = [s], [("A", [s])]
        found = s == t
        while front and not found:
            res.cycles += 1
            new = []
            for (r, c) in front:
                res.expanded += 1
                for dr, dc in self.op.shifts:
                    nr, nc = r + dr, c + dc
                    if m.in_bounds(nr, nc) and wave[nr][nc] == 0:
                        wave[nr][nc] = wave[r][c] + 1
                        new.append((nr, nc))
                        if (nr, nc) == t:
                            found = True
                if found:
                    break
            if new:
                res.frames.append(("A", new))
            front = new
        res.found, res.wave_a = found, wave
        if found:
            res.path = list(reversed(self._trace(wave, t)))
        res.marked = sum(1 for row in wave for v in row if v > 0)
        res.time_ms = (time.perf_counter() - t0) * 1000.0
        return res


class BidirectionalWave(WaveSearch):
    name = "bidirectional"

    def search(self) -> SearchResult:
        m, res = self.maze, SearchResult(self.name)
        t0 = time.perf_counter()
        wave_a, wave_b = m.empty_wave(), m.empty_wave()
        s, t = m.start, m.target
        wave_a[s[0]][s[1]] = 1
        wave_b[t[0]][t[1]] = 1
        front_a, front_b = [s], [t]
        res.frames = [("A", [s]), ("B", [t])]
        best: Optional[Tuple[int, Cell, Cell, str]] = None
        if s == t:
            best = (1, s, t, "A")
        while front_a and front_b and best is None:
            res.cycles += 1
            for side in ("A", "B"):
                own, other = (wave_a, wave_b) if side == "A" else (wave_b, wave_a)
                front = front_a if side == "A" else front_b
                new: List[Cell] = []
                for (r, c) in front:
                    res.expanded += 1
                    for dr, dc in self.op.shifts:
                        nr, nc = r + dr, c + dc
                        if not m.in_bounds(nr, nc):
                            continue
                        if other[nr][nc] > 0:               
                            total = own[r][c] + other[nr][nc]
                            if best is None or total < best[0]:
                                best = (total, (r, c), (nr, nc), side)
                        elif own[nr][nc] == 0:
                            own[nr][nc] = own[r][c] + 1
                            new.append((nr, nc))
                if new:
                    res.frames.append((side, new))
                if side == "A":
                    front_a = new
                else:
                    front_b = new
                if best is not None:
                    break
        res.wave_a, res.wave_b = wave_a, wave_b
        if best is not None:
            _, c1, c2, side = best
            a_cell, b_cell = (c1, c2) if side == "A" else (c2, c1)
            res.found, res.meeting = True, (a_cell, b_cell)
            part_a = list(reversed(self._trace(wave_a, a_cell)))
            part_b = self._trace(wave_b, b_cell) if a_cell != b_cell else []
            res.path = part_a + part_b                           
        res.marked = sum(1 for g in (wave_a, wave_b) for row in g for v in row if v > 0)
        res.time_ms = (time.perf_counter() - t0) * 1000.0
        return res


ALGORITHMS = {
    "bi": ("Двонаправлений хвильовий пошук", BidirectionalWave),
    "uni": ("Одно-направлений хвильовий пошук (для порівняння)", UnidirectionalWave),
}


C_FREE, C_WALL = "#ffffff", "#2c3e50"
C_START, C_TARGET, C_PATH, C_MEET = "#2e86de", "#c0392b", "#27ae60", "#8e44ad"
EDIT_MODES = {
    "view": "Перегляд (без редагування)",
    "wall": "Стіни: клік / протягування (додати-прибрати)",
    "start": "Задати початкову вершину (клік)",
    "target": "Задати цільову вершину (клік)",
}


def color_a(k: int, kmax: int) -> str: 
    t = 0 if kmax <= 1 else min(1.0, (k - 1) / (kmax - 1))
    return f"#{int(255 - 25 * t):02x}{int(235 - 110 * t):02x}{int(140 - 80 * t):02x}"


def color_b(k: int, kmax: int) -> str:
    t = 0 if kmax <= 1 else min(1.0, (k - 1) / (kmax - 1))
    return f"#{int(200 - 110 * t):02x}{int(235 - 80 * t):02x}{int(255 - 30 * t):02x}"


class WaveApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Лаб. №4 — Двонаправлений хвильовий пошук у лабіринті")
        root.geometry("1360x900")
        self.maze = Maze.generate(15, 15, 20, 1)
        self.result: Optional[SearchResult] = None
        self.marks: Dict[Cell, Tuple[str, int]] = {}
        self.cell = 40
        self.ox = self.oy = 0
        self.animating = False
        self.job = None
        self.paint_value: Optional[int] = None
        self._build()
        self._redraw()

    def _build(self) -> None:
        main = ttk.Frame(self.root)
        main.pack(fill="both", expand=True)
        panel = ttk.Frame(main, padding=10)
        panel.pack(side="left", fill="y")
        ttk.Label(panel, text="Керування пошуком", font=("Segoe UI", 13, "bold")).pack(anchor="w", pady=(0, 6))

        ttk.Label(panel, text="Алгоритм пошуку").pack(anchor="w")
        self.algo_combo = ttk.Combobox(panel, state="readonly", width=40, values=[v[0] for v in ALGORITHMS.values()])
        self.algo_combo.set(ALGORITHMS["bi"][0])
        self.algo_combo.pack(anchor="w", pady=(0, 6))

        ttk.Label(panel, text="Розмір лабіринту (рядків × стовпців)").pack(anchor="w")
        sf = ttk.Frame(panel); sf.pack(anchor="w", pady=(0, 4))
        self.rows_var, self.cols_var = tk.IntVar(value=15), tk.IntVar(value=15)
        ttk.Spinbox(sf, from_=10, to=30, width=5, textvariable=self.rows_var).pack(side="left")
        ttk.Label(sf, text=" × ").pack(side="left")
        ttk.Spinbox(sf, from_=10, to=30, width=5, textvariable=self.cols_var).pack(side="left")
        ttk.Label(panel, text="Щільність непрохідних клітинок, %").pack(anchor="w")
        self.density_var = tk.IntVar(value=20)
        ttk.Spinbox(panel, from_=0, to=60, width=6, textvariable=self.density_var).pack(anchor="w", pady=(0, 4))
        ttk.Label(panel, text="Seed (номер варіанта лабіринту)").pack(anchor="w")
        self.seed_var = tk.IntVar(value=1)
        ttk.Spinbox(panel, from_=0, to=9999, width=6, textvariable=self.seed_var).pack(anchor="w", pady=(0, 4))
        ttk.Button(panel, text="Побудувати лабіринт", command=self.generate).pack(fill="x", pady=2)
        ttk.Button(panel, text="Очистити всі стіни", command=self.clear_walls).pack(fill="x", pady=2)

        ttk.Label(panel, text="Оператор переходу").pack(anchor="w", pady=(6, 0))
        self.op_combo = ttk.Combobox(panel, state="readonly", width=40, values=[o.name for o in OPERATORS.values()])
        self.op_combo.set(OPERATORS["cross"].name)
        self.op_combo.pack(anchor="w", pady=(0, 4))

        ttk.Label(panel, text="Затримка між кроками хвилі, мс").pack(anchor="w")
        self.delay_var = tk.IntVar(value=150)
        ttk.Scale(panel, from_=1000, to=0, orient="horizontal", variable=self.delay_var).pack(fill="x")
        self.instant = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text="Миттєво (без анімації)", variable=self.instant).pack(anchor="w")
        self.show_nums = tk.BooleanVar(value=True)
        ttk.Checkbutton(panel, text="Показувати значення матриці та мітки хвиль", variable=self.show_nums,
                        command=self._redraw).pack(anchor="w", pady=(0, 6))

        ttk.Button(panel, text="▶ Запустити пошук", command=self.run).pack(fill="x", pady=2)
        ttk.Button(panel, text="⏹ Зупинити анімацію", command=self.stop).pack(fill="x", pady=2)
        ttk.Button(panel, text="Порівняти оператори й алгоритми", command=self.compare).pack(fill="x", pady=2)

        box = ttk.LabelFrame(panel, text="Ручне редагування лабіринту", padding=6)
        box.pack(fill="x", pady=6)
        self.edit_combo = ttk.Combobox(box, state="readonly", width=40, values=list(EDIT_MODES.values()))
        self.edit_combo.set(EDIT_MODES["view"]); self.edit_combo.pack(fill="x")
        self.status = tk.StringVar(value="Готово.")
        ttk.Label(panel, textvariable=self.status, wraplength=300, foreground="#333").pack(anchor="w")

        leg = ttk.LabelFrame(panel, text="Умовні позначення", padding=6); leg.pack(fill="x", pady=6)
        for col, txt in [(C_START, "початкова вершина"), (C_TARGET, "цільова вершина"),
                         (C_WALL, "непрохідна клітинка (-1)"), (C_FREE, "прохідна клітинка (0)"),
                         ("#f5c26b", "хвиля A (від старту)"), ("#7fc4f0", "хвиля B (від цілі)"),
                         (C_MEET, "місце зустрічі хвиль"), (C_PATH, "знайдений шлях")]:
            row = ttk.Frame(leg); row.pack(anchor="w")
            sw = tk.Canvas(row, width=14, height=14, highlightthickness=0)
            sw.create_rectangle(1, 1, 13, 13, fill=col, outline="#888"); sw.pack(side="left", padx=4)
            ttk.Label(row, text=txt).pack(side="left")

        self.canvas = tk.Canvas(main, bg="white", width=1000, height=880)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "paint_value", None))

    def op_key(self) -> str:
        return next((k for k, o in OPERATORS.items() if o.name == self.op_combo.get()), "cross")

    def algo_key(self) -> str:
        return next((k for k, v in ALGORITHMS.items() if v[0] == self.algo_combo.get()), "bi")

    def edit_key(self) -> str:
        return next((k for k, v in EDIT_MODES.items() if v == self.edit_combo.get()), "view")

    def _reset_result(self) -> None:
        self.result, self.marks = None, {}

    def generate(self) -> None:
        self.stop()
        self.maze = Maze.generate(int(self.rows_var.get()), int(self.cols_var.get()),
                                  int(self.density_var.get()), int(self.seed_var.get()))
        self._reset_result()
        self.status.set(f"Лабіринт {self.maze.rows}×{self.maze.cols}, стін {self.maze.wall_percent():.1f}%.")
        self._redraw()

    def clear_walls(self) -> None:
        self.stop()
        self.maze.grid = [[0] * self.maze.cols for _ in range(self.maze.rows)]
        self._reset_result(); self.status.set("Усі стіни вилучено."); self._redraw()

    def _cell_at(self, x: int, y: int) -> Optional[Cell]:
        c, r = int((x - self.ox) // self.cell), int((y - self.oy) // self.cell)
        return (r, c) if self.maze.in_bounds(r, c) else None

    def _press(self, e) -> None:
        cell, mode = self._cell_at(e.x, e.y), self.edit_key()
        if cell is None or mode == "view":
            return
        m = self.maze
        if mode == "wall" and cell not in (m.start, m.target):
            self.paint_value = 0 if m.is_wall(cell) else -1
            self._paint(cell)
        elif mode == "start" and not m.is_wall(cell) and cell != m.target:
            m.start = cell; self._reset_result()
            self.status.set(f"Початкову вершину задано: ({cell[0]+1}, {cell[1]+1})."); self._redraw()
        elif mode == "target" and not m.is_wall(cell) and cell != m.start:
            m.target = cell; self._reset_result()
            self.status.set(f"Цільову вершину задано: ({cell[0]+1}, {cell[1]+1})."); self._redraw()

    def _drag(self, e) -> None:
        if self.edit_key() == "wall" and self.paint_value is not None:
            cell = self._cell_at(e.x, e.y)
            if cell and cell not in (self.maze.start, self.maze.target):
                self._paint(cell)

    def _paint(self, cell: Cell) -> None:
        if self.maze.grid[cell[0]][cell[1]] != self.paint_value:
            self.maze.set_wall(cell, self.paint_value == -1)
            self._reset_result(); self._redraw()

    def _redraw(self, path: Optional[set] = None, meet: Optional[set] = None) -> None:
        cv, m = self.canvas, self.maze
        cv.delete("all")
        W, H = max(cv.winfo_width(), 800), max(cv.winfo_height(), 700)
        self.cell = max(14, min((W - 20) // m.cols, (H - 20) // m.rows))
        self.ox, self.oy = (W - self.cell * m.cols) // 2, (H - self.cell * m.rows) // 2
        fsize = max(6, self.cell // 3)
        ka = max([k for s, k in self.marks.values() if s == "A"] or [1])
        kb = max([k for s, k in self.marks.values() if s == "B"] or [1])
        for r in range(m.rows):
            for c in range(m.cols):
                x0, y0 = self.ox + c * self.cell, self.oy + r * self.cell
                fill, txt = (C_WALL, "-1") if m.grid[r][c] == -1 else (C_FREE, "0")
                if (r, c) in self.marks:
                    side, k = self.marks[(r, c)]
                    fill, txt = (color_a(k, ka) if side == "A" else color_b(k, kb)), str(k)
                if path and (r, c) in path:
                    fill = C_PATH
                if meet and (r, c) in meet:
                    fill = C_MEET
                if (r, c) == m.start:
                    fill = C_START
                if (r, c) == m.target:
                    fill = C_TARGET
                cv.create_rectangle(x0, y0, x0 + self.cell, y0 + self.cell, fill=fill, outline="#999")
                if self.show_nums.get():
                    colr = "white" if fill in (C_WALL, C_START, C_TARGET, C_PATH, C_MEET) else "#333"
                    cv.create_text(x0 + self.cell / 2, y0 + self.cell / 2, text=txt, fill=colr, font=("Segoe UI", fsize))

    def stop(self) -> None:
        self.animating = False
        if self.job:
            try: self.root.after_cancel(self.job)
            except Exception: pass
            self.job = None

    def run(self) -> None:
        self.stop()
        algo_cls = ALGORITHMS[self.algo_key()][1]
        res = algo_cls(self.maze, OPERATORS[self.op_key()]).search()
        self.result, self.marks = res, {}
        if self.instant.get():
            self._finish(res); return
        self.animating = True
        self._step(res, 0)

    def _step(self, res: SearchResult, i: int) -> None:
        if not self.animating:
            return
        if i >= len(res.frames):
            self.animating = False; self._finish(res); return
        side, cells = res.frames[i]
        wave = res.wave_a if side == "A" else res.wave_b
        for cell in cells:
            self.marks[cell] = (side, wave[cell[0]][cell[1]])
        self._redraw()
        self.status.set(f"Крок {i}: хвиля {side}, фронт із {len(cells)} клітинок.")
        self.job = self.root.after(max(1, int(self.delay_var.get())), lambda: self._step(res, i + 1))

    def _finish(self, res: SearchResult) -> None:
        self.marks = {}
        for r in range(self.maze.rows):
            for c in range(self.maze.cols):
                if res.wave_a[r][c] > 0:
                    self.marks[(r, c)] = ("A", res.wave_a[r][c])
                if res.wave_b is not None and res.wave_b[r][c] > 0:
                    self.marks[(r, c)] = ("B", res.wave_b[r][c])
        meet = set(res.meeting) if res.meeting else None
        self._redraw(set(res.path) if res.found else None, meet)
        self._result_window(res)

    def _result_window(self, res: SearchResult) -> None:
        m = self.maze
        w = tk.Toplevel(self.root); w.title("Результат пошуку"); w.geometry("600x600")
        f = ttk.Frame(w, padding=14); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Шлях: " + ("ЗНАЙДЕНО" if res.found else "НЕ ЗНАЙДЕНО"), font=("Segoe UI", 14, "bold"),
                  foreground="#1e8449" if res.found else "#c0392b").pack(anchor="w")
        ttk.Label(f, text=ALGORITHMS["bi" if res.algorithm == "bidirectional" else "uni"][0],
                  font=("Segoe UI", 10, "italic")).pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=6)
        info = [("Оператор переходу", OPERATORS[self.op_key()].name),
                ("Розмір лабіринту", f"{m.rows}×{m.cols}, стін {m.wall_percent():.1f}%"),
                ("Початкова вершина (рядок, стовпець)", f"({m.start[0]+1}, {m.start[1]+1})"),
                ("Цільова вершина (рядок, стовпець)", f"({m.target[0]+1}, {m.target[1]+1})"),
                ("Віддаль між вершинами (кількість вершин)", str(res.vertices) if res.found else "—"),
                ("Кількість кроків шляху", str(res.vertices - 1) if res.found else "—"),
                ("Кількість циклів роботи", str(res.cycles)),
                ("Кількість розкритих вершин", str(res.expanded)),
                ("Кількість позначених вершин", str(res.marked)),
                ("Час пошуку", f"{res.time_ms:.4f} мс")]
        if res.meeting:
            a, b = res.meeting
            info.append(("Місце зустрічі хвиль", f"({a[0]+1},{a[1]+1}) і ({b[0]+1},{b[1]+1})"))
        for a_, b_ in info:
            row = ttk.Frame(f); row.pack(fill="x", pady=2)
            ttk.Label(row, text=a_ + ":", width=40).pack(side="left")
            ttk.Label(row, text=b_, font=("Segoe UI", 9, "bold")).pack(side="left")
        ttk.Separator(f).pack(fill="x", pady=6)
        ttk.Label(f, text="Координати вершин шляху (рядок, стовпець):").pack(anchor="w")
        t = tk.Text(f, height=8, wrap="word")
        t.insert("1.0", " → ".join(f"({r+1},{c+1})" for r, c in res.path) if res.found else "шлях відсутній")
        t.configure(state="disabled"); t.pack(fill="both")
        ttk.Button(f, text="Закрити", command=w.destroy).pack(anchor="e", pady=8)

    def compare(self) -> None:
        m = self.maze
        w = tk.Toplevel(self.root); w.title("Порівняння операторів і алгоритмів"); w.geometry("1100x300")
        f = ttk.Frame(w, padding=10); f.pack(fill="both", expand=True)
        cols = ("Алгоритм", "Оператор переходу", "Знайдено?", "Вершин у шляху", "Циклів", "Розкрито", "Позначено", "Час, мс")
        tv = ttk.Treeview(f, columns=cols, show="headings", height=6)
        for c in cols:
            tv.heading(c, text=c); tv.column(c, width=105, anchor="center")
        tv.column("Алгоритм", width=240, anchor="w"); tv.column("Оператор переходу", width=230, anchor="w")
        for akey, (aname, cls) in ALGORITHMS.items():
            for op in OPERATORS.values():
                r = cls(m, op).search()
                tv.insert("", "end", values=(aname.split(" (")[0], op.name, "так" if r.found else "ні",
                          r.vertices if r.found else "—", r.cycles, r.expanded, r.marked, f"{r.time_ms:.4f}"))
        tv.pack(fill="both", expand=True)
        ttk.Label(f, text=f"Лабіринт {m.rows}×{m.cols}; старт ({m.start[0]+1},{m.start[1]+1}), "
                  f"ціль ({m.target[0]+1},{m.target[1]+1}).", foreground="#555").pack(anchor="w", pady=6)


def main() -> None:
    root = tk.Tk()
    try:
        s = ttk.Style()
        if "clam" in s.theme_names(): s.theme_use("clam")
    except Exception:
        pass
    WaveApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
