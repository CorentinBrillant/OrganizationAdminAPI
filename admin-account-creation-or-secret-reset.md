# Ajouter un service administrateur de création et de réinitialisation des comptes

Je souhaite ajouter à l'application une fonctionnalité accessible **uniquement aux administrateurs** permettant de :

1. créer un nouveau compte utilisateur ;
2. envoyer à cet utilisateur un lien sécurisé lui permettant de définir son mot de passe ;
3. consulter l'état de définition du mot de passe d'un compte ;
4. renvoyer le lien de définition du mot de passe ;
5. déclencher une réinitialisation du mot de passe d'un compte existant.

Le projet possède déjà un mécanisme de token d'action utilisateur pour la définition/réinitialisation du mot de passe. **Réutilise ce mécanisme plutôt que d'en créer un nouveau.**

Avant toute modification, analyse l'architecture existante du backend Django et du frontend React et respecte les conventions déjà présentes.

---

## 1. Accès réservé aux administrateurs

Toutes les fonctionnalités d'administration doivent être protégées côté backend.

Ne pas se contenter de masquer les boutons dans React.

Le backend doit vérifier que l'utilisateur connecté possède réellement les droits administrateur requis.

Un utilisateur non authentifié ou un utilisateur authentifié sans privilèges administrateur doit obtenir une réponse d'autorisation appropriée (`401` ou `403` selon les conventions existantes).

Le frontend doit également masquer les fonctionnalités d'administration aux utilisateurs qui ne disposent pas des droits nécessaires, mais cette protection frontend est uniquement complémentaire à la protection backend.

---

# 2. Interface de gestion des utilisateurs

Ajouter ou adapter une interface d'administration permettant de gérer les comptes utilisateurs.

La page doit permettre à l'administrateur de :

* consulter la liste des utilisateurs ;
* rechercher un utilisateur ;
* ouvrir la fiche d'un utilisateur ;
* créer un nouvel utilisateur ;
* consulter l'état de son mot de passe ;
* renvoyer le lien de définition du mot de passe ;
* déclencher une réinitialisation du mot de passe.

Respecter les composants, styles, routing et conventions UX déjà utilisés dans l'application.

---

# 3. Création d'un compte par un administrateur

Ajouter une interface du type :

```text
Créer un utilisateur

Email       [________________________]

Prénom      [________________________]

Nom         [________________________]

Rôle        [________________________]

[ ] Envoyer l'email de définition du mot de passe

                 [Créer le compte]
```

Le comportement par défaut doit être d'envoyer le lien de définition du mot de passe, sauf si l'architecture existante impose un autre comportement.

Lors de la création :

1. créer le User ;
2. ne pas définir de mot de passe utilisable ;
3. créer un `UserActionToken` avec l'action appropriée ;
4. envoyer l'email contenant le lien ;
5. retourner à l'administrateur le résultat de l'opération.

Le mot de passe ne doit jamais être demandé ou manipulé par l'interface d'administration.

L'administrateur ne doit donc **jamais connaître le mot de passe de l'utilisateur**.

---

# 4. Service backend de création de compte

Ne pas mettre toute cette logique directement dans une view Django.

Créer ou réutiliser un service métier centralisé, par exemple :

```python
UserService.create_user(...)
```

ou une abstraction équivalente adaptée au projet.

Ce service doit gérer :

```text
création User
      ↓
création éventuelle UserActionToken
      ↓
envoi du lien de définition du mot de passe
```

Si l'envoi d'email est asynchrone dans le projet, utiliser le mécanisme existant.

Le service doit pouvoir être réutilisé par d'autres workflows de création de compte.

---

# 5. Statut du mot de passe

Dans la fiche utilisateur de l'administration, afficher clairement l'état du compte.

Par exemple :

```text
Mot de passe

🟠 En attente de définition

[Envoyer le lien]
```

ou :

```text
Mot de passe

🟢 Défini

[Réinitialiser le mot de passe]
```

Ne jamais afficher le mot de passe lui-même.

Utiliser autant que possible les informations déjà disponibles dans Django (`has_usable_password()`, tokens actifs, etc.) plutôt que de dupliquer inutilement l'état.

---

# 6. Renvoyer le lien de définition

Pour un compte dont le mot de passe n'a pas encore été défini, ajouter une action :

```text
[Renvoyer le lien]
```

Lorsqu'elle est appelée :

1. invalider les anciens tokens `set_password` encore valides ;
2. générer un nouveau token ;
3. définir sa date d'expiration ;
4. envoyer un nouvel email ;
5. retourner un succès à l'interface.

Le token doit être généré et stocké conformément au mécanisme de sécurité déjà implémenté.

Ne jamais afficher le token à l'administrateur.

Ne jamais le logger.

---

# 7. Réinitialiser le mot de passe d'un utilisateur

Pour un utilisateur dont le compte existe déjà et dont le mot de passe est défini, ajouter :

```text
[Réinitialiser le mot de passe]
```

L'administrateur **ne doit pas saisir lui-même le nouveau mot de passe**.

Lorsqu'il déclenche cette action :

```text
Admin
  │
  │ Réinitialiser le mot de passe
  ▼
Django
  │
  ├── invalide les anciens tokens de reset
  ├── génère un nouveau token
  └── envoie un email à l'utilisateur
          │
          ▼
       Utilisateur
          │
          ▼
   /set-password?token=...
          │
          ▼
     nouveau mot de passe
```

