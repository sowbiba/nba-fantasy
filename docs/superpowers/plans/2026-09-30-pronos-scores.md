# Pronos 2026-27 et page Scores TTFL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Une page publique `/pronos-26-27` où les partenaires TTFL de l'utilisateur pronostiquent le bilan V-D des 30 équipes pour 2026-27, avec classement en direct, enregistrement automatique, lecture de tous les pronos, modification réservée à l'auteur (jeton en localStorage), clôture au premier match de la saison et image à partager. (2) Une page publique `/scores-25-26` « Scores TTFL » : moyenne et top score par joueur, filtre par équipe.

**Architecture:** Table `season_pronos` privée (RLS sans politique ; lecture/écriture seulement par le serveur via la clé service) ; server actions publiques mais validées : création (renvoie un jeton aléatoire affiché une seule fois au client, stocké haché côté serveur), mise à jour (exige le jeton, refusée après la clôture). Image de partage via `ImageResponse` (next/og) sur une route `/pronos-26-27/[id]/image`. Scores TTFL : vue SQL publique `player_ttfl_season` agrégée depuis `game_logs` + `games`.

**Tech Stack:** Next.js 16 (Node 22, vitest), Supabase Postgres, `next/og`.

**Spec:** conception validée en conversation le 2026-09-30 (résumée ci-dessous, fait foi).

Conception validée :
- `/pronos-26-27` public, lien partagé au groupe. Accueil : liste des pronostiqueurs (nom, date de mise à jour) + « Faire mon prono » (saisie du nom, 2 à 30 caractères, unique sans tenir compte de la casse et des espaces).
- Saisie : 15 équipes par conférence (Est/Ouest, même répartition que la vue `standings`), victoires 0–82, défaites = 82 − V. Classement en direct par conférence trié par victoires (égalité : ordre alphabétique), zones discrètes 1-6 / 7-10 comme le Classement. Compteur « total des victoires de la ligue » (attendu 1 230) : avertissement, pas de blocage.
- Enregistrement automatique (anti-rebond ~800 ms) avec indicateur « Enregistré ».
- Tout le monde voit tous les pronos (lecture seule pour les autres). Seul l'auteur modifie : à la création, le serveur génère un jeton aléatoire (32 octets), en stocke le SHA-256, renvoie le jeton au navigateur qui le garde en localStorage (`ttfl-prono-<id>`) ; chaque mise à jour envoie le jeton ; comparaison à temps constant ; pas de jeton → lecture seule (message « Ce prono appartient à X »).
- Clôture : au premier match de la saison régulière 2026-27 (heure `tip_off` du premier match `regular` de la saison dans `games` ; à défaut 2026-10-20T23:00Z) ; après, lecture seule pour tous, y compris la création.
- Partager : image PNG (nom + deux classements) ; bouton « Partager » → Web Share API avec fichier (iPhone : WhatsApp, etc.), repli : ouvrir l'image.
- `/scores-25-26` public : **saison 2025-26 uniquement** (pas de sélecteur de saison), type saison régulière / playoffs, filtre équipe, minimum de matchs (défaut 20) ; colonnes joueur, équipe (celle de son dernier match de la période), matchs, moyenne TTFL, top score (date + adversaire) ; tri au toucher sur moyenne et top score ; bouton **« Exporter »** : fichier CSV de la vue filtrée (mêmes filtres et tri), séparateur `;` et encodage UTF-8 avec BOM pour une ouverture directe dans Excel/Numbers en français, nom `scores-ttfl-2025-26-<type>[-<équipe>].csv`, via une route `/scores-25-26/export` (paramètres de filtre validés).
- **Pages autonomes** : `/pronos-26-27` et `/scores-25-26` ne sont reliées nulle part dans l'app (ni barre, ni lien) ; l'utilisateur partage leur URL. Elles gardent l'habillage de l'app mais sans la barre de navigation (mise en page dédiée).

## Global Constraints

