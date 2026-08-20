# Ajout d'un module sécurisé de définition et réinitialisation du mot de passe

Je souhaite ajouter à l'application un module permettant de gérer de manière sécurisée la définition et la réinitialisation du mot de passe.

## Contexte

L'application possède :

* un frontend en React ;
* un backend en Django / Django REST Framework ;
* une authentification existante qu'il faut réutiliser autant que possible.

Avant toute modification, **analyse l'architecture existante du projet** : modèle User, système d'authentification, API, routing React, système d'envoi d'emails, gestion des tâches asynchrones éventuelle, configuration et tests.

Ne recrée pas un système d'authentification si un mécanisme existe déjà.

---

## Fonctionnalités attendues

Le module doit couvrir deux cas d'utilisation avec le même mécanisme technique :

### 1. Création d'un nouveau compte

Lorsqu'un utilisateur est créé :

1. créer son compte ;
2. ne pas lui attribuer de mot de passe utilisable tant qu'il ne l'a pas défini ;
3. générer un token sécurisé et aléatoire ;
4. créer un lien de définition du mot de passe ;
5. envoyer ce lien par email à l'utilisateur.

Exemple :

`https://<frontend>/set-password?token=<TOKEN>`

L'utilisateur clique sur le lien et arrive sur une page React lui permettant de définir son mot de passe.

### 2. Mot de passe oublié

Lorsqu'un utilisateur demande la réinitialisation de son mot de passe :

1. il saisit son adresse email ;
2. Django génère un nouveau token ;
3. Django envoie un email contenant un lien de réinitialisation ;
4. l'utilisateur arrive sur la même page React de définition du mot de passe ;
5. il saisit son nouveau mot de passe ;
6. Django vérifie le token et modifie le mot de passe.

Le mécanisme de token doit donc être **réutilisable** pour les deux workflows.

---

# Architecture souhaitée

Créer un mécanisme générique de token d'action utilisateur.

Par exemple, un modèle équivalent à :

```python
UserActionToken
```

avec au minimum :

* utilisateur concerné ;
* type/action du token ;
* hash du token ;
* date de création ;
* date d'expiration ;
* date d'utilisation éventuelle.

Le modèle doit permettre d'étendre ultérieurement le système à d'autres actions comme :

* vérification d'adresse email ;
* invitation utilisateur ;
* changement d'adresse email ;
* etc.

Le token ne doit **jamais être stocké en clair en base de données**.

Utiliser un générateur cryptographiquement sûr, par exemple Python `secrets`.

Exemple conceptuel :

```python
raw_token = secrets.token_urlsafe(48)
```

Stocker uniquement un hash du token en base.

Le token en clair doit uniquement être transmis à l'utilisateur via le lien envoyé par email.

---

# Sécurité des tokens

Un token doit :

* être suffisamment long et imprévisible ;
* être à usage unique ;
* avoir une durée d'expiration ;
* être associé à une action précise ;
* être associé à un utilisateur précis ;
* être invalidé après utilisation ;
* ne pas être réutilisable ;
* ne pas être stocké en clair en base.

Pour un reset de mot de passe, utiliser par défaut une durée de validité d'environ **1 heure**, sauf si l'architecture existante impose une autre valeur.

Lorsqu'un nouvel email de reset est demandé, invalider les anciens tokens de reset encore valides pour cet utilisateur.

La consommation du token doit être atomique afin d'éviter qu'un même token puisse être utilisé simultanément plusieurs fois.

---

# API backend

Adapter les endpoints à l'architecture existante.

Le résultat attendu doit comporter au minimum les opérations suivantes :

### Inscription

```http
POST /auth/register
```

Création du compte puis génération et envoi du lien de définition du mot de passe.

### Demande de reset

```http
POST /auth/password-reset/request
```

Body :

```json
{
  "email": "user@example.com"
}
```

Important : cet endpoint ne doit **jamais révéler si l'adresse email existe ou non**.

La réponse doit être identique dans les deux cas, par exemple :

```json
{
  "detail": "Si un compte correspondant existe, un email a été envoyé."
}
```

Cela permet d'éviter l'énumération des utilisateurs.

### Définition / réinitialisation du mot de passe

Créer un endpoint permettant d'utiliser le token :

```http
POST /auth/password/set
```

Body :

```json
{
  "token": "...",
  "password": "..."
}
```

Cet endpoint est accessible sans authentification classique, car la possession du token constitue l'autorisation temporaire permettant cette opération.

Le backend doit vérifier :

1. que le token existe ;
2. que son hash correspond ;
3. qu'il n'est pas expiré ;
4. qu'il n'a pas déjà été utilisé ;
5. que son action autorise la définition du mot de passe ;
6. que le mot de passe respecte les règles de sécurité de l'application.

Ensuite :

1. modifier le mot de passe avec le mécanisme Django approprié (`set_password`) ;
2. sauvegarder l'utilisateur ;
3. marquer le token comme utilisé ;
4. invalider si nécessaire les autres sessions/tokens d'authentification existants selon les mécanismes déjà présents dans l'application.

