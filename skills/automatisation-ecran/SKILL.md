---
name: automatisation-ecran
description: Méthode fiable pour agir sur l'écran (ouvrir une appli, naviguer sur un site, remplir un formulaire, se connecter) avec see_screen, click_element, type_text, press_keys. À utiliser pour toute tâche qui demande de cliquer ou taper dans une fenêtre.
---

<!-- Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE -->

# Agir sur l'écran de façon fiable

## Boucle de base : regarder, agir, vérifier
1. **Regarde** : see_screen. Lis la fenêtre active et la liste des éléments (nom [type] -> x,y).
2. **Agis** : UNE action à la fois. Préfère `click_element(nom)` avec le nom exact de la liste. Utilise `click(x, y)` seulement si l'élément n'est pas listé, avec les coordonnées de la grille rouge.
3. **Vérifie** : see_screen à nouveau. Si le résultat attendu n'est pas là, ne répète pas la même action plus de deux fois : essaie autrement (autre élément, raccourci clavier, scroll).

## Ouvrir et amener une fenêtre
- Application : `open_app("Nom")`, puis see_screen jusqu'à voir la fenêtre (au plus 3 fois).
- Site web : `open_url("https://…")`, puis see_screen.
- Fenêtre déjà ouverte : `focus_window("morceau du titre")`.

## Taper du texte
- Clique TOUJOURS dans le champ avant `type_text`. Vérifie que le champ a le focus (curseur, bordure) ; en cas de doute, clique à nouveau.
- Pour valider : `type_text(texte, press_enter=True)` ou `press_keys("enter")`.
- Pour effacer un champ avant d'écrire : `press_keys("ctrl+a")` puis `press_keys("backspace")`.
- Champs de recherche : tape puis Entrée, puis see_screen pour lire les résultats.

## Se connecter à un compte
- Repère le champ e-mail ou identifiant dans la liste (types Edit, noms « E-mail », « Adresse e-mail », « Identifiant », « Nom d'utilisateur »). Clique dedans, tape exactement ce que l'utilisateur a dicté.
- Repère le champ mot de passe (nom « Mot de passe », « Password »). Clique dedans, tape le mot de passe dicté. Ne le répète jamais à voix haute ni dans ta réponse.
- Clique sur « Se connecter » / « Connexion » / « Sign in », puis see_screen pour confirmer.
- Si un code de vérification est demandé, dis-le à l'utilisateur et attends.

## Navigation web
- Cookies : cherche « Tout refuser » ou « Continuer sans accepter » ; sinon « Accepter ».
- Faire défiler : `scroll(-5)` vers le bas, `scroll(5)` vers le haut, puis see_screen.
- Onglets : `press_keys("ctrl+t")` nouvel onglet, `press_keys("ctrl+l")` barre d'adresse, `press_keys("ctrl+w")` fermer.
- Retour : `press_keys("alt+left")`.

## Prudence
- Ne clique jamais sur « Supprimer », « Payer », « Confirmer l'achat », « Désinstaller » sans que l'utilisateur l'ait demandé explicitement dans cette conversation.
- Si un écran est inattendu (popup, erreur, page inconnue), décris-le à l'utilisateur en une phrase et demande quoi faire.
- Quand la tâche est finie, dis-le en une phrase et arrête d'agir.
