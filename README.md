# Skolengo pour Home Assistant

Intégration **communautaire et non officielle** pour [Skolengo](https://www.skolengo.com/), permettant de récupérer dans Home Assistant l'emploi du temps, les devoirs, les absences et (dans la mesure du possible) les notes d'un élève.

> **Avertissement** : ce projet n'est ni développé, ni maintenu, ni approuvé par Skolengo ou Index Education. Il s'appuie sur une analyse non officielle de l'API utilisée par l'application mobile Skolengo, qui peut changer ou être bloquée à tout moment sans préavis. Utilisez-le à vos risques et périls, avec vos propres identifiants.

Ce projet s'inspire fonctionnellement de l'excellente intégration [hass-pronote](https://github.com/delphiki/hass-pronote), qui fait la même chose pour Pronote.

## Fonctionnalités

- **Calendrier `calendar.emploi_du_temps`** : l'emploi du temps de l'élève (cours, salle, professeur(s), cours annulés), directement exploitable dans les vues Calendrier de Home Assistant ou dans vos automatisations.
- **Calendrier `calendar.devoirs`** : les devoirs à venir, avec leur date de rendu, sous forme d'événements toute la journée.
- **Capteurs** :
  - Prochain cours
  - Nombre de cours aujourd'hui
  - Nombre de devoirs à faire
  - Nombre d'absences enregistrées
  - Moyenne générale (meilleur effort, voir limitations ci-dessous)
- Rafraîchissement automatique périodique (30 minutes par défaut, réglable dans les options de l'intégration).
- Gestion des comptes "représentant légal" (parent) reliés à plusieurs enfants : un élève par intégration, ajoutez l'intégration plusieurs fois pour suivre plusieurs enfants.

## Installation

### Via HACS (recommandé)

1. Dans HACS, ouvrez le menu **⋮ → Dépôts personnalisés (Custom repositories)**.
2. Ajoutez l'URL de ce dépôt (`https://github.com/infernalK/ha-skolengo`) avec la catégorie **Intégration**.
3. Recherchez "Skolengo" dans HACS et installez-le.
4. Redémarrez Home Assistant.

### Installation manuelle

1. Copiez le dossier `custom_components/skolengo` de ce dépôt dans le dossier `custom_components` de votre configuration Home Assistant.
2. Redémarrez Home Assistant.

## Configuration

1. Allez dans **Paramètres → Appareils et services → Ajouter une intégration**.
2. Recherchez **Skolengo**.
3. Renseignez le nom ou la ville de votre établissement, puis sélectionnez-le dans la liste (si plusieurs résultats).
4. Entrez vos identifiants de connexion Skolengo (les mêmes que pour l'application mobile ou le site web de votre établissement).
5. Si votre compte est relié à plusieurs enfants, choisissez celui à suivre.

Le mot de passe n'est utilisé qu'au moment de la connexion initiale : seul un jeton de rafraîchissement (`refresh_token`) est conservé par la suite pour renouveler automatiquement l'accès.

### Options

Depuis la page de l'intégration, le bouton **Configurer** permet d'ajuster l'intervalle de rafraîchissement des données (30 minutes par défaut).

## Limitations connues

- **Connexion** : Skolengo ne propose pas de mécanisme de connexion générique documenté. L'authentification implémentée ici "scrape" (analyse) génériquement la page de connexion CAS/SSO de votre établissement (recherche des champs identifiant/mot de passe usuels). Cette approche fonctionne pour de nombreux établissements, mais certains ENT régionaux utilisent des parcours de connexion multi-étapes ou non standards qui ne seront pas reconnus automatiquement. Si la connexion échoue avec une erreur "Identifiants incorrects ou formulaire de connexion non pris en charge", merci d'ouvrir une [issue GitHub](https://github.com/infernalK/ha-skolengo/issues) en décrivant votre établissement (sans jamais partager vos identifiants ni mot de passe).
- **Notes et absences** : les endpoints évaluations/notes et absences sont connus pour être instables ou indisponibles selon les établissements dans l'API Skolengo elle-même (pas seulement dans cette intégration) — par exemple une erreur serveur 500 sur `/absence-files` a déjà été observée sur un établissement, indépendante de cette intégration. Les capteurs correspondants peuvent donc rester à `inconnu` pour votre établissement — ce n'est pas nécessairement un bug de l'intégration.
- Cette intégration ne propose pas d'envoi de notifications, de liste de tâches (todo), ni de carte Lovelace dédiée : elle se concentre sur l'exposition des données via calendriers et capteurs, que vous pouvez ensuite combiner librement avec les automatisations et cartes standard de Home Assistant.

## Signaler un problème

Ouvrez une [issue sur GitHub](https://github.com/infernalK/ha-skolengo/issues) en précisant :

- la version de Home Assistant et de l'intégration,
- le journal d'erreur pertinent (`Paramètres → Système → Journaux`), en masquant toute information personnelle,
- **ne partagez jamais** votre identifiant, mot de passe, jeton d'accès ou de rafraîchissement dans une issue publique.

## Licence

[MIT](LICENSE)
