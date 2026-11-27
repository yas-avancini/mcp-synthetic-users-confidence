"""Métricas de distribuição para escalas ordinais de 1 a 5."""

from __future__ import annotations

import numpy as np

K = 5
MAX_STD = (K - 1) / 2  # desvio máximo possível em escala 1..5


def counts(values: np.ndarray) -> list[int]:
    return [int((values == v).sum()) for v in range(1, K + 1)]


def pmf(values: np.ndarray) -> np.ndarray:
    c = np.asarray(counts(values), dtype=float)
    return c / c.sum()


def summary(values: np.ndarray) -> dict:
    return {
        "escala": "likert5",
        "contagens": counts(values),
        "media": round(float(values.mean()), 3),
        "variancia": round(float(values.var(ddof=1)) if len(values) > 1 else 0.0, 3),
    }


def emd(p: np.ndarray, q: np.ndarray) -> float:
    """Distância de Wasserstein em escala ordinal, normalizada para 0..1."""
    return float(np.abs(np.cumsum(p) - np.cumsum(q)).sum() / (K - 1))


def total_variation(p: np.ndarray, q: np.ndarray) -> float:
    return float(0.5 * np.abs(p - q).sum())


def dispersion(values: np.ndarray) -> float:
    """Desvio padrão das amostras sobre o máximo possível (0 = idêntico, 1 = polarizado)."""
    if len(values) < 2:
        return float("nan")
    return float(values.std(ddof=1) / MAX_STD)


def bootstrap_emd_ci(
    synthetic: np.ndarray, human: np.ndarray, n_boot: int = 1000, seed: int = 0
) -> tuple[float, float]:
    """Intervalo de 95% da EMD sob o ruído de amostragem dos humanos (reamostra os dois lados)."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        s = rng.choice(synthetic, size=len(synthetic), replace=True)
        h = rng.choice(human, size=len(human), replace=True)
        out.append(emd(pmf(s), pmf(h)))
    lo, hi = np.percentile(out, [2.5, 97.5])
    return float(lo), float(hi)


def human_noise_floor(human: np.ndarray, n_synth: int, n_boot: int = 500, seed: int = 1) -> float:
    """EMD típica entre duas amostras humanas: o melhor que um usuário poderia atingir."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_boot):
        a = rng.choice(human, size=n_synth, replace=True)
        b = rng.choice(human, size=len(human), replace=True)
        out.append(emd(pmf(a), pmf(b)))
    return float(np.median(out))


Z95 = 1.96


def margin_of_error_mean(values: np.ndarray) -> float | None:
    """Margem de erro (95%) da média, em pontos da escala 1..5."""
    if len(values) < 2:
        return None
    return float(Z95 * values.std(ddof=1) / np.sqrt(len(values)))


def margin_of_error_proportion(n: int) -> float | None:
    """Margem de erro (95%) conservadora de uma proporção (pior caso, p = 0,5), em pontos percentuais."""
    if n < 1:
        return None
    return float(100 * Z95 * np.sqrt(0.25 / n))


def permutation_pvalue(synthetic: np.ndarray, human: np.ndarray, n_perm: int = 2000, seed: int = 2) -> float:
    """p-value do teste de permutação: chance de ver uma EMD tão grande se os dois grupos viessem da mesma distribuição."""
    rng = np.random.default_rng(seed)
    observed = emd(pmf(synthetic), pmf(human))
    pooled = np.concatenate([synthetic, human])
    ns = len(synthetic)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        if emd(pmf(pooled[:ns]), pmf(pooled[ns:])) >= observed:
            hits += 1
    return (hits + 1) / (n_perm + 1)


def variance_ci(values: np.ndarray, n_boot: int = 2000, seed: int = 3) -> tuple[float, float] | None:
    """Intervalo bootstrap de 95% da variância."""
    if len(values) < 2:
        return None
    rng = np.random.default_rng(seed)
    out = [rng.choice(values, size=len(values), replace=True).var(ddof=1) for _ in range(n_boot)]
    lo, hi = np.percentile(out, [2.5, 97.5])
    return float(lo), float(hi)


def variance_ratio_pvalue(synthetic: np.ndarray, human: np.ndarray, n_perm: int = 2000, seed: int = 4) -> float:
    """p-value (permutação) de que as duas variâncias sejam iguais, sobre |log da razão|."""
    rng = np.random.default_rng(seed)

    def stat(a: np.ndarray, b: np.ndarray) -> float:
        va, vb = a.var(ddof=1), b.var(ddof=1)
        if va <= 0 or vb <= 0:
            return float("inf")
        return abs(float(np.log(va / vb)))

    observed = stat(synthetic, human)
    pooled = np.concatenate([synthetic, human])
    ns = len(synthetic)
    hits = 0
    for _ in range(n_perm):
        rng.shuffle(pooled)
        if stat(pooled[:ns], pooled[ns:]) >= observed:
            hits += 1
    return (hits + 1) / (n_perm + 1)