---

# Frontend React

Créer ou adapter une page :

```text
/set-password
```

Elle doit récupérer le token présent dans l'URL :

```text
/set-password?token=XYZ
```

Afficher un formulaire avec :

* nouveau mot de passe ;
* confirmation du mot de passe ;
* validation côté frontend ;
* messages d'erreur compréhensibles ;
* état de chargement ;
* succès ;
* token invalide ;
* token expiré ;
* token déjà utilisé.

Le frontend ne doit pas considérer le token comme une authentification générale.

Il doit simplement le transmettre à Django lors de la soumission.

Après un succès, rediriger l'utilisateur vers la page de connexion ou vers le comportement prévu par l'architecture existante.

Ne pas stocker le token dans `localStorage`.

Éviter également de conserver inutilement le token dans un store global ou dans une URL après son utilisation.

---

# Emails

Implémenter ou réutiliser le système d'envoi d'emails existant.

Prévoir au minimum deux types d'emails :

### Définition initiale du mot de passe

Sujet et contenu indiquant que l'utilisateur doit définir son mot de passe.

### Réinitialisation du mot de passe

Sujet et contenu indiquant qu'une demande de réinitialisation a été effectuée.

Les deux emails doivent contenir un lien vers :

```text
<FRONTEND_URL>/set-password?token=<TOKEN>
```

Ne jamais inclure le mot de passe dans l'email.

Ne jamais écrire le token en clair dans les logs applicatifs.

Si le projet dispose déjà d'un système asynchrone d'envoi d'emails (Celery, queue, etc.), l'utiliser.

---

# Rate limiting et sécurité

Ajouter un mécanisme de limitation des demandes sur l'endpoint :

```text
/auth/password-reset/request
```

afin d'éviter l'abus et le spam.

Prendre également en compte :

* HTTPS ;
* CSRF selon le mécanisme d'authentification existant ;
* validation du mot de passe côté serveur ;
* protection contre l'énumération des comptes ;
* absence de token dans les logs ;
* absence de mot de passe dans les logs ;
* absence de données sensibles dans les messages d'erreur ;
* invalidation correcte des tokens ;
* concurrence lors de la consommation d'un token.

Si certaines protections sont déjà présentes dans le projet, les réutiliser plutôt que d'en créer de nouvelles.

---

# Organisation du code

Respecter les conventions déjà utilisées dans le projet.

Si aucune convention claire n'existe, séparer autant que possible :

* modèles ;
* API/views ;
* serializers ;
* logique métier ;
* génération/validation des tokens ;
* envoi d'emails ;
* tâches asynchrones ;
* frontend ;
* tests.

Éviter de mettre toute la logique dans les views Django.

Créer notamment un service métier réutilisable pour :

```text
create_action_token(...)
validate_action_token(...)
consume_action_token(...)
```

ou une abstraction équivalente adaptée au projet.

---

# Tests

Ajouter des tests backend et frontend adaptés à l'architecture existante.

Tester au minimum :

### Token

* génération ;
* caractère aléatoire ;
* stockage uniquement du hash ;
* expiration ;
* token valide ;
* token invalide ;
* token inexistant ;
* token déjà utilisé ;
* token utilisé une deuxième fois ;
* token associé à une mauvaise action ;
* invalidation d'un ancien token lors de la génération d'un nouveau ;
* concurrence lors de la consommation.

### Création de compte

* création du compte ;
* absence de mot de passe utilisable avant définition ;
* génération du token ;
* envoi de l'email ;
* définition du mot de passe via le lien.

### Reset

* demande avec email existant ;
* demande avec email inexistant ;
* même réponse dans les deux cas ;
* email envoyé uniquement si nécessaire ;
* reset avec token valide ;
* reset avec token expiré ;
* reset avec token invalide ;
* impossibilité de réutiliser le token.

### Frontend

Tester au minimum :

* récupération du token ;
* affichage du formulaire ;
* validation des mots de passe ;
* gestion des erreurs ;
* succès ;
* redirection après succès.

---

# Contraintes importantes

Avant de coder :

1. inspecte le projet ;
2. identifie les composants existants qui peuvent être réutilisés ;
3. identifie le système d'authentification actuel ;
4. identifie le système d'envoi d'emails ;
5. identifie la stratégie de tests ;
6. propose brièvement les fichiers qui vont être modifiés/créés.

Puis implémente le module.

**Ne remplace pas l'architecture existante sans raison.**

Le résultat doit être intégré proprement au projet actuel et suivre ses conventions.

À la fin, fournis :

1. la liste des fichiers modifiés/créés ;
2. une explication courte de l'architecture retenue ;
3. la liste des endpoints ajoutés/modifiés ;
4. les éventuelles migrations à exécuter ;
5. les variables d'environnement nécessaires ;
6. les commandes permettant de lancer les tests ;
7. les éventuels points de sécurité nécessitant une configuration en production.

Ne considère pas la fonctionnalité comme terminée tant que les tests pertinents ne passent pas.
