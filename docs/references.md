# Nguồn tham khảo và phạm vi sử dụng

Ngày tra cứu: 07/11/2026. Ghi nhận các nguồn thực sự đã đọc trong phiên nghiên
cứu này. Chưa sao chép mã nguồn, puzzle, hình ảnh hoặc asset từ các nguồn dưới
đây vào chương trình. Mục cập nhật implementation cuối file phân biệt phần đã
làm với các đề xuất còn lại.

## 1. Clues by Sam — trang trò chơi và hướng dẫn

- URL: https://cluesbysam.com/
- Loại nguồn: trang game gốc; mục How to play, Clarifying details, Tips và Stuck.
- Đã tham khảo: mở clue theo tiến trình, mọi clue đều đúng, hàng xóm gồm đường
  chéo, thứ tự tên alphabet, tương tác với clue và cơ chế hint hai bước.
- Ý tưởng phù hợp: giữ tên/nghề trên thẻ úp; chọn clue để highlight đối tượng;
  hint đầu tiên gợi ý clue cần đọc, hint tiếp theo chỉ ra người có thể chứng minh.
- Chỉ đọc hướng dẫn công khai; chưa xác minh repo mã nguồn chính thức hoặc giấy
  phép cho phép tái sử dụng code/asset của game.

## 2. Griductive — mô tả ứng dụng Reddit

- URL: https://developers.reddit.com/apps/griductive
- Loại nguồn: trang mô tả ứng dụng trên nền tảng Reddit.
- Đã tham khảo: progressive reveal, hint hai bước, glossary và lưu tiến trình.
- Ý tưởng phù hợp: làm rõ thuật ngữ vùng; phân biệt clue đang dùng và ô được
  hint. Chưa đọc mã client/server của ứng dụng này.
- Chưa xác minh giấy phép tái sử dụng mã hoặc dữ liệu puzzle.

## 3. Griductive — trang được griductive.com chuyển hướng tới

- URL: https://knotwise.games/games/griductive
- Đã truy cập qua https://www.griductive.com/ và đọc trang đích.
- Trang ghi tác giả nội dung: Shawn Liu, Knotwise Games.
- Đã tham khảo: phản hồi riêng cho verdict chưa chứng minh và verdict trái với
  clue; trang mô tả tính toán ngoài main thread để giữ giao diện phản hồi.
- Ý tưởng phù hợp: khi animate agent, hiển thị từng bước và giữ GUI phản hồi.
  Đây là tham khảo mô tả sản phẩm, không phải đã kiểm tra code worker.
- Không dùng trang này để suy ra quyền sở hữu/quan hệ của mọi dự án cùng tên
  Griductive; chưa xác minh repo hay giấy phép mã nguồn chính thức.

## 4. Syps / Nick Sypteras — cbs-bench

- Repo: https://github.com/Syps/cbs-bench
- File code đã đọc:
  https://github.com/Syps/cbs-bench/blob/main/cbs_bench/models.py
- Bản raw đã đọc:
  https://raw.githubusercontent.com/Syps/cbs-bench/main/cbs_bench/models.py
- Loại nguồn: benchmark cộng đồng cho Clues by Sam, không phải mã game gốc.
- Đã tham khảo README và model dữ liệu: trạng thái UNKNOWN/CRIMINAL/INNOCENT,
  metadata tên/nghề, clue, bản ghi phiên chơi và replay.
- Ý tưởng phù hợp: lưu trace để xem lại từng bước. Model tham khảo có cả trường
  đáp án; không đưa cấu trúc đó trực tiếp vào public state/agent của bài này.
- README tự khai MIT và trỏ tới LICENSE; lần tra cứu này chưa lấy được nội dung
  LICENSE để xác minh. Chưa sử dụng code từ repo này.

## 5. safina57 — clues-by-sam-solver

- Repo: https://github.com/safina57/clues-by-sam-solver
- Loại nguồn: solver cộng đồng, không phải mã game gốc.
- Đã đọc README về vòng Observe → Parse → Deduce → Act, Playwright, LLM và Z3.
- Tham khảo cách chia bước quan sát/suy luận/hành động để trình bày agent.
- Không dùng LLM dịch clue hoặc Z3 thay encoder/DPLL của bài: chương trình vẫn
  nhận clue có cấu trúc và tự cài đặt thuật toán chính theo đặc tả.
