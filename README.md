# Griductive-Solver

Dự án giải bài toán Griductive — Môn học: Cơ sở Trí tuệ Nhân tạo.
Kiến trúc phần mềm: **Modular Monolith** kết hợp giải thuật DPLL SAT Solver và suy diễn logic mệnh đề (Logical Entailment).

## Cấu trúc thư mục mã nguồn (`src/`)

```text
src/
├── main.py                     # CLI & GUI launcher chính
└── griductive/
    ├── domain/                 # [Module 1: Nghiệp vụ cốt lõi & Ngữ nghĩa]
    │   ├── model.py            # Value objects: CellId, Character, Clue, PublicState, Puzzle
    │   ├── regions.py          # Hình học bàn cờ (Row, Col, Neighbors, CommonNeighbors)
    │   └── semantics.py        # Trình đánh giá chân trị độc lập (Ground truth check)
    │
    ├── solver/                 # [Module 2: Động cơ Logic & SAT Solver]
    │   ├── cnf.py              # Mã hóa CNF (Sequential Counter, Tseitin parity)
    │   ├── dpll.py             # DPLL SAT Solver thuần túy & bộ đếm metric
    │   ├── kb.py               # Cơ sở tri thức công khai (KnowledgeBase)
    │   └── logic.py            # Suy diễn Entailment, Hint & Proof service
    │
    ├── game/                   # [Module 3: Động cơ trò chơi & Điều phối]
    │   ├── engine.py           # GameEngine (giữ đáp án bí mật, lật thẻ an toàn)
    │   ├── controller.py       # GameController (cầu nối tương tác, hint, auto-solve)
    │   └── io.py               # Nạp và kiểm tra cú pháp file Puzzle JSON
    │
    ├── analysis/               # [Module 4: Kiểm định & Thực nghiệm]
    │   ├── validation.py       # Kiểm định nghiệm duy nhất & tính giải được
    │   └── experiments.py      # Pipeline đo đạc thực nghiệm, xuất CSV/JSON/Markdown
    │
    ├── ui/                     # [Module 5: Trình diễn]
    │   └── gui.py              # Giao diện đồ họa người dùng Tkinter
    │
    ├── (model|cnf|...facades).py # Top-level facades hỗ trợ tương thích ngược
    └── __init__.py             # Root package exports
```

## Hướng dẫn cài đặt & Chạy

### 1. Cài đặt môi trường
Yêu cầu Python >= 3.10.

```bash
pip install -e .
# Hoặc cài đặt các phụ thuộc kiểm thử:
pip install pytest pytest-cov typeguard
```

### 2. Khởi chạy ứng dụng

- **Chạy giao diện đồ họa (GUI):**
  ```bash
  python src/main.py gui
  # hoặc chỉ định puzzle cụ thể:
  python src/main.py gui --puzzle puzzles/puzzle_3x3_progressive.json
  ```

- **Kiểm định file puzzle (Validation):**
  ```bash
  python src/main.py validate puzzles/puzzle_3x3_progressive.json
  ```

- **Chạy tự động giải câu đố (Auto Solve qua CLI):**
  ```bash
  python src/main.py solve puzzles/puzzle_3x3_progressive.json
  ```

- **Chạy thực nghiệm hiệu năng (Experiments):**
  ```bash
  python src/main.py experiment --repetitions 5 --print-summary
  ```

- **Chạy kiểm thử tự động (Unit & Integration tests):**
  ```bash
  pytest
  ```

# Reading clues

Revealed cards display their clues as English sentences directly on the board.
Click a revealed card to inspect its full clue and highlight the referenced cells.
Face-down cards show public names and professions; their clues appear only after
a proven verdict. The same structured level data generates the card and inspector
text, so no natural-language parsing or duplicate handwritten clues are needed.
Long clues scroll within the card and inspector without resizing the grid.
Larger boards can be scrolled horizontally and vertically.

See `docs/implementation-review.md` for the PDF compliance review and remaining work.
See `docs/references.md` for consulted game/solver sources, usage scope, and
the instructor's additional six-map and animation requirements.

The GUI Auto Solve button reveals one proven card every 650 ms; click again to
pause. Restart/Load cancel the current animation. Hint marks the revealed cards
whose clues, together with known statuses, prove a next verdict. Read highlighted
clues together: a single highlighted clue need not prove the verdict by itself.

The desktop board uses a warm brown card layout. Click a face-down character
for the verdict dialog; click a revealed card to read its full clue. The Evidence
button opens the detailed inspector and deduction history in a separate window.

