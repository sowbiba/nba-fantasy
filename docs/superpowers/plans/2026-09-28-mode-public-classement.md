# Mode public par défaut, mode connecté et classement NBA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** L'app s'ouvre en mode public (données NBA seulement : matchs du soir, matchs et box scores, classement, blessés, fiche joueur sans rien de lié au TTFL de l'utilisateur) ; un bouton « Mode connecté » envoie un code à `OWNER_EMAIL` et ouvre l'app complète ; les données TTFL de l'utilisateur ne sont plus lisibles publiquement, ni par l'interface ni en interrogeant la base ; un onglet Classement (Est/Ouest) s'ajoute à Matchs.

**Architecture:** La session Supabase décide du mode : `getViewer()` (serveur) renvoie `{ owner: boolean }`. En mode connecté, les pages lisent les données privées avec le client service **après** vérification de la session (`ownerDb()`), jamais avec la clé publique. Une migration retire la lecture publique des tables et fonctions TTFL ; elle part **après** le déploiement du nouveau front. Le classement est une vue SQL publique calculée depuis `games`.

**Tech Stack:** Next.js 16 (App Router, Node 22, vitest), Supabase Postgres (RLS, vues), @supabase/ssr.

**Spec:** conception validée en conversation le 2026-09-28 (résumée ci-dessous, fait foi) ; auth existante : `docs/superpowers/specs/2026-09-26-moteur-sr-po-design.md` §6 (OTP e-mail, propriétaire unique) ; règles `docs/regles-ttfl.md`.

Conception validée :
- Mode déconnecté par défaut. Ce soir = matchs de la soirée seulement (heures), sans classement ni suggestion. Deck et Picks cachés (absents de la barre ; accès direct → redirection vers `/`). Matchs = liste semaine par semaine + box score en direct, rien lié aux picks, + onglet Classement. Blessés disponible. Fiche joueur : 5 derniers, saison, floor · ceiling, prochains matchs (date, adversaire) ; pas d'étoiles, pas de badge de classement/tier, pas d'analyse (pour/contre/verdict), pas de disponibilité ni de bouton de pick.
- Bouton « Mode connecté » : un clic envoie un code à `OWNER_EMAIL` (aucun champ e-mail) ; champ du code ; une fois connecté, l'app complète (écrans actuels) + Classement. Bouton « Déconnexion » pour revenir au public.
- Confidentialité réelle (option A) : plus de lecture anon de picks, second_chances, recommendations, plan (et `plan_latest`), player_watchlist, weekly_plan, series_forecast ; `period_stats` et `player_calendar` non exécutables par anon. Restent publics : games, game_logs, players, injuries (colonnes de `players`), nights, series, matchups, sync_log, standings.
- Classement Est/Ouest : V-D, %, GB, domicile, extérieur, 10 derniers, série ; saison régulière (poules et phases finales de la NBA Cup comprises, finale `cup_final` exclue) ; tri au pourcentage (pas les règles officielles de départage). Délimitation visuelle **discrète** (pas de vert/orange) : léger dégradé ou teinte de fond sur les places 1-6 (playoffs) et 7-10 (play-in), et un séparateur fin après la 6e et la 10e place.

## Global Constraints