- Chưa xác minh giấy phép riêng; không sao chép code từ repo.

## Cách trích dẫn khi đưa vào report

Mỗi mục References nên ghi tác giả/tổ chức, tên trang/repo, URL, ngày truy cập
và phần đã tham khảo. Nếu sau này lấy code/asset, bổ sung file, commit cụ thể,
phần thay đổi, giấy phép và thông báo bản quyền tương ứng. Không ghi các ý tưởng
mới đề xuất ở đây thành tính năng đã hoàn thành.

## Nguồn cho lần chỉnh UI responsive

Tra cứu ngày 23/11/2026. Chọn [Anthropic Frontend Design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)
để lên hệ chữ, bảng màu, bố cục và kiểm tra ảnh chụp ở nhiều kích thước.
Đã cân nhắc [Stitch DESIGN.md](https://github.com/google-labs-code/stitch-skills/blob/main/plugins/stitch-utilities/skills/design-md/SKILL.md),
vốn dành cho quy trình thiết kế trong Stitch. Áp dụng hướng dẫn Anthropic trực
tiếp vào Tkinter, không tích hợp mã hoặc công cụ Stitch vào ứng dụng.

Ảnh thứ hai trong yêu cầu ngày 23/11/2026 là ảnh chụp
[Griductive trên Knotwise Games](https://knotwise.games/games/griductive).
Tham khảo tỷ lệ thẻ, cách đặt hướng dẫn cạnh board và nhóm nút gần board.
Dự án dùng bảng màu than xanh và vàng, portrait vẽ bằng code của dự án, cùng
bố cục điều khiển riêng cho Hint, solver và Evidence.

Tham khảo [Microsoft Learn về DPI awareness](https://learn.microsoft.com/en-us/windows/win32/hidpi/setting-the-default-dpi-awareness-for-a-process)
để thiết lập DPI trước khi tạo cửa sổ Tk trên Windows. Kích thước GUI dựa trên
DPI lúc mở ứng dụng.

Trong lượt tinh chỉnh tương tác, áp dụng phần motion của cùng skill cho phản
hồi hover/nhấn và giữ viền focus bàn phím. Nút dùng Segoe UI Semibold, ký hiệu
Unicode và mặt bo góc vẽ bằng Canvas. Hiệu ứng hover và tùy chọn giảm chuyển
động được cài đặt trong Tkinter của dự án. Ảnh Knotwise là tham chiếu về viền
và cách đặt icon bên cạnh nhãn.

### Spotlight và phân nhóm điều khiển

Đọc lại phần [How to Play và Features của Griductive trên Reddit for Developers](https://developers.reddit.com/apps/griductive)
để đối chiếu hai cấp hint: đưa người chơi đến clue làm căn cứ, rồi chỉ ô mục
tiêu. Hai ảnh Knotwise người dùng cung cấp cho thấy cách giảm sáng các thẻ
khác và đưa nút qua chuỗi Hint, Reveal, Clear. Dự án dùng hai viền liền khác
màu để phân biệt chứng cứ và mục tiêu. Reveal chỉ chỉ ra nhân vật cần xét;
việc công bố verdict và lật thẻ vẫn đi qua kiểm tra SAT.

Áp dụng [Anthropic Frontend Design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md)
cho thứ bậc chữ và ưu tiên thao tác. Georgia dùng cho tiêu đề, Trebuchet MS
dùng cho tên và nút, Consolas dùng cho nghề nghiệp. Icon có cỡ và khoảng
cách riêng. Hint, Auto Solve và Check board nằm cạnh board. Puzzles, Restart,
Settings và Solver log nằm ở nhóm quản lý. Solver log giữ truy vấn SAT và
trace để đọc chi tiết khi cần.

Kiểu chữ trên thẻ sau đó được đổi sang **Atkinson Hyperlegible** theo yêu cầu
của người dùng. Dự án phân phối bản Regular và Bold cùng `OFL.txt`, lấy từ
[kho Google Fonts](https://github.com/google/fonts/tree/main/ofl/atkinsonhyperlegible).
Trên Windows, ứng dụng nạp hai tệp font riêng cho tiến trình theo tài liệu
[Microsoft Learn về AddFontResourceExW](https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-addfontresourceexw).

### Rà soát chữ và thuật ngữ trong GUI

Đối chiếu phần microcopy của [Anthropic Frontend Design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md),
hướng dẫn chơi của [Knotwise Griductive](https://knotwise.games/games/griductive)
và [Griductive trên Reddit for Developers](https://developers.reddit.com/apps/griductive).
Tên thao tác viết Title Case và dùng lại xuyên suốt. Câu báo kết quả viết
ngắn, dùng từ người chơi hiểu và phân biệt rõ hai lý do từ chối verdict.
Giao diện dùng **Auto Solve** cho thao tác, **Logs** cho lịch sử và
**Check Board** cho kiểm tra trạng thái. Thanh trạng thái và phần chữ trong
Logs dùng Atkinson Hyperlegible. Font monospace dành cho mốc thời gian.
Các quy ước này cũng được ghi trong `AGENTS.md`.

Trong lần audit vai trò các nút, tham khảo thêm [Griductive Dev Log #1](https://www.reddit.com/r/Griductive/comments/1rkh1dw/griductive_dev_log_1_bug_fixes_logic_tree_and/)
về Logic Tree và [Griductive Archive](https://knotwise.games/games/griductive/archive)
về cách chọn màn. Hai nguồn này được dùng để đối chiếu vai trò của Logs và Puzzles.

Mẫu mô tả chính xác cho lần nghiên cứu này:

> Nhóm tham khảo hướng dẫn công khai của Clues by Sam và Griductive để thiết kế
> tiến trình mở clue, highlight và hint; tham khảo README/model dữ liệu của các
> solver cộng đồng để đánh giá cách tổ chức trạng thái và replay. Chưa tích hợp
> mã nguồn hay asset bên ngoài từ các nguồn này vào chương trình.

## Giải đáp của giảng viên do người dùng cung cấp

Nguồn: bảng hỏi đáp được người dùng gửi trong chat ngày 07/11/2026; chưa có URL
công khai. Đây là yêu cầu bổ sung của môn học, không phải thông tin lấy từ web.

- Đủ 6 map: 2 map 3×3, 2 map 4×4, 2 map 5×5.
- Các map chơi phải có unique solution; các fixture ambiguous/invalid chỉ dùng
  kiểm thử, không tính vào 6 map chơi.
- Load JSON hoặc chọn map trong danh sách đều được chấp nhận.
- Agent tự giải và cần animation/xem lại quá trình giải.
- Hint có thể chỉ người suy ra tiếp theo hoặc người/clue nên cân nhắc.
- Có thể mở sẵn nhiều thẻ, không bắt buộc chỉ một.
- Được dùng mã game Clues by Sam theo giải đáp, với trích dẫn đầy đủ; vẫn phải
  đáp ứng các yêu cầu thuật toán chính của đồ án.

Theo hiện trạng đã rà soát: thiếu 2 map 5×5, một trong 3 map 3×3 là ambiguous
nên không tính là map chơi hợp lệ; các map stalled cần đánh giá lại trải nghiệm
chơi. Ưu tiên bổ sung sáu map unique có thể giải hết không đoán và màn chọn map.

## Tham khảo tương tác qua bốn ảnh người dùng gửi

Nguồn ảnh: người dùng cung cấp trong chat ngày 07/11/2026. Ảnh không kèm URL
trang chụp, vì vậy chưa xác minh được tên game/phiên bản chỉ dựa vào hình.

| Ảnh | Nội dung quan sát | Phạm vi tham khảo |
| --- | --- | --- |
| 1 | Dialog tên/nghề và lựa chọn Innocent/Criminal/Cancel | Đã tự cài đặt dialog theo cùng luồng tương tác |
| 2 | Board với tên/nghề và clue trên thẻ đã mở | Bố cục thông tin và phân biệt trạng thái thẻ; không sao chép portrait/font/asset |
| 3 | Dialog từ chối vì chưa đủ bằng chứng | Đã tự cài đặt dialog riêng cho NOT_PROVABLE và CONTRADICTED |
| 4 | Một thẻ clue được viền nổi bật, các thẻ khác mờ hơn | Hint làm nổi thẻ chứa bằng chứng; app hiện dùng viền tím, không tái tạo lớp dim/viền sọc |

Đã đọc lại mục Stuck trên Clues by Sam và phần Features của trang ứng dụng
Griductive: cả hai mô tả hint hướng người chơi tới clue trước, rồi tới đối tượng
có thể suy ra. Đây là nguồn đối chiếu tương tác, không phải chứng cứ đã đọc code
của cơ chế hint gốc.

### Mẫu trích dẫn cho References và phần thiết kế

- **Clues by Sam.** “How to play”, “Tips”, “Stuck”. https://cluesbysam.com/.
  Truy cập ngày 07/11/2026. Phạm vi: tương tác hint và clue trên thẻ.
- **Griductive.** Trang mô tả ứng dụng, Reddit for Developers.
  https://developers.reddit.com/apps/griductive. Truy cập ngày 07/11/2026.
  Phạm vi: progressive reveal và hint hướng tới clue/đối tượng.
- **Ảnh giao diện do người dùng cung cấp**, trao đổi dự án ngày 07/11/2026.
  URL gốc và phiên bản game chưa được xác minh. Nếu đưa ảnh vào report, bổ sung
  URL game thực tế khi xác định được và ghi rõ ảnh chụp dùng để minh họa tham khảo.

Đoạn mô tả có thể dùng trong report, khớp implementation hiện tại:

> Nhóm tham khảo hướng dẫn tương tác của Clues by Sam, mô tả ứng dụng
> Griductive và ảnh giao diện được cung cấp để thiết kế việc làm nổi bật thẻ
> chứa clue khi yêu cầu Hint. Cơ chế chọn bộ bằng chứng được nhóm tự cài đặt
> bằng phép kiểm tra SAT trên kiến thức công khai. Auto Solve được nhóm tự
> cài đặt để chứng minh và mở lần lượt từng thẻ bằng bộ hẹn giờ Tkinter;
> không sử dụng mã nguồn hoặc asset của game gốc.

## Cập nhật implementation trong phiên này

- Nút GUI Auto Solve bắt đầu mở từng thẻ đã chứng minh, cách nhau 650 ms;
  bấm lại để Pause. Mỗi nhịp mới thực hiện một bước, không giải hết trước rồi
  giả lập các thẻ còn úp. Trace và tổng metrics được cộng dồn qua các nhịp.
- Load, Restart, Hint, Step và gọi verdict dừng animation; callback cũ được
  hủy/vô hiệu hóa. Đóng cửa sổ bằng nút đóng cũng hủy timer.
- Hint làm nổi tất cả thẻ chứa bộ clue đủ chứng minh verdict khi kết hợp với
  known statuses. Bộ clue được thu gọn bằng thử loại từng clue và kiểm tra
  UNSAT dưới giả định ngược; nhiều clue có thể cần kết hợp với nhau.
- Chưa có hiệu ứng xoay 3D hoặc lớp làm mờ nền. Dialog chọn verdict và từ chối
  đã được tự cài đặt trong lượt chỉnh GUI tiếp theo; không sao chép code/asset.
- Một bước SAT vẫn chạy trên UI thread; timer nhường quyền giữa các bước,
  nhưng một truy vấn nặng vẫn có thể gây chậm. Worker là cải tiến tiếp theo.
- API `auto_solve()` dùng cho headless/test vẫn chạy đồng bộ; nút GUI gọi
  `toggle_auto_solve()` để phát từng bước.

## Cập nhật giao diện theo ảnh tham khảo

Theo yêu cầu tiếp theo của người dùng, GUI chuyển sang nền nâu tối, chữ kem,
thẻ bo góc vẽ bằng Canvas, portrait có sẵn từ public metadata và thanh điều khiển
gọn phía trên. Board ở trung tâm; inspector và deduction log chuyển vào cửa sổ
Evidence. Thẻ đã mở dùng header tên/nghề gọn để dành chỗ cho clue; clue dài vẫn
cuộn được và có thể đọc đầy đủ khi bấm thẻ. Kích thước thẻ thích ứng với viewport.

Bấm thẻ úp mở dialog chọn verdict và Cancel. Từ chối có dialog giải thích riêng
cho hai trường hợp; Cancel và việc mở dialog không làm lộ clue. Load cập nhật
tiêu đề, kích thước và tiến độ. Phần tham khảo là palette/bố cục/luồng tương tác
trong ảnh; portrait vẫn được vẽ bằng code của dự án, không lấy asset từ ảnh.
