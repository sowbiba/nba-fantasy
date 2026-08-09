# TTFL Advisor

Outil d'aide à la décision pour la **TrashTalk Fantasy League** (TTFL). Chaque soir, l'app recommande les meilleurs picks parmi les joueurs NBA disponibles, avec un argumentaire détaillé. En playoffs, un moteur stratégique protège tes franchise-players pour les tours suivants.

App live : **https://web-sigma-one-74.vercel.app** (PWA installable sur mobile)

<!-- TODO: capture d'écran de l'accueil "CE SOIR" ici (à faire une fois le projet Supabase réactivé, écran vide sinon) -->

<img height="500" alt="Ce soir" src="https://github.com/user-attachments/assets/1500acce-5296-4bb7-9162-eaecc37fac1b" />

<img height="500" alt="WhatsApp Image 2026-04-23 at 13 18 00" src="https://github.com/user-attachments/assets/09e6be8c-6ce7-4489-8dfd-f9facf0ee17e" />

<img height="500" alt="WhatsApp Image 2026-04-29 at 18 16 24" src="https://github.com/user-attachments/assets/3225993b-a2fe-4403-9e10-bd1c15bce415" />

<img height="500" alt="WhatsApp Image 2026-04-25 at 15 42 04 (2)" src="https://github.com/user-attachments/assets/32152e62-7015-4755-a04b-3802db726f10" />

<img height="500" alt="WhatsApp Image 2026-05-06 at 20 46 11" src="https://github.com/user-attachments/assets/4d049389-2276-4baf-b402-b25c303a320c" />

<img height="500" alt="Capture d’écran du 2026-08-09 19-44-03" src="https://github.com/user-attachments/assets/d9869d40-b0ab-4ea0-b737-eb228cbc0255" />


## Ce que ça fait

- **Scoring 6 facteurs** : forme pondérée L5/L10/L20, matchup défensif par poste, split home/away, fatigue (back-to-backs), tendance, régularité floor/ceiling
- **Burn or save** : en playoffs, compare le score de ce soir au meilleur score estimé sur 7 jours pour décider de brûler ou garder un joueur
- **Plan hebdomadaire optimal** : affectation joueurs → jours via l'algorithme hongrois, avec pénalité de réservation des elites pour les tours avancés
- **Blessures en temps réel** : statuts ESPN (Out / Doubtful / Questionable / GTD) intégrés au scoring, détection des usage boosts quand un coéquipier majeur est OUT
- **Règles TTFL natives** : cooldown 30 jours en saison régulière, unicité des picks en playoffs

## Architecture

```
Sources de données                    Stockage                    Frontend
─────────────────                    ─────────                   ────────
cdn.nba.com (box scores, schedule)
nba_api (stats avancées, splits)   →  Python cron  →  Supabase  →  Next.js PWA
ESPN (blessures, statuts)             (machine locale)  (cloud)      (Vercel)
```

Un script Python tourne en cron 4x/jour, pousse stats et recommandations dans Supabase (PostgreSQL), et la PWA Next.js sur Vercel les affiche.

## Lancer en local

```bash
# Backend Python
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # puis renseigner les clés Supabase

# Sync manuel
python -m sync.main

# Frontend
cd web && npm install && npm run dev
```

## Documentation

- [Le moteur en détail](docs/moteur.md) — les 6 facteurs, ajustements blessures, couche stratégie playoffs, plan hebdo (algo hongrois), tuning des paramètres
- [Exploitation](docs/operations.md) — sources de données, rythme de synchro (cron), structure du code, commandes
- [Guide utilisateur](docs/guide-utilisateur.md) — les écrans de l'app, workflow hebdo recommandé

## Licence

Projet personnel — MIT
