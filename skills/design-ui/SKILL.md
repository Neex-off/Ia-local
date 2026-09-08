---
name: design-ui
description: Principes de design d'interface pour rendre une page, une appli ou un composant beau, lisible et cohérent : hiérarchie, espacement, couleur, typographie, états, retours visuels. À utiliser pour concevoir, critiquer ou améliorer une interface.
---

<!-- Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE -->

# Design d'interface : les règles qui comptent

## Hiérarchie visuelle
- Une seule chose doit attirer l'œil en premier sur chaque écran. Décide laquelle avant de dessiner.
- Taille, graisse, couleur et espace : quatre leviers. Utilise-en deux à la fois, pas quatre.
- Aligne tout sur une grille (colonnes, marges identiques). Les désalignements de 2 px se voient.

## Espacement
- Échelle unique : 4, 8, 12, 16, 24, 32, 48, 64, 96 px. Jamais de valeurs au hasard.
- Plus d'espace ENTRE les groupes qu'À L'INTÉRIEUR des groupes (loi de proximité).
- Laisse respirer : la plupart des interfaces manquent de marge, pas l'inverse.

## Typographie
- Deux polices maximum. Polices système sûres : « Segoe UI », Inter, Roboto, Georgia pour un ton éditorial.
- Échelle : 12 (mentions), 14 (secondaire), 16 (texte), 20 (sous-titre), 28–32 (titre de section), 40–56 (titre de page).
- Interligne 1.5 à 1.6 pour le texte, 1.1 à 1.2 pour les grands titres. Lignes de 45 à 75 caractères.
- Couleur du texte : pas de noir pur sur blanc pur ; #1a1a1a sur #fafafa, ou gris clair sur fond sombre.

## Couleur
- Une couleur d'accent, une neutre (gris chaud ou froid), un fond. Puis des nuances de ces trois-là.
- Le sens des couleurs : vert = succès, rouge = erreur ou danger, orange = attention, bleu = information. Ne détourne pas ces codes.
- Contraste texte/fond ≥ 4.5:1. Vérifie mentalement : si tu hésites, c'est insuffisant.
- Mode sombre : fond #0f1115 à #1c1f26, jamais #000 ; textes #e6e6e6 ; accents légèrement désaturés.

## Composants et états
- Chaque élément interactif a 4 états : normal, survol, focus, actif/désactivé. Tous visibles.
- Boutons : un primaire par écran (plein), les autres secondaires (contour ou texte). Verbes à l'impératif (« Envoyer », pas « OK »).
- Formulaires : label au-dessus du champ, erreurs en texte à côté du champ, jamais seulement en rouge.
- Cartes : rayon de coin identique partout (8, 12 ou 16 px), ombre douce (`0 4px 16px rgba(0,0,0,.08)`).
- Icônes : même famille, même épaisseur de trait, 20 ou 24 px, alignées sur le texte.

## Retours et mouvement
- Toute action a un retour dans les 100 ms : changement d'état, spinner, message.
- Transitions courtes : 150 ms pour un survol, 250–400 ms pour une apparition, easing `cubic-bezier(0.4,0,0.2,1)`. Pas de rebond gratuit.
- Les états vides, de chargement et d'erreur sont conçus, pas oubliés : une phrase, une action.

## Critiquer une interface existante
Passe en revue dans l'ordre : 1) Qu'est-ce qui attire l'œil, est-ce voulu ? 2) Alignements et espacements réguliers ? 3) Trop de couleurs ou de polices ? 4) Contraste suffisant ? 5) Chaque bouton est-il clair sur ce qu'il fait ? 6) Que se passe-t-il si le texte est deux fois plus long, ou sur mobile ? Donne 3 à 5 corrections concrètes, les plus impactantes d'abord.
