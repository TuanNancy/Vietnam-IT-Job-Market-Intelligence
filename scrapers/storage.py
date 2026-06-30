from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def ensure_parent(path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def append_jsonl(path: str | Path, record: dict[str, Any]) -> None:
    output_path = ensure_parent(path)
    with output_path.open("a", encoding="utf-8") as file:
        json.dump(record, file, ensure_ascii=False)
        file.write("\n")


def read_jsonl(path: str | Path) -> Iterable[dict[str, Any]]:
    input_path = Path(path)
    if not input_path.exists():
        return

    with input_path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSONL at {input_path}:{line_number}") from error


def existing_urls(path: str | Path) -> set[str]:
    input_path = Path(path)
    if not input_path.exists():
        return set()

    urls: set[str] = set()
    for record in read_jsonl(input_path):
        url = record.get("url")
        if isinstance(url, str):
            urls.add(url)
    return urls
