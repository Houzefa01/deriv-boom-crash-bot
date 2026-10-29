"""
Modèle statistique — analyse de survie / fonction de hazard
=============================================================

Idée : beaucoup de "stratégies anti-spike" pour Boom/Crash supposent que plus
le temps écoulé depuis le dernier spike est long, plus la probabilité d'un
spike imminent augmente. C'est une hypothèse empirique, pas un fait garanti :
si le générateur de Deriv utilise un tirage à probabilité constante à chaque
tick (processus "sans mémoire", loi géométrique), alors CETTE hypothèse est
fausse et aucune stratégie basée sur le "temps depuis le dernier spike" n'a
de valeur prédictive.

Ce module ne suppose rien : il construit la fonction de hazard empirique
h(t) = P(spike au tick suivant | aucun spike depuis t ticks)
directement à partir des données historiques, avec un intervalle de
confiance (score de Wilson), et te dit honnêtement si un écart significatif
par rapport à la moyenne existe. C'est l'outil académique correct pour
répondre à cette question (équivalent d'une life table en biostatistique).

Aucun résultat n'est garanti : si le test ne trouve rien de significatif,
la bonne décision est de NE PAS trader ce signal.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median

import config


@dataclass
class HazardBucket:
    t: int                # ticks écoulés depuis le dernier spike
    n_observed: int        # nombre de fois où le process a atteint ce "t" sans spike
    n_spikes: int           # nombre de fois où un spike est arrivé exactement à ce "t"

    @property
    def hazard_rate(self) -> float:
        if self.n_observed == 0:
            return 0.0
        return self.n_spikes / self.n_observed

    def wilson_interval(self, z: float = config.CONFIDENCE_Z) -> tuple[float, float]:
        """Intervalle de confiance de Wilson pour une proportion (plus fiable
        qu'un intervalle normal classique sur de petits échantillons / proba
        proches de 0)."""
        n = self.n_observed
        if n == 0:
            return (0.0, 0.0)
        p = self.hazard_rate
        denom = 1 + z ** 2 / n
        centre = p + z ** 2 / (2 * n)
        margin = z * math.sqrt((p * (1 - p) + z ** 2 / (4 * n)) / n)
        low = (centre - margin) / denom
        high = (centre + margin) / denom
        return (max(0.0, low), min(1.0, high))


@dataclass
class HazardModel:
    threshold_mad: float = config.SPIKE_THRESHOLD_MAD
    buckets: dict[int, HazardBucket] = field(default_factory=dict)
    baseline_hazard: float = 0.0
    n_spikes_total: int = 0
    n_ticks_total: int = 0

    # --- Détection des spikes ------------------------------------------------

    @staticmethod
    def _detect_spikes(prices: list[float], threshold_mad: float) -> list[bool]:
        """Retourne un masque booléen: True si le tick i est un spike."""
        returns = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
        abs_returns = [abs(r) for r in returns]
        med = median(abs_returns) if abs_returns else 0.0
        mad = median([abs(r - med) for r in abs_returns]) if abs_returns else 0.0
        # MAD peut être nul si beaucoup de retours identiques -> fallback sur un
        # multiple de la médiane elle-même pour éviter une division par zéro.
        scale = mad if mad > 1e-9 else (med if med > 1e-9 else 1e-9)
        is_spike = [False]  # le premier tick n'a pas de retour associé
        for r in abs_returns:
            is_spike.append(abs(r - med) > threshold_mad * scale)
        return is_spike

    # --- Construction du modèle ------------------------------------------------

    def fit(self, prices: list[float]) -> "HazardModel":
        spikes = self._detect_spikes(prices, self.threshold_mad)
        self.n_ticks_total = len(spikes)
        self.n_spikes_total = sum(spikes)

        t = 0  # ticks depuis le dernier spike
        for is_spike in spikes:
            t += 1
            bucket = self.buckets.setdefault(t, HazardBucket(t=t, n_observed=0, n_spikes=0))
            bucket.n_observed += 1
            if is_spike:
                bucket.n_spikes += 1
                t = 0  # reset du compteur

        self.baseline_hazard = (
            self.n_spikes_total / self.n_ticks_total if self.n_ticks_total else 0.0
        )
        return self

    # --- Interrogation du modèle ------------------------------------------------

    def hazard_at(self, t: int) -> HazardBucket | None:
        return self.buckets.get(t)

    def is_significantly_elevated(self, t: int) -> bool | None:
        """
        Retourne True si le hazard au temps t est significativement AU-DESSUS
        de la moyenne (intervalle de Wilson entièrement au-dessus du baseline),
        False si significativement EN-DESSOUS, None si pas assez de données ou
        pas de différence significative.
        """
        bucket = self.buckets.get(t)
        if bucket is None or bucket.n_observed < config.MIN_BUCKET_SAMPLES:
            return None
        low, high = bucket.wilson_interval()
        if low > self.baseline_hazard:
            return True
        if high < self.baseline_hazard:
            return False
        return None

    def summary_report(self, max_t: int = 30) -> str:
        lines = [
            f"Ticks analysés        : {self.n_ticks_total}",
            f"Spikes détectés        : {self.n_spikes_total}",
            f"Hazard moyen (baseline) : {self.baseline_hazard:.5f}",
            "",
            f"{'t':>4} | {'n_obs':>7} | {'hazard':>8} | {'IC 95%':>17} | verdict",
            "-" * 60,
        ]
        for t in sorted(k for k in self.buckets if k <= max_t):
            b = self.buckets[t]
            low, high = b.wilson_interval()
            verdict = self.is_significantly_elevated(t)
            verdict_str = (
                "ELEVE" if verdict is True else "REDUIT" if verdict is False else "-"
            )
            lines.append(
                f"{t:>4} | {b.n_observed:>7} | {b.hazard_rate:>8.5f} "
                f"| [{low:.5f}, {high:.5f}] | {verdict_str}"
            )
        return "\n".join(lines)
