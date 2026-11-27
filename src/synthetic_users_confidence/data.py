"""Importação dos microdados e separação do holdout."""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass, field

import numpy as np

from .scales import SCALES

csv.field_size_limit(sys.maxsize)
STRATA = ("Age", "DevType", "Employment")  # estratos da Stack Overflow 2025


@dataclass
class Dataset:
    rows: list[dict[str, str]] = field(default_factory=list)
    holdout_idx: set[int] = field(default_factory=set)
    escalas: dict[str, dict[str, int]] | None = None  # None: perguntas ativas (scales.SCALES)
    separador: str = ";"  # separa as opções de colunas de múltipla escolha

    def humans(self, question: str, segment: dict[str, str], holdout: bool = True) -> np.ndarray:
        """Respostas humanas ordinais da pergunta, no segmento, dentro ou fora do holdout."""
        scale = (self.escalas or SCALES)[question]
        out: list[int] = []
        for i, row in enumerate(self.rows):
            if (i in self.holdout_idx) != holdout:
                continue
            if any(segment[k] not in (row.get(k) or "").split(self.separador) for k in segment):
                continue
            value = scale.get((row.get(question) or "").strip())
            if value is not None:
                out.append(value)
        return np.asarray(out, dtype=int)


def split_holdout(rows: list[dict[str, str]], fraction: float, seed: int, strata=STRATA) -> set[int]:
    """Holdout por respondente (uma linha cada), estratificado pelas colunas de `strata`."""
    rng = np.random.default_rng(seed)
    groups: dict[tuple[str, ...], list[int]] = {}
    for i, row in enumerate(rows):
        groups.setdefault(tuple(row.get(k) or "" for k in strata), []).append(i)
    chosen: set[int] = set()
    for idxs in groups.values():
        take = int(round(len(idxs) * fraction))
        if take:
            chosen.update(int(x) for x in rng.choice(idxs, size=take, replace=False))
    return chosen


def read_csv(path: str) -> tuple[list[str], list[dict[str, str]]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def load_csv(path: str, holdout_fraction: float = 0.3, seed: int = 42) -> Dataset:
    _, rows = read_csv(path)
    return Dataset(rows=rows, holdout_idx=split_holdout(rows, holdout_fraction, seed))
