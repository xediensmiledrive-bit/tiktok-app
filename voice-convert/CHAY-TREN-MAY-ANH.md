# Chạy đổi giọng hàng loạt trên máy anh

## Vì sao phải chạy trên máy anh

Phiên làm việc này mở từ claude.ai/code trên trình duyệt/điện thoại, nên Claude
chạy trong một container trên cloud — không phải trên PC của anh. Container đó
không nhìn thấy ổ `Y:` hay bất kỳ ổ đĩa nào của anh.

Nhưng phần chạy hàng loạt **không cần Claude ngồi cạnh**. Toàn bộ chuỗi xử lý đã
nằm trong `scripts/batch.py`; nó tự gọi ElevenLabs và tự chạy ffmpeg. Anh chỉ
bấm một lệnh trên PC là nó xử lý hết cả thư mục.

## Cài một lần

1. **Python 3** — tải ở python.org, nhớ tích *Add Python to PATH* khi cài.
2. **ffmpeg**:
   ```
   winget install Gyan.FFmpeg
   ```
   Cài xong **mở lại Command Prompt** thì PATH mới có hiệu lực.
3. **Thư viện**:
   ```
   python -m pip install requests
   ```
4. **Khoá API** — tạo file `.env` đặt cạnh `config.json`, nội dung một dòng:
   ```
   ELEVENLABS_API_KEY=xi_...
   ```
   File này đã nằm trong `.gitignore` nên không bao giờ lọt lên git.

## Chạy

Bấm đúp `chay-windows.bat`, hoặc từ Command Prompt:

```
python scripts\batch.py --pha 1 --input "Y:\CLAUDE\Workflow Automation\Change-tone\Video dau vao"
```

Sửa đường dẫn trong file `.bat` cho khớp máy anh nếu khác.

## Hai pha, và vì sao tách ra

| Pha | Làm gì | Chi phí |
|---|---|---|
| **1** | Bóc chữ, chuyển từ vựng Bắc→Nam | ~24% |
| **2** | Đọc lại, canh nhịp, cân tông, chèn nhạc, ghép | ~76% |

Giữa hai pha anh mở thư mục `work\<tên clip>\nam.txt` đọc lại bản chữ. Sai chỗ
nào sửa chỗ đó rồi lưu — pha 2 đọc đúng file đó. Không tách pha thì mỗi lần sai
một chữ là đốt lại toàn bộ tiền đọc.

Bộ từ điển đã chặn được vài chỗ nguy hiểm (`động cơ`, `không dây`, `chỉ số`),
nhưng mỗi kênh có thuật ngữ riêng. Thấy từ nào bị đổi sai thì thêm vào
`data/bac_nam.json`, mục `_cum_bao_ve.cum`.

## Dừng giữa chừng thì sao

Chạy lại là được. Clip nào đã có file trong thư mục ra thì bỏ qua. Muốn làm lại
hết thì thêm `--lam-lai`.

## Kiểm tra tự động

Mỗi clip xong đều được kiểm bốn điểm, ghi vào `<tên>__bao-cao.json`:

- đủ khung hình so với bản gốc
- luồng video giống bit-for-bit (không re-encode, không mất chất hình)
- thời lượng khớp
- đỉnh thật dưới −0.3 dBTP (không vỡ tiếng)

Clip nào không đạt sẽ in cảnh báo ngay trên màn hình.

## Cấu hình

Mọi thứ trong `config.json`. Những khoá hay đụng tới:

| Khoá | Ý nghĩa |
|---|---|
| `voice_id` / `tts_model_id` | giọng và model. Đang là Trâm + `eleven_v3` |
| `muc_do_doi_tu_vung` | `nhe` hoặc `dam`. Đang để `dam` |
| `nhac_nen.file` | để rỗng nếu không muốn chèn nhạc |
| `nhac_nen.gain_db` | `-2` = mức Rõ. Số âm hơn thì nhạc nhỏ lại |
| `nhac_nen.duck_db` | nhạc lùi bao nhiêu dB khi có tiếng nói |

## Nếu anh muốn Claude chạy trực tiếp trên máy

Cài Claude Code CLI trên PC rồi mở trong thư mục này. Lúc đó Claude thấy ổ `Y:`
và chạy được trực tiếp. Nhưng cho việc lặp lại 15 clip thì không cần —
`batch.py` tự chạy hết, không cần AI trong lúc chạy.
