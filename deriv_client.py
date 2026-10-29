"""
Fine couche au-dessus de la librairie officielle `python_deriv_api`.
Isole tous les appels réseau pour que le reste du code (modèle, bot) n'ait
jamais à connaître le format exact des messages WebSocket.

Librairie officielle : pip install python_deriv_api
Doc : https://deriv-com.github.io/python-deriv-api/
"""

from __future__ import annotations

import logging
from typing import Optional

from deriv_api import DerivAPI

import config

log = logging.getLogger("deriv_client")


class DerivClient:
    def __init__(self, app_id: str = config.APP_ID, token: str = config.API_TOKEN):
        if not token:
            raise RuntimeError(
                "Aucun token API trouvé. Définis la variable d'environnement "
                "DERIV_API_TOKEN (voir README.md) avant de lancer le bot."
            )
        self._app_id = app_id
        self._token = token
        self.api: Optional[DerivAPI] = None
        self.account_info: dict = {}

    async def connect(self) -> None:
        self.api = DerivAPI(endpoint=config.ENDPOINT, app_id=self._app_id)
        auth = await self.api.authorize(self._token)
        self.account_info = auth.get("authorize", {})
        is_virtual = bool(self.account_info.get("is_virtual"))
        log.info(
            "Connecté au compte %s (%s) — solde: %s %s",
            self.account_info.get("loginid"),
            "DEMO / VIRTUEL" if is_virtual else "REEL",
            self.account_info.get("balance"),
            self.account_info.get("currency"),
        )
        if not is_virtual:
            log.warning(
                "!!! CE COMPTE EST UN COMPTE REEL. Assure-toi d'avoir testé "
                "en démo et d'avoir compris les risques avant de continuer. !!!"
            )

    async def disconnect(self) -> None:
        if self.api:
            await self.api.clear()  # ferme proprement la connexion et les souscriptions

    # --- Données de marché --------------------------------------------------

    async def get_tick_history(self, symbol: str, count: int) -> list[float]:
        """Récupère un historique de ticks (prix uniquement, ordre chronologique)."""
        resp = await self.api.ticks_history(
            {
                "ticks_history": symbol,
                "end": "latest",
                "count": count,
                "style": "ticks",
            }
        )
        history = resp.get("history", {})
        prices = history.get("prices", [])
        return [float(p) for p in prices]

    async def subscribe_ticks(self, symbol: str):
        """Retourne un objet Observable (rx) de ticks temps réel."""
        return await self.api.subscribe({"ticks": symbol})

    # --- Trading ------------------------------------------------------------

    async def get_balance(self) -> float:
        bal = await self.api.balance()
        return float(bal.get("balance", {}).get("balance", 0.0))

    async def buy_rise_fall(
        self,
        symbol: str,
        direction: str,
        stake: float,
        duration: int,
        duration_unit: str,
    ) -> dict:
        """
        Achète un contrat Rise/Fall (CALL = à la hausse, PUT = à la baisse).
        Utilise le flux proposal -> buy recommandé par Deriv pour connaître le
        prix exact avant l'achat (le payout n'est jamais garanti à l'avance).
        """
        contract_type = "CALL" if direction.upper() in ("CALL", "RISE", "UP") else "PUT"
        proposal = await self.api.proposal(
            {
                "proposal": 1,
                "amount": stake,
                "basis": "stake",
                "contract_type": contract_type,
                "currency": self.account_info.get("currency", "USD"),
                "duration": duration,
                "duration_unit": duration_unit,
                "symbol": symbol,
            }
        )
        proposal_id = proposal["proposal"]["id"]
        ask_price = proposal["proposal"]["ask_price"]
        buy = await self.api.buy({"buy": proposal_id, "price": ask_price})
        return buy.get("buy", {})

    async def get_contract_result(self, contract_id: int) -> dict:
        """Interroge le statut final d'un contrat (gagné/perdu, profit)."""
        poc = await self.api.proposal_open_contract(
            {"proposal_open_contract": 1, "contract_id": contract_id}
        )
        return poc.get("proposal_open_contract", {})
