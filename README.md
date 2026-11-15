# Music Split

App chạy local, tách một bài hát thành các stem bằng mô hình AI:

- **Lời:** lead vocal (khô), back vocal, echo + reverb
- **Nhạc:** trống, bass, nhạc còn lại

Có 3 mức độ kỹ: Nhanh / Cân bằng / Kỹ (càng kỹ càng nhiều segment chồng lấn, càng chậm).

## Yêu cầu

- Card NVIDIA + driver (chạy CPU được nhưng rất chậm)
- [ffmpeg](https://ffmpeg.org/) có trong PATH
- [uv](https://docs.astral.sh/uv/)

## Cài đặt

```
git clone https://github.com/Vader7-166/music.git
cd music
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements.txt
```

Trên Windows, PyTorch mặc định có thể là bản CPU. Nếu app không dùng GPU, cài lại bản CUDA:

```
uv pip install --python .venv torch --index-url https://download.pytorch.org/whl/cu132 --reinstall
```

## Chạy

Giao diện đồ họa (mở http://127.0.0.1:7860):

```
# Linux
.venv/bin/python app.py
# Windows
.venv\Scripts\python app.py
```

Trong giao diện:

- **Đầu ra:** chọn Đầy đủ / Chỉ vocal / Chỉ nhạc nền / Chỉ trống, hoặc tick từng file muốn xuất. App chỉ chạy những bước cần cho các file đã chọn.
- **Nhiều job:** bấm "Thêm job" nhiều lần để xếp hàng; thanh "Số job chạy cùng lúc" (1–4) quyết định bao nhiêu job chạy song song. Chạy song song tốn thêm VRAM.
- **Tải lại trang:** danh sách job nằm ở server và được lưu trong `output/jobs.json`, nên F5 hay mở lại app vẫn còn. Bấm vào một dòng trong bảng để xem kết quả.

Dòng lệnh:

```
.venv/bin/python split.py "bai_hat.mp3" --preset fast|balanced|quality
.venv/bin/python split.py "bai_hat.mp3" --stems drums bass
```

Các stem: `lead`, `lead_wet`, `back`, `fx`, `drums`, `bass`, `other`, `vocal_full`, `instrumental_full`.

Lần chạy đầu sẽ tự tải các model (khoảng 2,4 GB) vào `models/`. Kết quả nằm trong `output/<tên bài>_<preset>/`.

## Model

| Bước | Model |
|---|---|
| Vocal / instrumental | BS-Roformer-Viperx-1297 |
| Lead / back vocal | Mel-Roformer-Karaoke (aufr33/viperx) |
| Vocal khô / echo + reverb | MelBand Roformer De-Reverb-Echo V2 (Sucial) |
| Trống / bass / nhạc | htdemucs_ft (mức Nhanh dùng htdemucs) |

Chạy qua thư viện [python-audio-separator](https://github.com/nomadkaraoke/python-audio-separator).
