"""Giao diện đồ họa cho split.py. Chạy: .venv/bin/python app.py"""
import time

import gradio as gr

from jobs import JobManager
from split import DEFAULT_STEMS, OUTPUT_DIR

PRESET_CHOICES = [
    ("Nhanh (ít segment)", "fast"),
    ("Cân bằng", "balanced"),
    ("Kỹ (nhiều segment, chậm nhất)", "quality"),
]
# stem -> nhãn hiển thị, theo đúng thứ tự các ô nghe thử
STEM_LABELS = {
    "lead": "Lead vocal (khô)",
    "lead_wet": "Lead vocal (còn echo/reverb)",
    "back": "Back vocal",
    "fx": "Echo + reverb",
    "drums": "Trống",
    "bass": "Bass",
    "other": "Nhạc còn lại",
    "vocal_full": "Vocal đầy đủ",
    "instrumental_full": "Instrumental đầy đủ",
}
CUSTOM = "Tùy chọn"
OUTPUT_SETS = {
    "Đầy đủ": list(DEFAULT_STEMS),
    "Chỉ vocal": ["vocal_full"],
    "Chỉ nhạc nền": ["instrumental_full"],
    "Chỉ trống": ["drums"],
    CUSTOM: None,
}
STATUS_LABELS = {"queued": "Đang chờ", "running": "Đang chạy", "done": "Xong", "error": "Lỗi", "cancelled": "Đã hủy"}
PRESET_LABELS = {value: label.split(" (")[0] for label, value in PRESET_CHOICES}

manager = JobManager()


def elapsed(job):
    if not job["started"]:
        return ""
    return f"{(job['finished'] or time.time()) - job['started']:.0f}s"


def job_rows():
    return [
        [
            job["id"],
            job["name"],
            PRESET_LABELS[job["preset"]],
            ", ".join(STEM_LABELS[s] for s in job["stems"]),
            STATUS_LABELS[job["status"]],
            elapsed(job),
        ]
        for job in manager.list()
    ]


def submit(audio, preset, stems):
    if not audio:
        raise gr.Error("Chưa chọn file audio")
    if not stems:
        raise gr.Error("Chưa chọn đầu ra nào")
    return manager.submit(audio, preset, stems)


def pick_job(rows, evt: gr.SelectData):
    return rows[evt.index[0]][0]


def cancel_job(selected):
    if not manager.cancel(selected):
        gr.Info("Job đang xem không còn chạy hay chờ nên không có gì để hủy")


def cancel_all():
    gr.Info(f"Đã hủy {manager.cancel_all()} job")


def refresh(selected, shown):
    """Cập nhật bảng job và khung chi tiết. Ô nghe thử chỉ được vẽ lại khi job đang xem đổi trạng thái,
    để không ngắt audio đang phát."""
    job = manager.get(selected)
    if not job:
        detail, signature = "Bấm vào một job trong bảng để xem kết quả.", ""
    else:
        detail = f"{job['name']} — {job['message']} ({elapsed(job) or 'chưa chạy'})"
        if job["status"] == "done":
            detail += f"\nThư mục: {job['out']}"
        signature = f"{job['id']}:{job['status']}"
    if signature == shown:
        results = [gr.update()] * (1 + len(STEM_LABELS))
    else:
        files = job["files"] if job else {}
        results = [job["zip"] if job else None]
        results += [gr.Audio(value=files.get(s), visible=s in files) for s in STEM_LABELS]
    return [job_rows(), detail, signature, *results]


with gr.Blocks(title="Music Split") as demo:
    gr.Markdown("# Music Split\nTách lời và nhạc bằng mô hình AI chạy local.")
    selected = gr.BrowserState("", storage_key="music_split_selected_job")
    shown = gr.State("")
    with gr.Row():
        with gr.Column(scale=1):
            audio = gr.Audio(label="Bài hát", type="filepath", sources=["upload"])
            preset = gr.Radio(PRESET_CHOICES, value="balanced", label="Mức độ kỹ")
            output_set = gr.Radio(list(OUTPUT_SETS), value="Đầy đủ", label="Đầu ra")
            stems = gr.CheckboxGroup(
                [(label, stem) for stem, label in STEM_LABELS.items()], value=OUTPUT_SETS["Đầy đủ"], label="File xuất ra"
            )
            btn = gr.Button("Thêm job", variant="primary")
            limit = gr.Slider(1, 4, step=1, value=manager.limit, label="Số job chạy cùng lúc")
        with gr.Column(scale=2):
            table = gr.Dataframe(
                headers=["ID", "Bài", "Mức", "Đầu ra", "Trạng thái", "Thời gian"],
                type="array",
                interactive=False,
                label="Danh sách job (bấm vào một dòng để xem kết quả)",
            )
            detail = gr.Textbox(label="Job đang xem", interactive=False, lines=2)
            with gr.Row():
                cancel_btn = gr.Button("Hủy job đang xem", variant="stop")
                cancel_all_btn = gr.Button("Hủy tất cả job đang chạy / chờ")
            zip_file = gr.File(label="Tải tất cả (zip)")
            players = [gr.Audio(label=label, type="filepath", interactive=False) for label in STEM_LABELS.values()]

    view = dict(fn=refresh, inputs=[selected, shown], outputs=[table, detail, shown, zip_file, *players])
    quiet = dict(show_progress="hidden", api_visibility="private")

    output_set.input(lambda name: gr.update() if name == CUSTOM else OUTPUT_SETS[name], output_set, stems, **quiet)
    stems.input(lambda: CUSTOM, None, output_set, **quiet)
    limit.change(manager.set_limit, limit, None, **quiet)
    btn.click(submit, [audio, preset, stems], selected, api_name="submit").then(**view, **quiet)
    table.select(pick_job, table, selected, **quiet).then(**view, **quiet)
    cancel_btn.click(cancel_job, selected, None, api_name="cancel").then(**view, **quiet)
    cancel_all_btn.click(cancel_all, None, None, api_name="cancel_all").then(**view, **quiet)
    gr.Timer(2).tick(**view, show_progress="hidden", api_name="refresh")
    demo.load(lambda: manager.limit, None, limit, **quiet).then(**view, **quiet)

if __name__ == "__main__":
    demo.queue(default_concurrency_limit=8).launch(inbrowser=True, allowed_paths=[str(OUTPUT_DIR)])
