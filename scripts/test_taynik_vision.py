#!/usr/bin/env python3
"""Ручная проверка распознавания обезличенного JPG/PNG через Taynik."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import shlex
import sys

from smeta_estimator.ai import (
    TaynikVisionConfig,
    TaynikVisionError,
    check_gateway_access,
    recognize_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Отправить обезличенный план в AI API и проверить строгий JSON."
    )
    parser.add_argument(
        "image",
        type=Path,
        nargs="?",
        help="путь к обезличенному JPG или PNG; если не указан, скрипт его спросит",
    )
    args = parser.parse_args()

    try:
        env = dict(os.environ)
        if not env.get("AI_API_KEY", "").strip():
            env["AI_API_KEY"] = getpass.getpass("Вставьте ключ Taynik: ").strip()

        image = args.image
        if image is None:
            entered = input(
                "Перетащите сюда обезличенный JPG/PNG и нажмите Enter: "
            ).strip()
            # При перетаскивании zsh может добавить кавычки или обратные слеши.
            parts = shlex.split(entered)
            if len(parts) != 1:
                raise TaynikVisionError("Нужно указать путь ровно к одному изображению.")
            image = Path(parts[0])

        config = TaynikVisionConfig.from_env(env)
        print("Проверяю ключ и доступность модели…", file=sys.stderr)
        gateway_diagnostics = check_gateway_access(config)
        print(
            "Ключ принят, модель доступна. Отправляю изображение…",
            file=sys.stderr,
        )
        recognition, diagnostics = recognize_plan(image, config)
    except TaynikVisionError as error:
        print(f"Ошибка проверки: {error}", file=sys.stderr)
        return 1

    print(json.dumps(recognition.to_dict(), ensure_ascii=False, indent=2))
    print("\nДиагностика без секретов:", file=sys.stderr)
    print(
        json.dumps(
            {"gateway": gateway_diagnostics, "recognition": diagnostics},
            ensure_ascii=False,
            indent=2,
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
