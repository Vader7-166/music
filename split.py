"""Tách bài hát thành: lead vocal (khô), back vocal, vocal FX (echo+reverb), trống, bass, nhạc.

Dùng: .venv/bin/python split.py <file audio> [--preset fast|balanced|quality] [--stems drums bass ...]
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

# stem -> tên file đầu ra
STEMS = {
    "lead": "vocal_lead_dry",
    "lead_wet": "vocal_lead",
    "back": "vocal_back",
    "fx": "vocal_fx_echo_reverb",
    "drums": "drums",
    "bass": "bass",
    "other": "music_other",
    "vocal_full": "vocal_full",
    "instrumental_full": "instrumental_full",
}
DEFAULT_STEMS = tuple(s for s in STEMS if s != "lead_wet")


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


def separate(audio, preset="balanced", stems=DEFAULT_STEMS, out=None, on_progress=None):
    """Chạy chuỗi tách, trả về (thư mục output, {stem: đường dẫn file}).

    Chỉ chạy những bước cần cho các stem được yêu cầu (khóa của STEMS).
    on_progress(i, n, mô tả) được gọi trước mỗi bước.
    """
    audio = Path(audio)
    cfg = PRESETS[preset]
    stems = set(stems)
    if not stems or stems - set(STEMS):
        raise ValueError(f"stems phải nằm trong {list(STEMS)}")
    if out is None:
        out = OUTPUT_DIR / f"{audio.stem}_{preset}"
        if out.exists():
            shutil.rmtree(out)
    work = Path(out) / "_work"
    work.mkdir(parents=True)

    need_fx = bool(stems & {"lead", "fx"})
    need_back = need_fx or bool(stems & {"lead_wet", "back"})
    need_instruments = bool(stems & {"drums", "bass", "other"})

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

    n = 1 + need_back + need_fx + need_instruments
    i = 0

    def tick(desc):
        nonlocal i
        if on_progress:
            on_progress(i, n, desc)
        i += 1

    # giải mã bằng ffmpeg trước: đọc được mọi định dạng, kể cả file sai đuôi (vd. m4a đặt tên .mp3)
    wav = work / "input.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(audio), "-vn", "-ar", "44100", "-ac", "2", str(wav)], check=True
    )

    tick("Tách vocal / instrumental")
    s1 = run(sep, VOCAL_MODEL, wav, work)
    produced = {"vocal_full": s1["vocals"], "instrumental_full": s1["instrumental"]}
    if need_back:
        tick("Tách lead / back vocal")
        s2 = run(sep, KARAOKE_MODEL, s1["vocals"], work)
        produced["lead_wet"] = s2["vocals"]
        produced["back"] = s2["instrumental"]
    if need_fx:
        tick("Tách echo / reverb")
        s3 = run(sep, DEREVERB_MODEL, produced["lead_wet"], work)
        produced["lead"] = s3["dry"]
        produced["fx"] = s3["no dry"]
    if need_instruments:
        tick("Tách trống / bass / nhạc")
        s4 = run(sep, cfg["demucs"], s1["instrumental"], work)
        produced["drums"] = s4["drums"]
        produced["bass"] = s4["bass"]
        produced["other"] = s4["other"]

    result = {}
    for stem in STEMS:
        if stem in stems:
            result[stem] = Path(out) / f"{STEMS[stem]}.flac"
            shutil.copy(produced[stem], result[stem])
    shutil.rmtree(work)
    return Path(out), result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audio", type=Path)
    ap.add_argument("--preset", choices=PRESETS, default="balanced")
    ap.add_argument("--stems", nargs="+", choices=STEMS, default=DEFAULT_STEMS, help="các stem cần xuất")
    ap.add_argument("--out", type=Path, help="thư mục đầu ra (mặc định: output/<tên bài>_<preset>)")
    args = ap.parse_args()

    def on_progress(i, n, desc):
        print(f"STEP {i + 1}/{n}: {desc}", flush=True)

    t0 = time.time()
    out, _ = separate(args.audio, args.preset, args.stems, args.out, on_progress)
    print(f"Xong sau {time.time() - t0:.0f}s -> {out}")


if __name__ == "__main__":
    main()
