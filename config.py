"""
Configuration centrale du bot.
------------------------------
NE JAMAIS committer un vrai token API dans ce fichier. Utilise des variables
d'environnement (voir README.md).

Pour obtenir un token :
  1. Connecte-toi sur https://app.deriv.com
  2. Va dans Paramètres -> API Token
  3. Crée un token avec les scopes "Read" + "Trade" (jamais "Withdraw" pour un bot)
  4. Crée un token séparé pour ton compte DÉMO et un pour ton compte RÉEL
"""

import os

# --- Connexion API ---------------------------------------------------------
APP_ID = os.environ.get("DERIV_APP_ID", "1089")  # 1089 = app_id générique de test Deriv
API_TOKEN = os.environ.get("DERIV_API_TOKEN", "")  # NE PAS écrire le token en dur ici
ENDPOINT = "wss://ws.derivws.com/websockets/v3"

# --- Marché ------------------------------------------------------------
# Symboles valides côté Deriv : BOOM1000, BOOM500, CRASH1000, CRASH500
SYMBOL = os.environ.get("DERIV_SYMBOL", "BOOM1000")

# --- Détection des spikes (pour le modèle de hazard) -----------------------
# Un "spike" est détecté quand |retour du tick| dépasse SPIKE_THRESHOLD_MAD fois
# la déviation absolue médiane (MAD) des retours "normaux". C'est une détection
# statistique, pas une valeur magique — à recalibrer par symbole si besoin.
SPIKE_THRESHOLD_MAD = 8.0

# --- Modèle de hazard (survie) ---------------------------------------------
MIN_BUCKET_SAMPLES = 30          # nombre mini d'observations pour qu'un bucket soit fiable
CONFIDENCE_Z = 1.96              # ~95% (loi normale) pour l'intervalle de Wilson

# --- Gestion du risque -------------------------------------------------
STAKE = float(os.environ.get("DERIV_STAKE", "1"))       # mise par trade, en devise du compte
MAX_DAILY_LOSS = float(os.environ.get("DERIV_MAX_DAILY_LOSS", "20"))
MAX_CONSECUTIVE_LOSSES = int(os.environ.get("DERIV_MAX_CONSEC_LOSSES", "4"))
CONTRACT_DURATION = 5             # nombre de ticks du contrat Rise/Fall
CONTRACT_DURATION_UNIT = "t"      # "t" = ticks

# --- Historique pour le backtest / calibration du modèle -------------------
HISTORY_COUNT = 5000              # nombre de ticks à récupérer pour calibrer le modèle

# --- Sécurité ------------------------------------------------------------
# Le bot refuse de trader en réel tant que ce flag n'est pas explicitement
# mis à True par l'utilisateur en ligne de commande (--live). Par défaut : démo.
CONFIRM_LIVE_TRADING = False
