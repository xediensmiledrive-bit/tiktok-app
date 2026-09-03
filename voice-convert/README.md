# Đổi giọng video: nữ miền Bắc → nữ miền Nam

Pipeline dùng ElevenLabs + ffmpeg. Bỏ clip vào `input/`, chạy một lệnh, nhận clip
đã đổi giọng trong `output/`.

## Quy trình

```
input/clip.mp4
   │
   ├─ 1. ffmpeg tách track audio ra khỏi video
   │
   ├─ 2. ElevenLabs Audio Isolation → tách giọng nói khỏi nhạc nền
   │       └─ đo năng lượng phần còn lại để biết clip có nhạc nền đáng kể hay không
   │          (có → giữ làm nền, trộn lại ở bước cuối; không → bỏ)
   │
   ├─ 3a. NHÁNH A — Voice changer (speech-to-speech)
   │       giọng gốc ─→ ElevenLabs STS ─→ giọng mới, giữ nguyên nhịp nói & cảm xúc
   │       → timing khớp video 100%, nhưng vẫn là *phát âm* miền Bắc
   │
   ├─ 3b. NHÁNH B — Đọc lại (speech-to-text → sửa từ vựng → text-to-speech)
   │       giọng gốc ─→ Scribe STT (timestamp từng từ)
   │                 ─→ đổi từ vựng Bắc→Nam (bố mẹ→ba má, đắt→mắc, quả dứa→trái thơm…)
   │                 ─→ TTS từng câu bằng giọng nữ miền Nam
   │                 ─→ canh mỗi câu vào đúng khung thời gian của câu gốc
   │       → ra đúng chất giọng Nam, timing khớp ở mức từng câu
   │
   ├─ 4. Trộn giọng mới với nhạc nền đã giữ lại (nếu có), qua limiter chống clip tiếng
   │
   └─ 5. ffmpeg gắn track audio mới vào video (không re-encode hình)

output/clip__A-voicechanger.mp4   ← nghe thử bản A
output/clip__B-doclai.mp4         ← nghe thử bản B
output/clip__report.json          ← log: câu nào đổi từ gì, lệch timing bao nhiêu
```

Mặc định chạy **cả hai nhánh** để so rồi chọn. Đổi trong `config.json` hoặc
`--mode sts` / `--mode tts` nếu chỉ cần một bản.

## Cần gì trước khi chạy

| | Cách kiểm |
|---|---|
| `ffmpeg` + `ffprobe` | hook `.claude/hooks/session-start.sh` tự cài mỗi session |
| `ELEVENLABS_API_KEY` | biến môi trường (đừng ghi key vào file trong repo) |
| `voice_id` giọng nữ miền Nam | `python3 scripts/list_voices.py --add` |
| Mạng tới `api.elevenlabs.io` | environment phải cho host này qua network policy |

Kiểm hết một lượt:

```bash
python3 scripts/preflight.py
```

## Chạy

```bash
export ELEVENLABS_API_KEY=xi_...

python3 scripts/list_voices.py --add    # chọn giọng, tự ghi voice_id vào config.json
cp ~/clip-can-doi-giong.mp4 input/
./run.sh                                 # xử lý mọi clip trong input/
```

Các tùy chọn hay dùng:

```bash
./run.sh --mode tts            # chỉ nhánh B (đọc lại)
./run.sh --mode sts            # chỉ nhánh A (voice changer)
./run.sh --keep-music yes      # ép giữ nhạc nền, không tự dò
./run.sh --keep-music no       # bỏ hẳn nhạc nền
./run.sh --clean-work          # xoá file trung gian cũ trước khi chạy
```

## Tự kiểm không tốn credit

```bash
python3 scripts/selftest.py
```

Tạo clip test, mock toàn bộ endpoint ElevenLabs, chạy trọn pipeline và kiểm 11 điểm
(độ dài clip ra, phát hiện nhạc nền, gom câu, canh timing, đổi từ vựng). Không gọi
mạng, không tốn credit.

## Sửa từ vựng Bắc → Nam

`data/bac_nam.json` — thêm/sửa thoải mái. Quy tắc:

- Khớp theo biên từ, cụm dài ưu tiên trước cụm ngắn (`bố mẹ` xử lý trước `bố`).
- Giữ nguyên kiểu hoa/thường của từ gốc.
- Từ nằm trong `_rui_ro_can_review.canh_bao` thì **không** tự đổi — chỉ ghi cảnh báo
  ra log để anh tự quyết. Đây là những từ dễ sai nghĩa theo ngữ cảnh
  (`không`→`hông` nghe rất Nam nhưng dễ lệch sắc thái, `hoa`→`bông` sai với tên riêng,
  `xem`/`nhìn`→`coi` không phải lúc nào cũng đúng).

Thử nhanh một câu:

```bash
python3 scripts/north_to_south.py "Bố mẹ tớ bảo thế nào cũng được"
# → Ba má tui bảo sao cũng được
```

## Tinh chỉnh chất lượng

Trong `config.json`:

| Khoá | Ý nghĩa |
|---|---|
| `tts_voice_settings.stability` | thấp → biểu cảm hơn nhưng dễ lạc giọng; cao → đều đều |
| `similarity_boost` | độ giống giọng mẫu |
| `max_stretch` | câu dài hơn khung thì nói nhanh tối đa bao nhiêu lần (1.40 = +40%) |
| `min_stretch` | để gần `1.0`. Câu ngắn hơn khung sẽ **chèn im lặng** chứ không kéo nhão giọng |
| `bed_gain_db` | nhạc nền to/nhỏ so với giọng mới |
| `music_detect_threshold_db` | ngưỡng dò nhạc nền. Dò sai thì dùng `--keep-music yes/no` |
| `segment_gap_threshold` | khoảng lặng (giây) để tách câu khi gom từ |

## Giới hạn cần biết

- **Nhánh B không khớp khẩu hình.** Câu được canh vào đúng khung thời gian của câu
  gốc, nhưng trong một câu thì môi và tiếng không trùng khít. Clip quay cận mặt sẽ
  thấy rõ; clip có b-roll / chữ overlay thì gần như không nhận ra.
- **Câu quá dài** không nhét vừa khung sẽ tràn sang sau. `report.json` ghi rõ câu nào
  và lệch bao nhiêu giây — chỉnh `max_stretch` hoặc cắt câu trong script gốc.
- **Nhánh A giữ phát âm Bắc.** Chỉ đổi người nói, không đổi chất giọng vùng miền.
- **Tách nhạc nền không hoàn hảo.** Nhạc nền dày, giọng chồng nhạc to sẽ để lại tiếng
  vọng nhẹ. Clip nào bị vậy thì `--keep-music no` cho sạch.
- **STT sai chính tả tên riêng.** Tên người/thương hiệu hay bị bóc lệch, kéo theo TTS
  đọc sai. Xem `output/*__report.json` để soát câu trước khi đăng.
