"""Giao diện đồ họa cho split.py. Chạy: .venv/bin/python app.py"""
import shutil
import time

import gradio as gr

from split import OUTPUT_DIR, separate

PRESET_CHOICES = [
    ("Nhanh (ít segment)", "fast"),
    ("Cân bằng", "balanced"),
    ("Kỹ (nhiều segment, chậm nhất)", "quality"),
]
STEP_CHOICES = [
    ("Tách lead / back vocal", "back"),
    ("Tách echo + reverb khỏi vocal", "fx"),
    ("Tách trống / bass / nhạc", "instruments"),
]
# slot -> nhãn hiển thị, theo đúng thứ tự các ô nghe thử
SLOTS = {
    "lead": "Lead vocal",
    "back": "Back vocal",
    "fx": "Echo + reverb",
    "drums": "Trống",
    "bass": "Bass",
    "other": "Nhạc còn lại",
    "vocal_full": "Vocal đầy đủ",
    "instrumental_full": "Instrumental đầy đủ",
}


def process(audio, preset, steps, progress=gr.Progress()):
    if not audio:
        raise gr.Error("Chưa chọn file audio")
    t0 = time.time()
    out, stems = separate(
        audio, preset, steps, on_progress=lambda i, n, desc: progress(i / n, desc=f"Bước {i + 1}/{n}: {desc}")
    )
    progress(1, desc="Đóng gói zip")
    zip_path = shutil.make_archive(str(out), "zip", out)
    status = f"Xong sau {time.time() - t0:.0f}s. Thư mục: {out}"
    players = [gr.Audio(value=str(stems[s]) if s in stems else None, visible=s in stems) for s in SLOTS]
    return [status, zip_path, *players]


with gr.Blocks(title="Music Split") as demo:
    gr.Markdown("# Music Split\nTách lời và nhạc bằng mô hình AI chạy local.")
    with gr.Row():
        with gr.Column(scale=1):
            audio = gr.Audio(label="Bài hát", type="filepath", sources=["upload"])
            preset = gr.Radio(PRESET_CHOICES, value="balanced", label="Mức độ kỹ")
            steps = gr.CheckboxGroup(STEP_CHOICES, value=[v for _, v in STEP_CHOICES], label="Các bước")
            btn = gr.Button("Tách", variant="primary")
            status = gr.Textbox(label="Trạng thái", interactive=False)
            zip_file = gr.File(label="Tải tất cả (zip)")
        with gr.Column(scale=2):
            players = [gr.Audio(label=label, type="filepath", interactive=False) for label in SLOTS.values()]
    btn.click(process, [audio, preset, steps], [status, zip_file, *players])

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=1).launch(inbrowser=True, allowed_paths=[str(OUTPUT_DIR)])