- Node 22 (`export PATH=/home/isow/.nvm/versions/node/v22.23.3/bin:$PATH`) ; lire `web/node_modules/next/dist/docs/` (server actions, `image-response.md`) avant de coder ; `cd web && npm test && npx tsc --noEmit && npm run lint && npm run build`.
- SQL : `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -q`.
- Aucune donnée du TTFL de l'utilisateur dans ces pages ; aucune lecture de tables privées avec le client public (test anti-fuite existant à garder vert ; y ajouter `season_pronos`).
- Jamais de jeton en clair côté serveur (hash seulement), jamais dans une URL, jamais journalisé.
- Entrées validées côté serveur (nom, équipes connues, V entiers 0–82) ; taille bornée ; limite simple de créations (ex. 30 pronos au total, message clair au-delà).
- Aucune écriture en prod, aucun db push, déploiement ou push hors de la mise en prod finale (feu vert de l'utilisateur).
- Commits en français terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Modification du prono d'un autre sans jeton (appel direct de la server action) → refusée. Test.
2. Après la clôture : création et modification refusées côté serveur, même si l'interface est restée ouverte. Test.
3. Deux onglets / double saisie rapide : pas de perte (dernière écriture gagne, sans erreur). Test sur l'action.
4. Nom en double à la casse près → refusé avec message clair. Test.
5. Image de partage : noms et équipes échappés, rendu sans police externe (polices locales). Test du rendu (statut 200, type image/png).

---

### Task 1: Migration 032 — table `season_pronos` et vue `player_ttfl_season`
- `season_pronos(id uuid pk default gen_random_uuid(), season text not null, name text not null, name_key text not null, wins jsonb not null default '{}', token_hash text not null, created_at, updated_at, unique(season, name_key))`, RLS sans politique.
- Vue publique `player_ttfl_season(season, game_type, player_id, name, team, games, avg_ttfl, total_ttfl, top_score, top_date, top_opponent)` sur `game_logs` (minutes > 0) × `games` (types regular / playoffs), `security_invoker`, `grant select to anon, authenticated`.
- Tests SQL : anon ne lit pas `season_pronos` ; vue correcte sur données synthétiques (moyenne, top avec date/adversaire, équipe = celle du dernier match, DNP exclus).

### Task 2: Pronos — actions serveur et logique pure
- `web/src/lib/pronos.ts` (pur, testé) : `standingsFromWins(wins, teams)`, `leagueWinsTotal`, `validateWins`, `nameKey`, `isClosed(now, deadline)`.
- `web/src/app/pronos-26-27/actions.ts` : `createProno(name)`, `saveProno(id, token, wins)`, `listPronos()`, `getProno(id)` via la clé service ; jeton aléatoire, SHA-256, comparaison à temps constant ; clôture vérifiée côté serveur.
- Tests vitest des cas de Review Focus 1-4.

### Task 3: Pronos — pages et partage
- `/pronos-26-27` (liste + création), `/pronos-26-27/[id]` (saisie ou lecture, classement en direct, compteur, enregistrement auto, badge « Enregistré »), route image `/pronos-26-27/[id]/image` (`ImageResponse`, polices locales), bouton Partager (Web Share API fichier, repli ouverture).
- Tests : rendu de l'image (200, image/png), helpers de partage.

### Task 4: Page Scores TTFL `/scores-25-26`
- Page publique autonome lisant `player_ttfl_season` pour la saison 2025-26 seulement, filtres (type, équipe, minimum de matchs), tri au toucher (moyenne, top score), aucun lien depuis l'app ; export CSV (route `/scores-25-26/export`, `;`, UTF-8 BOM, filtres validés) ; helpers de tri et de génération CSV testés (échappement des guillemets et `;`).

### Task 5: Mise en prod (feu vert)
- Migration 032 (dry-run : 032 seule), déploiement, vérification (création d'un prono de test puis suppression, lecture seule sans jeton, image), merge, push.
