from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import UploadFile


ALLOWED_SUFFIXES = {".csv", ".xlsx"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)


class FileStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.upload_dir = self.data_dir / "uploads"
        self.result_dir = self.data_dir / "results"
        self.upload_meta_dir = self.data_dir / "meta" / "uploads"
        self.result_meta_dir = self.data_dir / "meta" / "results"
        for directory in (
            self.upload_dir,
            self.result_dir,
            self.upload_meta_dir,
            self.result_meta_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def save_upload(self, upload: UploadFile) -> dict[str, Any]:
        filename = upload.filename or "dataset.csv"
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("Unsupported file type. Use .csv or .xlsx.")

        file_id = uuid4().hex
        stored_filename = f"{file_id}{suffix}"
        stored_path = self.upload_dir / stored_filename

        with stored_path.open("wb") as destination:
            shutil.copyfileobj(upload.file, destination)

        metadata = {
            "file_id": file_id,
            "filename": _safe_name(filename),
            "suffix": suffix,
            "stored_path": str(stored_path),
            "file_size_bytes": int(stored_path.stat().st_size),
            "created_at": _utcnow_iso(),
        }
        self._write_json(self.upload_meta_dir / f"{file_id}.json", metadata)
        return metadata

    def get_upload_meta(self, file_id: str) -> dict[str, Any]:
        return self._read_json(self.upload_meta_dir / f"{file_id}.json")

    def get_result_meta(self, result_id: str) -> dict[str, Any]:
        return self._read_json(self.result_meta_dir / f"{result_id}.json")

    def load_upload_df(self, file_id: str) -> pd.DataFrame:
        meta = self.get_upload_meta(file_id)
        path = Path(meta["stored_path"])
        if not path.exists():
            raise FileNotFoundError(f"Upload not found for file_id={file_id}")

        suffix = meta["suffix"]
        if suffix == ".csv":
            return pd.read_csv(path)
        if suffix == ".xlsx":
            return pd.read_excel(path, engine="openpyxl")
        raise ValueError("Unsupported file format in metadata.")

    def save_result(
        self,
        df: pd.DataFrame,
        source_file_id: str,
        output_format: str,
    ) -> dict[str, Any]:
        if output_format not in {"csv", "xlsx"}:
            raise ValueError("output_format must be csv or xlsx")

        result_id = uuid4().hex
        suffix = f".{output_format}"
        result_path = self.result_dir / f"{result_id}{suffix}"

        if output_format == "csv":
            df.to_csv(result_path, index=False)
        else:
            df.to_excel(result_path, index=False)

        metadata = {
            "result_id": result_id,
            "source_file_id": source_file_id,
            "output_format": output_format,
            "stored_path": str(result_path),
            "created_at": _utcnow_iso(),
        }
        self._write_json(self.result_meta_dir / f"{result_id}.json", metadata)
        return metadata

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            raise FileNotFoundError(path.name)
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
