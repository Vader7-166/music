"""Tách bài hát thành: lead vocal (khô), back vocal, vocal FX (echo+reverb), trống, bass, nhạc.

Dùng: .venv/bin/python split.py <file audio> [--preset fast|balanced|quality]
Giao diện đồ họa: .venv/bin/python app.py
"""
import argparse
import re
import shutil
import subprocess
import time
from pathlib import Path

from audio_separator.separator import Separator

ROOT = Path(__file__).parent
MODEL_DIR = ROOT / "models"
OUTPUT_DIR = ROOT / "output"

# overlap càng cao -> càng nhiều cửa sổ chồng lấn -> kỹ hơn nhưng chậm hơn
PRESETS = {
    "fast": {"overlap": 2, "shifts": 1, "demucs_overlap": 0.25, "demucs": "htdemucs.yaml"},
    "balanced": {"overlap": 4, "shifts": 2, "demucs_overlap": 0.25, "demucs": "htdemucs_ft.yaml"},
    "quality": {"overlap": 8, "shifts": 4, "demucs_overlap": 0.5, "demucs": "htdemucs_ft.yaml"},
}

VOCAL_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
KARAOKE_MODEL = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
DEREVERB_MODEL = "dereverb-echo_mel_band_roformer_sdr_13.4843_v2.ckpt"

# các bước tùy chọn (bước tách vocal / instrumental luôn chạy)
STEPS = ("back", "fx", "instruments")


def run(sep, model, src, work):
    """Chạy 1 model, trả về {tên stem viết thường: đường dẫn file}."""
    t = time.time()
    sep.load_model(model_filename=model)
    stems = {}
    for f in sep.separate(str(src)):
        p = Path(f) if Path(f).is_absolute() else work / f
        stem = re.findall(r"_\(([^)]+)\)_", p.name)[-1].lower()
        stems[stem] = p
    print(f"[{time.time() - t:6.1f}s] {model} -> {sorted(stems)}", flush=True)
    return stems


def separate(audio, preset="balanced", steps=STEPS, on_progress=None):
    """Chạy chuỗi tách, trả về (thư mục output, {slot: đường dẫn file}).

    slot: lead, fx, back, drums, bass, other, vocal_full, instrumental_full
    on_progress(i, n, mô tả) được gọi trước mỗi bước.
    """
    audio = Path(audio)
    cfg = PRESETS[preset]
    out = OUTPUT_DIR / f"{audio.stem}_{preset}"
    work = out / "_work"
    if out.exists():
        shutil.rmtree(out)
    work.mkdir(parents=True)

    sep = Separator(
        log_level=30,
        model_file_dir=str(MODEL_DIR),
        output_dir=str(work),
        output_format="FLAC",
        use_autocast=True,
        mdxc_params={
            "segment_size": 256,
            "override_model_segment_size": False,
            "batch_size": 1,
            "overlap": cfg["overlap"],
            "pitch_shift": 0,
        },
        demucs_params={
            "segment_size": "Default",
            "shifts": cfg["shifts"],
            "overlap": cfg["demucs_overlap"],
            "segments_enabled": True,
        },
    )

    n = 1 + sum(s in steps for s in STEPS)
    i = 0

    def tick(desc):
        nonlocal i
        if on_progress:
            on_progress(i, n, desc)
        i += 1

    # slot -> (tên file, đường dẫn tạm)
    final = {}
    # giải mã bằng ffmpeg trước: đọc được mọi định dạng, kể cả file sai đuôi (vd. m4a đặt tên .mp3)
    wav = work / "input.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-vn", "-ar", "44100", "-ac", "2", str(wav)], check=True
    )

    tick("Tách vocal / instrumental")
    s1 = run(sep, VOCAL_MODEL, wav, work)
    final["vocal_full"] = ("vocal_full", s1["vocals"])
    final["instrumental_full"] = ("instrumental_full", s1["instrumental"])

    lead, lead_name = s1["vocals"], "vocal"
    if "back" in steps:
        tick("Tách lead / back vocal")
        s2 = run(sep, KARAOKE_MODEL, lead, work)
        lead, lead_name = s2["vocals"], "vocal_lead"
        final["lead"] = (lead_name, lead)
        final["back"] = ("vocal_back", s2["instrumental"])
    if "fx" in steps:
        tick("Tách echo / reverb")
        s3 = run(sep, DEREVERB_MODEL, lead, work)
        final["lead"] = (f"{lead_name}_dry", s3["dry"])
        final["fx"] = ("vocal_fx_echo_reverb", s3["no dry"])
    if "instruments" in steps:
        tick("Tách trống / bass / nhạc")
        s4 = run(sep, cfg["demucs"], s1["instrumental"], work)
        final["drums"] = ("drums", s4["drums"])
        final["bass"] = ("bass", s4["bass"])
        final["other"] = ("music_other", s4["other"])

    result = {}
    for slot, (name, path) in final.items():
        result[slot] = out / f"{name}.flac"
        shutil.copy(path, result[slot])
    shutil.rmtree(work)
    return out, result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("--preset", choices=PRESETS, default="balanced")
    args = ap.parse_args()

    t0 = time.time()
    out, _ = separate(args.audio, args.preset)
    print(f"Xong sau {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