- Front : Node 22 (`export PATH=/home/isow/.nvm/versions/node/v22.23.3/bin:$PATH`), lire `web/node_modules/next/dist/docs/` avant d'écrire du code Next (Next 16, `web/AGENTS.md`). Vérifier : `cd web && npm test && npx tsc --noEmit && npm run lint && npm run build`.
- SQL : `TEST_DATABASE_URL=postgresql://postgres:pg@localhost:55432/postgres ./venv/bin/python -m pytest tests/sql -q` (Postgres jetable local, rôles Supabase créés par le conftest).
- **Jamais** la clé service dans du code client ; toute lecture de donnée privée passe par `ownerDb()` qui appelle `requireOwner()` d'abord ; toute écriture reste une action serveur protégée (existant).
- Aucune écriture en prod, aucun `db push`, aucun déploiement, aucun push git hors de la tâche 6 (feu vert de l'utilisateur). `web/.env.local` pointe la prod : ne pas lancer `npm run dev`.
- Textes en français, tutoiement. Commits en français terminés par `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Fuite de données privées en mode public** : aucune page publique ne doit requêter `picks`, `recommendations`, `plan_latest`, `player_watchlist`, `second_chances`, `period_stats`, `player_calendar` (même si la requête échouerait après la migration) — test par `grep` + tests des helpers. Tâches 3-5.
2. **Ordre de déploiement** : le nouveau front doit marcher **avant et après** la migration 028 (le connecté lit via `ownerDb()`, le public ne lit rien de privé) ; l'ancien front casserait après 028 → 028 part en dernier. Tâche 6.
3. **Session expirée ou cookies absents (PWA iPhone)** : `getViewer()` renvoie `owner: false` sans erreur ; aucune page ne plante ; Deck/Picks/Rappels redirigent. Tâche 3.
4. **Envoi du code par un inconnu** : n'importe qui peut cliquer « Mode connecté » ; le code part seulement à `OWNER_EMAIL`, le formulaire n'accepte aucune adresse, et la réponse ne révèle pas l'adresse. Tâche 3.
5. **Classement avant le premier match** : 30 équipes à 0-0, pas de division par zéro, ordre stable (alphabétique à égalité). Tâche 1.

---

### Task 1: Vue `standings` (migration 027)

**Files:** Create `supabase/migrations/027_standings.sql`, `tests/sql/test_027_standings.py`

**Interfaces:** Produces la vue publique `standings(season text, conference text, team text, wins int, losses int, pct numeric, games_behind numeric, home_wins int, home_losses int, away_wins int, away_losses int, last10_wins int, last10_losses int, streak text, rank int)`, `security_invoker = true`, lecture anon accordée (hérite de `games`).

- [ ] **Step 1: Tests** — saison fictive (`season = '2026-27'`) : 3 matchs `regular` `final` avec scores, 1 match `cup_final` final (exclu), 1 match `preseason` final (exclu), 1 match `regular` `scheduled` (ignoré). Attendus : les 30 équipes présentes (15 Est, 15 Ouest), V-D et domicile/extérieur corrects, `pct` = V/(V+D) arrondi à 3 décimales (0 si aucun match), `games_behind` = ((V1−V) + (D−D1))/2 par conférence, `last10_*` sur les 10 derniers matchs de l'équipe, `streak` du type `'V3'`/`'D1'` (vide si aucun match), `rank` 1-15 par conférence trié par `pct` desc puis `wins` desc puis `team` asc. Saison affichée = la plus récente présente dans `games` avec `game_type = 'regular'`.
- [ ] **Step 2: Échec**, **Step 3: Migration** — conférences en `values` dans la vue (Est : ATL BOS BKN CHA CHI CLE DET IND MIA MIL NYK ORL PHI TOR WAS ; Ouest : DAL DEN GSW HOU LAC LAL MEM MIN NOP OKC PHX POR SAC SAS UTA) ; résultats par équipe via `cross join lateral (values (home_team, true), (away_team, false))` ; fenêtres pour les 10 derniers et la série ; `grant select on standings to anon, authenticated`.
- [ ] **Step 4: Suite SQL → PASS**. **Step 5: Commit** `feat(db): classement NBA Est/Ouest calculé depuis les matchs (027)`.

---

### Task 2: Migration 028 — fin de la lecture publique des données TTFL

**Files:** Create `supabase/migrations/028_private_ttfl_data.sql`, `tests/sql/test_028_private.py`

- [ ] **Step 1: Tests** — en tant que rôle `anon` (`set local role anon`) : `select` sur picks, second_chances, recommendations, plan, plan_latest, player_watchlist, weekly_plan, series_forecast renvoie 0 ligne ou une erreur de permission ; `period_stats(...)` et `player_calendar(...)` refusés (`has_function_privilege('anon', ..., 'execute') = false`) ; `games`, `players`, `nights`, `standings` restent lisibles par anon ; `service_role` lit tout.
- [ ] **Step 2: Échec**, **Step 3: Migration** — `drop policy if exists` des politiques « anon read » de ces tables (noms exacts dans `supabase/schema.sql` et migrations 002, 005, 018, 019 ; vérifier aussi series_forecast/weekly_plan) ; `revoke execute on function period_stats(text, text, date), player_calendar(int, date, date) from public, anon, authenticated` puis `grant execute ... to service_role`. En-tête : « À appliquer APRÈS le déploiement du front qui lit ces données via le serveur. »
- [ ] **Step 4: PASS**. **Step 5: Commit** `feat(db): données TTFL privées, plus de lecture publique (028)`.

---

### Task 3: Session, mode et connexion par code sans e-mail

**Files:** Create `web/src/lib/viewer.ts`, `web/src/lib/viewer.test.ts` ; Modify `web/src/app/connexion/actions.ts`, `web/src/app/connexion/LoginForm.tsx`, `web/src/app/connexion/page.tsx`, `web/src/app/layout.tsx`, `web/src/components/BottomNav.tsx`, `web/src/app/actions.ts` (signOut inchangé, réutilisé)

**Interfaces:**
- `getViewer(): Promise<{ owner: boolean }>` (server-only ; `false` sur toute erreur de session) et `ownerDb(): Promise<AdminClient | null>` (server-only ; `null` si pas propriétaire, sinon `adminClient()`), dans `web/src/lib/viewer.ts`.
- `sendOwnerCode(): Promise<{ ok: boolean; error?: string }>` : `signInWithOtp({ email: OWNER_EMAIL, options: { shouldCreateUser: false } })` ; message générique d'erreur ; ne renvoie jamais l'adresse. `verifyOwnerCode(code: string)` : `verifyOtp` avec `OWNER_EMAIL` et le code (chiffres seulement).
- `BottomNav({ owner })` : public → Ce soir · Matchs · Blessés ; connecté → Ce soir · Deck · Matchs · Picks · Blessés. En-tête (layout) : bouton « Mode connecté » (public) ou « Déconnexion » (connecté), discret.

- [ ] **Step 1: Tests** (vitest, dépendances injectées) : `getViewer` → false si `getUser` lève ou renvoie un autre e-mail, true pour `OWNER_EMAIL` (casse/espaces ignorés) ; `ownerDb` → null si non propriétaire.
- [ ] **Step 2: Implémenter** ; `/connexion` : bouton « Recevoir un code » puis champ du code, plus de champ e-mail ; après succès → `/` + `router.refresh()`. Lire le guide Next 16 sur `cookies()`/Server Functions.
- [ ] **Step 3: Vérifier** (commande front) ; **Commit** `feat(web): mode public par défaut et connexion propriétaire en un clic`.

---

### Task 4: Pages connectées via le serveur, pages privées protégées

**Files:** Modify `web/src/app/page.tsx`, `web/src/app/deck/page.tsx`, `web/src/app/picks/page.tsx`, `web/src/app/player/[id]/page.tsx`, `web/src/app/rappels/page.tsx`, et tout fichier qui lit `picks`, `recommendations`, `plan_latest`, `player_watchlist`, `second_chances`, `period_stats`, `player_calendar` avec le client public (`grep -rn` dans `web/src`).

- [ ] **Step 1:** Deck, Picks, Rappels : `const viewer = await getViewer(); if (!viewer.owner) redirect("/")` en tête (lire la doc Next 16 de `redirect`).
- [ ] **Step 2:** Toutes les lectures de données privées passent par `ownerDb()` (serveur, après vérification) au lieu du client public ; les données publiques (games, players, nights, game_logs, matchup_season) restent sur le client public.
- [ ] **Step 3: Test anti-fuite** (vitest ou script de test) : aucun fichier de `web/src` hors `lib/viewer.ts`, `app/actions.ts`, `app/api/reminders` n'appelle `.from("picks" | "recommendations" | "plan_latest" | "player_watchlist" | "second_chances")` ou `.rpc("period_stats" | "player_calendar")` avec le client public `supabase` (test qui lit les fichiers et cherche le motif `supabase.from("picks"` etc.).
- [ ] **Step 4: Vérifier** ; **Commit** `feat(web): données TTFL lues côté serveur après vérification de la session`.

---

### Task 5: Vues publiques et classement

**Files:** Modify `web/src/app/page.tsx`, `web/src/app/player/[id]/page.tsx`, `web/src/app/games/page.tsx` ; Create `web/src/app/games/classement/page.tsx` (ou onglet par paramètre — suivre la doc Next 16), `web/src/components/GamesTabs.tsx`, `web/src/components/StandingsTable.tsx`, helpers + tests dans `web/src/lib/display.ts`/`display.test.ts`.

- [ ] **Step 1: Ce soir public** : si `!owner`, la page n'affiche que les matchs de la soirée du deck (heure de Paris, équipes, statut/score si commencé), sans recos, pick, x2, bannière de pick.
- [ ] **Step 2: Fiche joueur publique** : si `!owner`, afficher en-tête (nom, équipe, poste, blessure si présente), 5 derniers, saison, floor · ceiling, et « Prochains matchs » (30 jours) lus depuis `games` (date, domicile/extérieur, adversaire) — pas de `player_calendar`, pas d'étoiles, pas de tier, pas de pour/contre/verdict, pas de boutons. Connecté : inchangé.
- [ ] **Step 3: Onglets Matchs · Classement** en haut de Matchs (les deux modes). `StandingsTable` : deux tableaux (Est, Ouest) lus depuis la vue `standings` ; colonnes Rang, Équipe, V, D, %, GB, Dom., Ext., 10 der., Série ; mobile d'abord (colonnes secondaires masquables ou tableau défilant horizontalement dans son conteneur) ; délimitation discrète : fond très légèrement teinté dégressif sur 1-6, plus léger sur 7-10, séparateur fin après la 6e et la 10e place, petite légende « 1-6 playoffs · 7-10 play-in ». Helper testé : `standingsZone(rank): "playoffs" | "playin" | null`.
- [ ] **Step 4: Vérifier** ; **Commit** `feat(web): Ce soir et fiche joueur publics, onglet Classement`.

---

### Task 6: Mise en prod (feu vert de l'utilisateur à chaque étape)

- [ ] **Step 1:** Mettre de côté `028_private_ttfl_data.sql` ; `supabase db push --linked --dry-run` ne doit lister que 027 ; push.
- [ ] **Step 2:** Déployer le front (`cd web && vercel --prod --yes`) ; vérifier en navigation privée (public) : Ce soir sans recos, barre à 3 onglets, `/deck` et `/picks` redirigent, fiche joueur sans étoiles, Classement affiché ; l'utilisateur se connecte sur l'iPhone et vérifie l'app complète.
- [ ] **Step 3:** Remettre 028, dry-run (028 seule), push ; vérifier en lecture avec la clé anon : `picks`/`recommendations`/`plan_latest` renvoient 0 ligne ou 401/permission, `standings` et `games` répondent ; l'app connectée fonctionne toujours.
- [ ] **Step 4:** Merge dans `main`, push, mémoire à jour.