Le workflow doit donc réutiliser exactement le même système de définition de mot de passe que le workflow « mot de passe oublié ».

---

# 8. Confirmation avant réinitialisation

Avant de déclencher un reset depuis l'administration, afficher une confirmation.

Par exemple :

```text
Réinitialiser le mot de passe ?

Un email sera envoyé à :

jean.dupont@example.com

L'utilisateur pourra choisir un nouveau mot de passe
à partir du lien reçu.

[Annuler] [Envoyer le lien]
```

Ne pas effectuer l'action immédiatement sans confirmation.

---

# 9. API d'administration

Créer ou adapter les endpoints REST nécessaires en suivant les conventions existantes.

Conceptuellement :

```http
POST /admin/users
```

pour créer un utilisateur.

```http
POST /admin/users/{id}/password-setup
```

pour envoyer ou renvoyer le lien de définition.

```http
POST /admin/users/{id}/password-reset
```

pour déclencher une réinitialisation.

Les noms exacts doivent être adaptés au routing existant.

Tous ces endpoints doivent nécessiter une authentification et une autorisation administrateur.

Ne pas exposer les actions administratives sur les endpoints publics utilisés par les utilisateurs.

---

# 10. Réutilisation du Password/Action Token Service

Il doit exister une seule logique de génération/validation/consommation des tokens.

Les différents workflows doivent utiliser le même mécanisme :

```text
Création utilisateur
       │
       ▼
set_password token
       │
       ▼
Email
```

```text
Utilisateur → "mot de passe oublié"
       │
       ▼
password_reset token
       │
       ▼
Email
```

```text
Administrateur → "réinitialiser"
       │
       ▼
password_reset token
       │
       ▼
Email
```

Ne crée pas un deuxième système de tokens spécifique à l'administration.

---

# 11. Sécurité

Vérifier et conserver les protections suivantes :

* endpoints administratifs protégés côté backend ;
* token cryptographiquement aléatoire ;
* token stocké uniquement sous forme de hash ;
* token à usage unique ;
* expiration ;
* invalidation des anciens tokens ;
* HTTPS ;
* aucun mot de passe dans les logs ;
* aucun token dans les logs ;
* aucun mot de passe affiché à l'administrateur ;
* aucun token affiché à l'administrateur ;
* contrôle des permissions côté backend ;
* protection contre les appels répétés abusifs ;
* utilisation de `transaction.on_commit()` si nécessaire pour ne pas envoyer un email concernant une transaction qui serait finalement annulée.

---

# 12. Gestion des erreurs

L'interface doit gérer proprement :

* email déjà utilisé ;
* utilisateur inexistant ;
* utilisateur désactivé ;
* absence de permission ;
* erreur d'envoi d'email ;
* erreur réseau ;
* erreur serveur ;
* token expiré ou invalide.

Les messages présentés à l'administrateur doivent être compréhensibles mais ne doivent pas exposer de données sensibles.

---

# 13. Tests

Ajouter des tests backend et frontend.

Tester notamment :

### Permissions

* utilisateur non authentifié → accès refusé ;
* utilisateur authentifié non administrateur → accès refusé ;
* administrateur → accès autorisé.

### Création

* création réussie ;
* compte créé sans mot de passe utilisable ;
* token généré ;
* email envoyé ;
* aucune information sensible retournée par l'API.

### Renvoi du lien

* ancien token invalidé ;
* nouveau token généré ;
* email envoyé ;
* impossibilité d'utiliser l'ancien token.

### Reset administrateur

* action réservée aux administrateurs ;
* ancien token invalidé ;
* nouveau token généré ;
* email envoyé au bon utilisateur ;
* utilisateur capable de définir son nouveau mot de passe ;
* ancien mot de passe invalidé selon le comportement attendu par le système d'authentification.

### Frontend

* boutons visibles uniquement pour les administrateurs ;
* formulaire de création ;
* confirmation de reset ;
* affichage du statut du mot de passe ;
* gestion des erreurs ;
* états de chargement ;
* messages de succès.

---

# 14. Important : ne pas créer de mot de passe depuis l'administration

Le principe de sécurité recherché est :

```text
Administrateur
    │
    │ crée/réinitialise
    ▼
Envoi d'un lien
    │
    ▼
Utilisateur
    │
    │ choisit son mot de passe
    ▼
Django
```

et jamais :

```text
Administrateur
    │
    │ choisit le mot de passe
    ▼
Django
```

L'administrateur ne doit donc jamais avoir accès au mot de passe de l'utilisateur.

---

# 15. Résultat attendu

À la fin de l'implémentation, un administrateur doit pouvoir réaliser entièrement le workflow suivant :

```text
Administration
     │
     ▼
Créer utilisateur
     │
     ▼
Utilisateur créé
     │
     ▼
Email envoyé
     │
     ▼
Utilisateur clique sur le lien
     │
     ▼
/set-password
     │
     ▼
Utilisateur définit son mot de passe
     │
     ▼
Compte actif
```

Et pour un compte existant :

```text
Administration
     │
     ▼
Réinitialiser le mot de passe
     │
     ▼
Email envoyé
     │
     ▼
Utilisateur clique
     │
     ▼
/set-password
     │
     ▼
Nouveau mot de passe
```

Avant de commencer l'implémentation, inspecte le code existant et identifie les modèles, services, endpoints, composants React et mécanismes d'authentification/email qui doivent être réutilisés. Ne crée pas de doublon lorsqu'un mécanisme existant peut être étendu.
