"""
Backtest hors-ligne de la stratégie basée sur le modèle de hazard.

MÉTHODOLOGIE (important, à lire) :
- Les données sont coupées en deux : la première moitié sert UNIQUEMENT à
  calibrer le modèle (détection des spikes + fonction de hazard), la seconde
  moitié sert UNIQUEMENT à simuler les trades ("out-of-sample"). C'est
  indispensable — évaluer un modèle sur les données qui ont servi à le
  calibrer donne systématiquement des résultats gonflés et inutiles.
- Le payout est approximé via `PAYOUT_RATIO_APPROX` ci-dessous. Le vrai
  payout d'un contrat Rise/Fall dépend du pricing en temps réel de Deriv
  (proposal endpoint) et varie selon la volatilité du moment — ce backtest
  donne donc un ordre de grandeur, PAS un résultat garanti reproductible en
  live.
- Un backtest positif n'est jamais une preuve suffisante. Teste ensuite en
  compte DÉMO en conditions réelles (latence, slippage, vrai pricing) avant
  d'envisager quoi que ce soit d'autre.
"""

from __future__ import annotations

from dataclasses import dataclass

from hazard_model import HazardModel
import config

PAYOUT_RATIO_APPROX = 0.88  # approximation grossière, à ajuster / vérifier via l'API


@dataclass
class BacktestResult:
    n_trades: int
    n_wins: int
    n_losses: int
    pnl: float
    pnl_no_filter: float  # PnL si on trade la tendance à CHAQUE tick, sans filtre hazard

    @property
    def win_rate(self) -> float:
        return self.n_wins / self.n_trades if self.n_trades else 0.0

    def __str__(self) -> str:
        return (
            f"Trades: {self.n_trades} | Win rate: {self.win_rate:.2%} | "
            f"PnL (stratégie filtrée): {self.pnl:+.2f} | "
            f"PnL (sans filtre, référence): {self.pnl_no_filter:+.2f}"
        )


def _trend_direction(symbol: str) -> str:
    """Boom: dérive vers le bas entre les spikes -> on parie PUT.
    Crash: dérive vers le haut entre les spikes -> on parie CALL."""
    return "PUT" if symbol.upper().startswith("BOOM") else "CALL"


def run_backtest(
    prices: list[float],
    symbol: str = config.SYMBOL,
    duration: int = config.CONTRACT_DURATION,
    stake: float = config.STAKE,
) -> BacktestResult:
    split = len(prices) // 2
    calibration_prices = prices[:split]
    test_prices = prices[split:]

    model = HazardModel().fit(calibration_prices)
    direction = _trend_direction(symbol)

    n_trades = n_wins = n_losses = 0
    n_trades_nf = n_wins_nf = 0
    pnl = 0.0
    pnl_no_filter = 0.0

    spikes_test = HazardModel._detect_spikes(test_prices, model.threshold_mad)

    t_since_spike = 0
    i = 1  # index dans test_prices, on démarre à 1 car _detect_spikes[0] est toujours False
    while i < len(test_prices) - duration:
        t_since_spike += 1
        if spikes_test[i]:
            t_since_spike = 0

        entry_price = test_prices[i]
        exit_price = test_prices[i + duration]
        won = (exit_price > entry_price) if direction == "CALL" else (exit_price < entry_price)

        # Référence "sans filtre" : on trade la tendance à chaque tick disponible
        n_trades_nf += 1
        if won:
            n_wins_nf += 1
            pnl_no_filter += stake * PAYOUT_RATIO_APPROX
        else:
            pnl_no_filter -= stake

        # Stratégie filtrée par le modèle de hazard : on ne trade que quand le
        # hazard courant est significativement RÉDUIT (donc la tendance a
        # statistiquement plus de chances de se poursuivre sans interruption).
        verdict = model.is_significantly_elevated(t_since_spike)
        if verdict is False:
            n_trades += 1
            if won:
                n_wins += 1
                pnl += stake * PAYOUT_RATIO_APPROX
            else:
                n_losses += 1
                pnl -= stake
            i += duration  # pas de chevauchement de positions
        else:
            i += 1

    return BacktestResult(
        n_trades=n_trades,
        n_wins=n_wins,
        n_losses=n_losses,
        pnl=pnl,
        pnl_no_filter=pnl_no_filter,
    )
