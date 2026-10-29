"""
Gestion du risque — la partie la plus importante du bot, statistiquement
parlant. Un modèle prédictif imparfait combiné à une bonne gestion du risque
survit. Un modèle parfait sans gestion du risque finit toujours par exploser
(taille de mise qui grandit après une perte, absence de limite quotidienne...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import config


@dataclass
class RiskManager:
    max_daily_loss: float = config.MAX_DAILY_LOSS
    max_consecutive_losses: int = config.MAX_CONSECUTIVE_LOSSES
    stake: float = config.STAKE

    _day: date = field(default_factory=date.today)
    _daily_pnl: float = 0.0
    _consecutive_losses: int = 0
    _trade_log: list[dict] = field(default_factory=list)

    def _roll_day_if_needed(self) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._daily_pnl = 0.0
            self._consecutive_losses = 0

    def can_trade(self) -> tuple[bool, str]:
        self._roll_day_if_needed()
        if self._daily_pnl <= -abs(self.max_daily_loss):
            return False, (
                f"Limite de perte quotidienne atteinte "
                f"({self._daily_pnl:.2f} <= -{self.max_daily_loss})."
            )
        if self._consecutive_losses >= self.max_consecutive_losses:
            return False, (
                f"{self._consecutive_losses} pertes consécutives — "
                f"arrêt de sécurité (max autorisé: {self.max_consecutive_losses})."
            )
        return True, "ok"

    def next_stake(self) -> float:
        """Mise fixe par défaut. Ne JAMAIS faire de martingale (doubler après
        une perte) — c'est un des pièges les plus fréquents et les plus
        destructeurs sur Boom/Crash, car un run de pertes ordinaire suffit à
        ruiner un compte avec ce type de gestion de mise."""
        return self.stake

    def record_result(self, profit: float) -> None:
        self._roll_day_if_needed()
        self._daily_pnl += profit
        if profit < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._trade_log.append(
            {
                "day": str(self._day),
                "profit": profit,
                "daily_pnl": self._daily_pnl,
                "consecutive_losses": self._consecutive_losses,
            }
        )

    @property
    def daily_pnl(self) -> float:
        self._roll_day_if_needed()
        return self._daily_pnl

    @property
    def trade_log(self) -> list[dict]:
        return list(self._trade_log)
