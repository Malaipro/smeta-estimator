"""Amvera and local entry point for the Telegram demo."""

from pathlib import Path
import sys


SOURCE_ROOT = Path(__file__).resolve().parent / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


from smeta_estimator.telegram_bot import run


if __name__ == "__main__":
    run()
