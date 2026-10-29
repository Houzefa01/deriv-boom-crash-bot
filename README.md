# Bot Boom/Crash pour Deriv — modèle statistique de hazard

Squelette fonctionnel d'un bot de trading pour les indices synthétiques
Boom/Crash de Deriv, utilisant l'API officielle. Le "modèle" n'est pas une
IA magique : c'est une analyse de survie (fonction de hazard) qui teste
honnêtement, sur données réelles, si le temps écoulé depuis le dernier spike
donne une information exploitable — au lieu de le supposer.

## ⚠️ Avant de commencer — à lire absolument

1. **Boom/Crash sont des indices synthétiques générés par Deriv**, pas de
   vrais marchés. Aucun modèle ne peut "prédire" un générateur aléatoire
   au-delà de ce que sa loi statistique permet.
2. **Ce code est un point de départ, pas un produit fini.** Il n'a pas été
   testé en conditions réelles prolongées. Attends-toi à devoir déboguer,
   ajuster les seuils, et valider chaque hypothèse toi-même.
3. **Commence TOUJOURS sur un compte démo.** Crée un token API lié à un
   compte démo (voir ci-dessous) et ne passe en réel qu'après des semaines
   de test stable.
4. **Aucun win rate n'est garanti.** Le backtest fourni est une
   approximation (voir les commentaires dans `backtest.py`) — un résultat
   positif en backtest ne se traduit pas automatiquement en résultat positif
   en direct.
5. Ceci n'est pas un conseil financier. Le trading sur produits dérivés
   comporte un risque de perte du capital investi, potentiellement rapide
   sur des instruments aussi volatils que Boom/Crash.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

1. Connecte-toi sur https://app.deriv.com
2. Paramètres → API Token → crée un token avec les scopes **Read** + **Trade**
   uniquement (jamais "Withdraw" pour un bot automatisé).
3. Fais-le d'abord pour ton **compte démo**, puis exporte-le :

```bash
export DERIV_API_TOKEN="ton_token_demo_ici"
export DERIV_APP_ID="1089"       # ou ton propre app_id enregistré sur api.deriv.com
export DERIV_SYMBOL="BOOM1000"   # BOOM1000, BOOM500, CRASH1000, CRASH500
```

## Utilisation

### 1. Analyse seule (recommandé en premier) — ne place aucun trade

```bash
python live_bot.py --analyze
```

Ça télécharge l'historique de ticks, construit le modèle de hazard, affiche
un tableau `t | n_obs | hazard | IC 95% | verdict`, et lance un backtest
out-of-sample. **Regarde le verdict** : si aucun bucket n'affiche "ELEVE" ou
"REDUIT" de façon significative, c'est que — pour ce symbole, cette période,
et ce seuil de détection — **aucun edge temporel n'a été détecté**. Dans ce
cas, la conclusion honnête est de ne pas trader ce signal, pas de forcer une
stratégie dessus.

### 2. Trading en boucle (démo d'abord !)

```bash
python live_bot.py --run --max-trades 10
```

Le bot trade uniquement quand le signal du modèle est statistiquement
favorable, avec :
- une mise fixe (jamais de martingale — voir `risk_manager.py`),
- un plafond de perte quotidien (`MAX_DAILY_LOSS`),
- un coupe-circuit après N pertes consécutives (`MAX_CONSECUTIVE_LOSSES`).

Tous les trades sont journalisés dans `trade_log.csv`.

## Structure du projet

| Fichier             | Rôle                                                        |
|----------------------|--------------------------------------------------------------|
| `config.py`          | Tous les paramètres réglables, aucun secret en dur           |
| `deriv_client.py`    | Enveloppe autour de la lib officielle `python_deriv_api`     |
| `hazard_model.py`    | Analyse de survie : détection de spikes + fonction de hazard |
| `backtest.py`        | Backtest out-of-sample (calibration/test séparés)            |
| `risk_manager.py`    | Mise fixe, plafond de perte, coupe-circuit                   |
| `live_bot.py`        | CLI : `--analyze` et `--run`                                 |

## Pistes d'amélioration (à toi de jouer)

- Récupérer le vrai `ask_price` du `proposal` pour un backtest avec payout
  exact plutôt qu'approximé.
- Tester plusieurs valeurs de `SPIKE_THRESHOLD_MAD` et `CONTRACT_DURATION`
  en walk-forward (pas juste un split calibration/test unique).
- Ajouter un modèle ML (ex. gradient boosting) prenant en entrée plusieurs
  features (volatilité récente, t depuis dernier spike, heure, etc.) — mais
  ne remplace jamais la case "significativité statistique" par un modèle
  boîte noire sans le valider en out-of-sample.
- Ajouter des tests unitaires sur `hazard_model.py` (les fonctions statistiques
  sont les plus faciles à casser silencieusement).
