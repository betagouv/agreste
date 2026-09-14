# Agreste

Forké depuis Sites Conformes (voir ci dessous)

Releases are tagged commits in `production-agreste` branch, with a release
created on github.

In code, whe agreste version is in agreste_version.txt, while pyproject.toml
still has SC's version (for now).
Version format : the first three numbers are the Agreste version, the second
three are the Sites Conformes version (`${agreste_version}-{SC_version}`).
Example : 2.8.0-4.1.0

## To upgrade Sites Conformes

- Start the merge from `main-agreste`:

  ```sh
  just merge-sc-tag 4.2.0-rc1
  ```

  This will attempt to merge the given tag from SC into main-agreste, and
  resolve known conflicts (uv.lock and deleted code : demo/, tarteaucitron lib,
  package.json, uv.lock) and makemigrations.

- Review remaining changes (especially any new migrations), commit, push

- `gh pr create` to open a PR. Pass the CI and merge.

## To create a release

- Update the version number in `agreste_version.txt` :

  ```sh
  VERSION="2.8.0-4.1.0"; # ${agreste_version}-{SC_version}
  git checkout main-agreste; git pull; 
  echo $VERSION > agreste_version.txt; 
  git add agreste_version.txt; 
  git commit -m "Bump version to $VERSION"; 
  git push
  ```

- Open a PR to merge `main-agreste` into `production-agreste`
  <!-- markdownlint-disable-next-line MD013 -->
  - `gh pr create --base production-agreste --head main-agreste --title "v$VERSION" --body ""`
    The name is the version number ("v2.8.0-4.1.0") and will be picked up
    automatically to name the version and tag.
  - Solve any conflicts and merge. This will trigger a github action that will
  create the release and tag. If the auto-deploy is configured on Scalingo, it
  will deploy the release.

-----

## Sites Conformes

**Sites Conformes** (anciennement « Sites Faciles ») vise à permettre la
création simplifiée de **sites dont le domaine se termine par .gouv.fr**.

Basé sur **[Wagtail](https://wagtail.org/)**, il permet de **concevoir
rapidement des sites internet conformes aux normes numériques en vigueur**.

En particulier, il permet de **construire des pages à l’aide de composants**
prêts à l’emploi issus du **[Système de design de l’État (DSFR)](https://www.systeme-de-design.gouv.fr/)**.

## Prérequis

Sites Conformes vise à utiliser les dernières versions disponibles de
[Django (6.0+)](https://www.djangoproject.com/download/) et [Wagtail](https://docs.wagtail.org/en/stable/releases/upgrading.html).

Les tests automatisés couvrent les versions suivantes :

- Python 3.10 à 3.14 (cf. [versions de Python supportées par Django](https://docs.djangoproject.com/en/5.2/faq/install/))
- PostgreSQL 14 à 17 (cf. [versions de PostgreSQL supportées par Django](https://code.djangoproject.com/wiki/SupportedDatabaseVersions))

## Déploiement

- Pour déployer le projet en production sur un serveur, voir la [documentation d’installation](https://numerique-gouv.github.io/sites-conformes/deploiement/index.html)
- Pour installer le projet en local pour le développement, voir
[installer le projet en local](https://numerique-gouv.github.io/sites-conformes/contrib/installation-locale.html)
- Avant de soumettre une contribution, consulter le [guide de contribution](https://numerique-gouv.github.io/sites-conformes/contrib/guide-contribution.md)
- Pour déployer une instance (Scalingo, serveur Linux, Docker…), voir la
[documentation de déploiement](https://numerique-gouv.github.io/sites-conformes/deploiement/index.md)
- Pour les sauvegardes et le stockage des médias, voir la [gestion des données](https://numerique-gouv.github.io/sites-conformes/donnees/index.md)

## Architecture

[![Made with Django](https://img.shields.io/badge/Made%20with-Django-0C4B33.svg)](https://www.djangoproject.com/)
[![Made with Wagtail](https://img.shields.io/badge/Made%20with-Wagtail-0F7676.svg)](https://wagtail.io/)

Sites Conformes est développé en utilisant le framework
[Django](https://www.djangoproject.com/) et le CMS [Wagtail](https://wagtail.org/).
Il est centré autour d’une application principale nommée
**sites_conformes.core**, accompagnée d’applications annexes pour divers types
de pages.

Le détail des applications Django, de la structure du dépôt et le schéma
d’ensemble sont décrits dans la [documentation d’architecture](./docs/contrib/architecture.md).

## Notifications

Le panneau d’information de l’administration peut afficher des notifications
(nouveautés, alertes, maintenances) aux utilisateurs qui ont accès au back-office.
Ces notifications sont pilotées par le fichier
[`notifications.json`](notifications.json) à la racine du dépôt.

Pour savoir comment ajouter, modifier ou désactiver une notification, voir la
documentation dédiée : [`NOTIFICATIONS.md`](./docs/notifications.md).

## Droit d’utilisation du DSFR

Ce projet utilise le DSFR et est donc tenu par les conditions d’utilisations
suivantes :

### ⚠️ Utilisation interdite en dehors des sites Internet de l’État

>Il est formellement interdit à tout autre acteur d’utiliser le
Système de Design de l’État (les administrations territoriales ou tout autre
acteur privé) pour des sites web ou des applications. Le Système de Design de
l’État représente l’identité numérique de l’État. En cas d’usage à des fins
trompeuses ou frauduleuses, l’État se réserve le droit d’entreprendre les
actions nécessaires pour y mettre un terme.

Voir les [conditions générales d’utilisation](https://github.com/GouvernementFR/dsfr/blob/main/doc/legal/cgu.md).

#### ⚠️ Prohibited Use Outside Government Websites

>This Design System is only meant to be used by official French public services'
websites and apps. Its main purpose is to make it easy to identify governmental
websites for citizens. See terms.
