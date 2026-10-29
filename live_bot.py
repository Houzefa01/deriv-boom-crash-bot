"""
Point d'entrée du bot.

Usage :
  # 1. Analyse uniquement : télécharge l'historique, affiche le rapport de
  #    hazard et le résultat du backtest. NE PLACE AUCUN TRADE.
  python live_bot.py --analyze

  # 2. Trading en boucle sur le compte associé au token fourni (démo par
  #    défaut si ton token est un token de compte démo — c'est TOI qui
  #    contrôles ça en choisissant le token, pas un flag du script).
  python live_bot.py --run --max-trades 20

Sécurité :
  - Ce script ne fait AUCUNE différence technique entre démo et réel : c'est
    le TOKEN que tu fournis qui détermine le compte utilisé. Utilise un
    token de compte démo tant que tu n'as pas validé la stratégie.
  - Toutes les limites de risque sont dans config.py et risk_manager.py.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
from datetime import datetime

import config
from backtest import run_backtest, _trend_direction
from deriv_client import DerivClient
from hazard_model import HazardModel
from risk_manager import RiskManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("live_bot")

LOG_FILE = "trade_log.csv"


def _ensure_log_file() -> None:
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(
                ["timestamp", "symbol", "direction", "stake", "contract_id", "profit"]
            )


def _append_log(row: list) -> None:
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow(row)


async def analyze(symbol: str) -> HazardModel:
    client = DerivClient()
    await client.connect()
    try:
        log.info("Téléchargement de %d ticks pour %s...", config.HISTORY_COUNT, symbol)
        prices = await client.get_tick_history(symbol, config.HISTORY_COUNT)
        log.info("%d ticks reçus.", len(prices))

        model = HazardModel().fit(prices)
        print("\n=== Rapport du modèle de hazard (calibré sur tout l'historique) ===")
        print(model.summary_report())

        print("\n=== Backtest out-of-sample (calibration/test séparés) ===")
        result = run_backtest(prices, symbol=symbol)
        print(result)
        print(
            "\nRappel : un backtest positif n'est pas une garantie de résultat "
            "futur. Passe par un compte démo avant toute mise en réel."
        )
        return model
    finally:
        await client.disconnect()


async def run_live(symbol: str, max_trades: int | None) -> None:
    _ensure_log_file()
    client = DerivClient()
    await client.connect()

    risk = RiskManager()
    direction = _trend_direction(symbol)

    log.info("Calibration du modèle sur l'historique récent...")
    prices = await client.get_tick_history(symbol, config.HISTORY_COUNT)
    model = HazardModel().fit(prices)
    log.info("Modèle calibré. Hazard moyen: %.5f", model.baseline_hazard)

    spikes_ref = HazardModel._detect_spikes(prices, model.threshold_mad)
    t_since_spike = 0
    for is_spike in spikes_ref:
        t_since_spike = 0 if is_spike else t_since_spike + 1

    n_trades_done = 0
    active_contract_expiry_tick = -1
    tick_counter = 0

    try:
        stream = await client.subscribe_ticks(symbol)
        done = asyncio.Event()

        def on_tick(tick):
            nonlocal t_since_spike, n_trades_done, active_contract_expiry_tick, tick_counter
            tick_counter += 1

            # Heuristique de spike en direct : réutilise l'échelle calibrée sur
            # l'historique (on ne peut pas recalculer la MAD à chaque tick, ce
            # serait trop coûteux et instable sur un seul point).
            t_since_spike += 1

            can_trade, reason = risk.can_trade()
            if not can_trade:
                log.warning("Trading suspendu: %s", reason)
                return

            if max_trades is not None and n_trades_done >= max_trades:
                log.info("Nombre maximum de trades atteint (%d). Arrêt.", max_trades)
                done.set()
                return

            if tick_counter <= active_contract_expiry_tick:
                return  # une position est déjà ouverte, on attend son expiration

            verdict = model.is_significantly_elevated(t_since_spike)
            if verdict is not False:
                return  # pas de signal exploitable à cet instant

            stake = risk.next_stake()
            log.info(
                "Signal détecté (t=%d depuis dernier spike) -> ouverture %s, mise %.2f",
                t_since_spike, direction, stake,
            )
            active_contract_expiry_tick = tick_counter + config.CONTRACT_DURATION

            def _mark_done():
                nonlocal n_trades_done
                n_trades_done += 1

            asyncio.create_task(
                _place_and_track(client, risk, symbol, direction, stake, _mark_done)
            )

        # NOTE: `python_deriv_api` utilise rx (ReactiveX) sur la boucle asyncio
        # courante. `asyncio.create_task` dans `on_tick` suppose que ce callback
        # est bien exécuté dans le contexte de cette boucle — teste ce point en
        # démo avant de t'y fier ; adapte avec `asyncio.run_coroutine_threadsafe`
        # si jamais le callback arrive sur un autre thread/scheduler.
        stream.subscribe(on_tick)
        log.info("Bot démarré sur %s. Ctrl+C pour arrêter proprement.", symbol)
        await done.wait()
    except KeyboardInterrupt:
        pass
    finally:
        await client.disconnect()
        log.info("Bilan de la session — PnL du jour: %.2f", risk.daily_pnl)


async def _place_and_track(client, risk, symbol, direction, stake, on_done):
    try:
        buy = await client.buy_rise_fall(
            symbol=symbol,
            direction=direction,
            stake=stake,
            duration=config.CONTRACT_DURATION,
            duration_unit=config.CONTRACT_DURATION_UNIT,
        )
        contract_id = buy.get("contract_id")
        # Attend la fin du contrat pour connaître le profit réel.
        await asyncio.sleep(0.5)
        poc = {}
        for _ in range(60):  # jusqu'à ~60s d'attente pour un contrat de quelques ticks
            poc = await client.get_contract_result(contract_id)
            if poc.get("is_sold") or poc.get("status") not in (None, "open"):
                break
            await asyncio.sleep(1)
        profit = float(poc.get("profit", 0.0))
        risk.record_result(profit)
        _append_log(
            [datetime.utcnow().isoformat(), symbol, direction, stake, contract_id, profit]
        )
        log.info("Contrat %s clôturé — profit: %+.2f | PnL jour: %+.2f",
                  contract_id, profit, risk.daily_pnl)
    except Exception:
        log.exception("Erreur lors du placement/suivi du trade")
    finally:
        on_done()


def main():
    parser = argparse.ArgumentParser(description="Bot Boom/Crash basé sur un modèle de hazard.")
    parser.add_argument("--symbol", default=config.SYMBOL)
    parser.add_argument("--analyze", action="store_true", help="Analyse + backtest, aucun trade.")
    parser.add_argument("--run", action="store_true", help="Lance la boucle de trading.")
    parser.add_argument("--max-trades", type=int, default=None)
    args = parser.parse_args()

    if not args.analyze and not args.run:
        parser.print_help()
        return

    if args.analyze:
        asyncio.run(analyze(args.symbol))

    if args.run:
        asyncio.run(run_live(args.symbol, args.max_trades))


if __name__ == "__main__":
    main()
