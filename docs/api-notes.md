# Notes d'investigation sur l'API Skolengo

Journal des requêtes/réponses testées en conditions réelles contre l'API Skolengo
(`https://api.skolengo.com/api/v1/bff-sko-app`), au fil des bugs/quirks découverts.
Sert de référence pour éviter de re-découvrir les mêmes pièges. Basé en partie sur
la bibliothèque de référence [maelgangloff/scolengo-api](https://github.com/maelgangloff/scolengo-api)
(client Node.js non officiel), citée dans les commentaires du code de `api.py`.

## `/homework-assignments` (`get_homework`)

- **Paramètres** : `filter[student.id]`, `filter[dueDate][GE]`, `filter[dueDate][LE]`.
- **Confirmé : les deux bornes `GE` et `LE` sont obligatoires.** Une requête sans l'une des
  deux renvoie `400 BAD_REQUEST` (`"filter[dueDate][GE] is mandatory"` / `"...[LE] is mandatory"`).
  On ne peut donc pas contourner un bug de filtrage en supprimant juste une borne.
- **Bug serveur confirmé** : si un devoir dans la plage filtrée n'a pas de `dueDateTime`
  (valeur `null` côté Skolengo), l'API renvoie `500 INTERNAL_SERVER_ERROR`. Le détail de
  l'erreur est parfois présent (`"Cannot invoke \"java.time.ZonedDateTime.toLocalDate()\"..."`),
  parfois absent (juste `INTERNAL_SERVER_ERROR` sans `detail`) — donc **ne pas** filtrer sur le
  texte du message, matcher sur le code 500 tout court.
- **Contournement retenu (v1.0.10+)** : sur tout 500 de cet endpoint, on rebascule sur
  `/agendas` (qui embarque déjà `homeworkAssignments` par jour via `include`) et on dédoublonne
  par id. Voir `_get_homework_via_agenda()` dans `api.py`.

## `/agendas` (`get_agenda`)

- **Paramètres** : `filter[student.id]`, `filter[date][GE]`, `filter[date][LE]`, `include`.
- `include=lessons,lessons.subject,lessons.teachers,homeworkAssignments,homeworkAssignments.subject`
  fonctionne et n'est pas affecté par le bug `dueDate` ci-dessus (les devoirs y sont rattachés
  au jour, pas filtrés par date d'échéance).

## `/evaluations-settings` (`get_evaluations_settings`)

- **Ne contient PAS de notes/moyennes.** C'est un objet de configuration
  (`periodicReportsEnabled`, `skillsEnabled`, `evaluationsDetailsAvailable`) — piège si on
  s'attend à y trouver directement les moyennes.
- **Les périodes (trimestres/semestres) sont dans la relation `periods`**, qui n'est PAS
  résolue par défaut : sans `include=periods`, seule la liaison `{type, id}` brute revient
  (pas de `label`/`startDate`/`endDate`). Confirmé en lisant `EvaluationSettings.ts` +
  `index.ts` de scolengo-api.
- **Modèle `Period`** : `{ id, label, startDate, endDate }` (dates au format `YYYY-MM-DD`).
- **Fix appliqué (v1.0.12+)** : `get_evaluations_settings()` passe désormais `include=periods`.

## `/evaluation-services` (`get_evaluations`)

- **Paramètres** : `filter[student.id]`, `filter[period.id]` (optionnel — confirmé par la lib de
  référence, correspond à ce que `api.py` faisait déjà).
- Sans `filter[period.id]`, Skolengo renvoie les `evaluationService` de **toutes** les périodes
  mélangées, sans indication de période sur chaque enregistrement (pas de relation `period`
  visible dans nos réponses testées — à confirmer si un jour on a des notes pour vérifier).
- **Stratégie retenue (v1.0.12+)** : un appel par période (`filter[period.id]=<id>` pour chaque
  `Period` renvoyé par `/evaluations-settings`), avec un tag interne `_period_id` posé côté
  client sur chaque `evaluationService` récupéré — pas d'attente d'un champ "period" natif
  dans la réponse.
- Toujours **best-effort** : certains établissements renvoient des erreurs sur cet endpoint
  (`SkolengoApiError` catchée en `debug`, jamais fatale).
- ⚠️ **Non vérifié en conditions réelles avec des notes existantes** : au moment du test
  (2026-09-03), l'année scolaire venait de commencer et aucune note n'était encore disponible
  pour le compte testé. La forme exacte d'un `evaluationService`/`evaluation` réel (present sur
  `subject`, `evaluationResult`, etc.) reste basée sur les commentaires existants du code
  (`sensor.py`) et la lib de référence, pas sur une réponse brute observée. À revérifier dès
  que des notes seront publiées.

## Généralités JSON:API observées

- Sans `include=...` explicite sur une relation, Skolengo ne renvoie que le lien `{type, id}`
  brut, jamais les attributs — vu à la fois sur `homeworkAssignments` (agenda) et `periods`
  (evaluations-settings). Réflexe à avoir : si un champ attendu est `null`/absent alors qu'il
  "devrait" être là, vérifier d'abord l'`include`.
- Les messages d'erreur Skolengo sont **inconsistants** : parfois un `detail` explicite avec la
  stack Java, parfois juste `title` (`INTERNAL_SERVER_ERROR`) sans détail. Ne jamais coder de
  logique de fallback basée sur le contenu précis du message d'erreur — se baser sur le code
  HTTP (ex: tout 500) plutôt que sur une sous-chaîne fragile.
