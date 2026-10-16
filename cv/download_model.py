"""Download the YOLO weights once (needs internet), so the demo laptop can run offline afterwards.

    python cv/download_model.py                 # yolov8n.pt -> cv/models/yolov8n.pt
    python cv/download_model.py yolo11n.pt      # another Ultralytics model
(then set EOIP_YOLO_MODEL=cv/models/yolo11n.pt if you use a non-default model)
"""
import shutil
import sys
from pathlib import Path

MODELS = Path(__file__).resolve().parent / "models"


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "yolov8n.pt"
    MODELS.mkdir(exist_ok=True)
    from ultralytics import YOLO
    model = YOLO(name)                      # downloads to the current folder / Ultralytics cache
    src = Path(getattr(model, "ckpt_path", name))
    dst = MODELS / name
    if src.exists() and src.resolve() != dst.resolve():
        shutil.copy(src, dst)
    print(f"Model ready: {dst}")


if __name__ == "__main__":
    main()
