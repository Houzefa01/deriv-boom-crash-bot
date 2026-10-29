Tu es chargé de tester, déboguer et fiabiliser ce bot de trading algorithmique pour les indices synthétiques Boom/Crash de Deriv. Le code utilise un modèle d'analyse de survie (fonction de hazard) pour déterminer s'il existe une structure temporelle exploitable entre les spikes. Réfère-toi à API.md pour le format exact des réponses de l'API Deriv. Voici tes instructions, à suivre strictement et dans l'ordre.

1. TESTS FONCTIONNELS (priorité absolue)
- Fais tourner "python live_bot.py --analyze" sur les 4 symboles disponibles (BOOM1000, BOOM500, CRASH1000, CRASH500).
- Identifie et corrige tous les bugs, exceptions, erreurs de connexion API, incohérences de format de données.
- Écris des tests unitaires pour hazard_model.py (détection de spikes, calcul du hazard, intervalle de Wilson) et risk_manager.py (plafond de perte, coupe-circuit après pertes consécutives).
- Vérifie que le risk_manager bloque bien le trading quand ses limites sont atteintes (teste-le en simulant une série de pertes).

2. VALIDATION STATISTIQUE — méthode obligatoire
Le split calibration/test unique actuel dans backtest.py est un minimum, pas une validation suffisante. Remplace-le ou complète-le par une validation walk-forward :
- Découpe l'historique en N fenêtres successives (ex. calibrer sur les ticks 1–2000, tester sur 2001–3000 ; calibrer sur 1001–3000, tester sur 3001–4000 ; etc.).
- Pour chaque fenêtre de test, calcule : nombre de trades, win rate avec intervalle de confiance à 95%, espérance de gain par trade, drawdown maximum, profit factor.
- Un edge n'est crédible que s'il reste stable et significatif sur plusieurs fenêtres indépendantes, pas sur une seule.
- Fais une analyse de sensibilité : fais varier SPIKE_THRESHOLD_MAD et CONTRACT_DURATION de ±20-30% et vérifie que le résultat ne s'effondre pas au moindre changement de paramètre.

3. RÈGLES ANTI-TRICHE (non négociables)
- N'assouplis JAMAIS risk_manager.py (plafond de perte, coupe-circuit, taille de mise fixe) pour améliorer un résultat de backtest.
- Ne réduis JAMAIS la fenêtre de test après-coup pour ne garder que la période favorable.
- Si un test ne montre aucun edge statistiquement significatif sur un symbole donné, c'est un résultat valide à documenter tel quel — pas un échec à corriger en modifiant les seuils jusqu'à obtenir un chiffre plus flatteur.
- Ne modifie jamais le calcul du win rate, du PnL ou des intervalles de confiance pour "arranger" un résultat — seulement pour corriger un bug réel, avec justification écrite du bug corrigé.

4. CRITÈRES D'ARRÊT
Termine la session quand, et seulement quand, TOUS ces points sont vérifiés :
1. Tous les tests unitaires passent.
2. Le bot tourne de bout en bout sur un compte démo sans exception, sur les 4 symboles.
3. Le rapport de validation walk-forward est généré, avec les intervalles de confiance, pour chaque symbole.
4. Le risk_manager a été testé et bloque bien le trading dans les scénarios de perte simulés.
5. Un rapport final résume, pour chaque symbole : edge détecté ou non, niveau de confiance statistique, sensibilité aux paramètres, et recommandation (trader / ne pas trader / affiner encore).

Il n'y a pas de seuil de rentabilité à atteindre pour arrêter la session. Si après une validation rigoureuse un symbole ne montre aucun edge exploitable, documente-le clairement — c'est une information utile, pas un échec de la mission.

5. LIVRABLE ATTENDU
- Le code corrigé, avec les tests unitaires.
- Un rapport (RAPPORT_VALIDATION.md) listant : bugs corrigés, résultats walk-forward par symbole avec IC 95%, analyse de sensibilité, et recommandation finale honnête (y compris si la recommandation est "aucun edge fiable trouvé, ne pas déployer en réel").
