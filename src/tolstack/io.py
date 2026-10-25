"""Loading dimension chains from JSON and CSV files.

JSON format (object form)::

    {
      "links": [
        {"name": "shaft",  "nominal": 50.0, "tol_plus": 0.10,
         "tol_minus": 0.10, "sign": 1},
        {"name": "sleeve", "nominal": 48.0, "tol_plus": 0.05,
         "tol_minus": 0.05, "sign": -1}
      ]
    }

A bare list of link objects is also accepted.  ``tol_minus`` defaults to
``tol_plus`` and ``sign`` defaults to ``1`` when omitted.

CSV format (header row required)::

    name,nominal,tol_plus,tol_minus,sign
    shaft,50.0,0.10,0.10,1
    sleeve,48.0,0.05,0.05,-1

The ``tol_minus`` and ``sign`` columns may be omitted entirely, in which
case the same defaults as JSON apply.
"""

from __future__ import annotations

import csv
import json
import os
from typing import Union

from .core import Chain, Link

__all__ = ["load_chain", "loads_json", "load_csv_text"]


def loads_json(text: str) -> Chain:
    """Parse a chain from a JSON string."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    return Chain.from_dict(data)


def load_csv_text(text: str) -> Chain:
    """Parse a chain from CSV text with a header row."""
    reader = csv.DictReader(text.splitlines())
    if reader.fieldnames is None:
        raise ValueError("CSV input is empty")
    fields = [f.strip() for f in reader.fieldnames if f]
    for required in ("name", "nominal", "tol_plus"):
        if required not in fields:
            raise ValueError(f"CSV is missing required column: {required}")
    links = []
    for lineno, row in enumerate(reader, start=2):
        if row is None or all(v is None or str(v).strip() == "" for v in row.values()):
            continue  # skip blank lines
        try:
            tol_minus_raw = row.get("tol_minus")
            sign_raw = row.get("sign")
            link = Link(
                name=str(row["name"]).strip(),
                nominal=float(row["nominal"]),
                tol_plus=float(row["tol_plus"]),
                tol_minus=(
                    float(tol_minus_raw)
                    if tol_minus_raw is not None and str(tol_minus_raw).strip() != ""
                    else None
                ),
                sign=(
                    int(float(sign_raw))
                    if sign_raw is not None and str(sign_raw).strip() != ""
                    else 1
                ),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid CSV row at line {lineno}: {exc}") from exc
        links.append(link)
    if not links:
        raise ValueError("CSV contains no links")
    return Chain(links)


def load_chain(path: Union[str, os.PathLike]) -> Chain:
    """Load a chain from a ``.json`` or ``.csv`` file based on its suffix."""
    suffix = os.path.splitext(str(path))[1].lower()
    if suffix not in (".json", ".csv"):
        raise ValueError(
            f"unsupported file type {suffix!r}; expected a .json or .csv chain file"
        )
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    if suffix == ".json":
        return loads_json(text)
    return load_csv_text(text)
