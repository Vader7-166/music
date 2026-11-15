"""Hàng đợi job tách nhạc: chạy nhiều job song song, hủy được từng job.

Mỗi job là một tiến trình `split.py` riêng, nên hủy job là dừng hẳn tiến trình đó và trả lại VRAM ngay.
Trạng thái nằm ở server (và được ghi ra output/jobs.json) nên tải lại trang hay mở lại app đều không mất.
"""
import atexit
import json
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from split import OUTPUT_DIR, ROOT, STEMS

JOBS_FILE = OUTPUT_DIR / "jobs.json"
UPLOAD_DIR = OUTPUT_DIR / "_uploads"
ACTIVE = ("queued", "running")


class JobManager:
    def __init__(self, limit=2):
        self.lock = threading.Lock()
        self.limit = limit
        self.running = 0
        self.jobs = {}  # id -> job, theo thứ tự tạo
        self.procs = {}  # id -> tiến trình đang chạy
        if JOBS_FILE.exists():
            for job in json.loads(JOBS_FILE.read_text()):
                if job["status"] in ACTIVE:
                    job.update(status="error", message="App bị tắt khi job chưa xong")
                self.jobs[job["id"]] = job
        atexit.register(self.cancel_all)

    def _save(self):
        """Gọi khi đang giữ lock."""
        OUTPUT_DIR.mkdir(exist_ok=True)
        tmp = JOBS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(list(self.jobs.values()), ensure_ascii=False, indent=1))
        tmp.replace(JOBS_FILE)

    def submit(self, audio, preset, stems):
        audio = Path(audio)
        job_id = time.strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        # giữ bản sao riêng: file tạm của trình duyệt upload có thể bị dọn trước khi job tới lượt
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        src = UPLOAD_DIR / f"{job_id}{audio.suffix}"
        shutil.copy(audio, src)
        job = {
            "id": job_id,
            "name": audio.stem,
            "preset": preset,
            "stems": list(stems),
            "status": "queued",
            "message": "Đang chờ",
            "input": str(src),
            "out": str(OUTPUT_DIR / f"{job_id}_{audio.stem}_{preset}"),
            "files": {},
            "zip": None,
            "started": None,
            "finished": None,
        }
        with self.lock:
            self.jobs[job_id] = job
        self._pump()
        return job_id

    def set_limit(self, limit):
        self.limit = int(limit)
        self._pump()

    def get(self, job_id):
        return self.jobs.get(job_id)

    def list(self):
        """Job mới nhất trước."""
        return list(reversed(self.jobs.values()))

    def cancel(self, job_id):
        """Hủy job đang chờ hoặc đang chạy. Trả về True nếu có job bị hủy."""
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job["status"] not in ACTIVE:
                return False
            if job["status"] == "queued":
                self._finish(job, status="cancelled", message="Đã hủy")
                self._save()
            else:
                # _run sẽ thấy cờ này khi tiến trình dừng và tự dọn dẹp
                job["cancel"] = True
                job["message"] = "Đang hủy"
                if job_id in self.procs:
                    self.procs[job_id].terminate()
        return True

    def cancel_all(self):
        return sum(self.cancel(job_id) for job_id in list(self.jobs))

    def _finish(self, job, **result):
        """Gọi khi đang giữ lock."""
        job.pop("cancel", None)
        job.update(result, finished=time.time())
        Path(job["input"]).unlink(missing_ok=True)

    def _pump(self):
        """Khởi chạy các job đang chờ cho tới khi đủ số job chạy song song."""
        with self.lock:
            for job in self.jobs.values():
                if self.running >= self.limit:
                    break
                if job["status"] == "queued":
                    job.update(status="running", message="Đang khởi động", started=time.time())
                    self.running += 1
                    threading.Thread(target=self._run, args=(job,), daemon=True).start()
            self._save()

    def _run(self, job):
        out = Path(job["out"])
        log = out.with_suffix(".log")
        cmd = [sys.executable, str(ROOT / "split.py"), job["input"], "--preset", job["preset"]]
        cmd += ["--out", str(out), "--stems", *job["stems"]]
        code = None
        with open(log, "w") as err:
            with self.lock:
                if not job.get("cancel"):
                    proc = self.procs[job["id"]] = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, text=True)
            if job["id"] in self.procs:
                for line in proc.stdout:
                    if line.startswith("STEP ") and not job.get("cancel"):
                        job["message"] = "Bước " + line[5:].strip()
                code = proc.wait()

        if job.get("cancel"):
            result = {"status": "cancelled", "message": "Đã hủy"}
        elif code == 0:
            job["message"] = "Đóng gói zip"
            result = {
                "status": "done",
                "message": "Xong",
                "files": {stem: str(out / f"{STEMS[stem]}.flac") for stem in STEMS if stem in job["stems"]},
                "zip": shutil.make_archive(str(out), "zip", out),
            }
        else:
            lines = [l for l in log.read_text(errors="replace").splitlines() if l.strip()]
            result = {"status": "error", "message": f"Lỗi: {lines[-1] if lines else f'mã thoát {code}'}"}
        if result["status"] != "error":
            log.unlink()  # chỉ giữ log khi lỗi để còn tra nguyên nhân
        if result["status"] != "done":
            shutil.rmtree(out, ignore_errors=True)
        with self.lock:
            self.procs.pop(job["id"], None)
            self._finish(job, **result)
            self.running -= 1
        self._pump()
