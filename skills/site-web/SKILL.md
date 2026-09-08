---
name: site-web
description: Créer un site vitrine, une landing page ou une page web complète et soignée en un seul fichier HTML (CSS et JS inclus), responsive, sans dépendance externe. À utiliser dès qu'on demande un site, une page, une landing, un portfolio.
---

<!-- Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE -->

# Créer un site web complet et professionnel

## Méthode
1. Comprends le besoin en une phrase : pour qui, quel but (vendre, présenter, contacter), quel ton.
2. Choisis une direction visuelle nette AVANT d'écrire : une palette de 3 couleurs (fond, texte, accent), une paire de polices système (titres + texte), un style (épuré, bold, chaleureux, tech…). Écris-la en commentaire en haut du fichier.
3. Écris UN fichier `.html` autonome : `<style>` et `<script>` dans le fichier, aucune bibliothèque externe, images remplacées par des dégradés, formes CSS ou emojis.
4. Enregistre-le SANS write_file (trop long pour un argument d'outil) : écris le fichier complet dans ta réponse finale entre une ligne `<<<FICHIER: site-coach-sportif.html>>>` et une ligne `<<<FIN>>>`, sans bloc de code autour. Il est enregistré automatiquement dans le dossier de travail. Termine par une phrase pour l'utilisateur, et propose de l'ouvrir avec open_file.

## Structure d'une page vitrine (dans cet ordre)
- **Header** fixe : logo texte à gauche, 3 à 5 liens d'ancrage, un bouton d'action.
- **Hero** : un titre fort (max 8 mots), un sous-titre d'une phrase, un bouton principal, éventuellement un visuel CSS.
- **Preuve / confiance** : chiffres clés, logos, ou une citation client.
- **Offre** : 3 cartes (icône, titre, 2 lignes) sur une grille responsive.
- **À propos** ou **Comment ça marche** : 3 étapes numérotées.
- **Tarifs** si pertinent : 2 ou 3 formules, celle du milieu mise en avant.
- **Témoignages** : 2 ou 3 cartes courtes.
- **Appel à l'action** final + **formulaire** de contact simple (nom, e-mail, message).
- **Footer** : liens, mentions, réseaux.

## Règles de design qui font la différence
- Espacement généreux et régulier : échelle 8 px (8, 16, 24, 32, 48, 64, 96). Sections avec `padding: 96px 0` sur desktop, 64px sur mobile.
- Largeur de contenu max 1100 px centrée, texte de paragraphe max 65 caractères par ligne.
- Hiérarchie typographique nette : h1 48–64 px, h2 32–40 px, texte 16–18 px, interligne 1.6. Une seule police pour les titres, une pour le texte.
- Une seule couleur d'accent, utilisée pour les boutons et 2 ou 3 touches. Fond clair ou fond sombre, pas les deux mélangés sans intention.
- Boutons : coins arrondis cohérents (8 px ou 999 px), état `:hover` visible (translation 2 px + ombre), `:focus-visible` marqué.
- Cartes : bord 1 px subtil ou ombre douce, jamais les deux lourds. Pas d'ombres noires épaisses.
- Images absentes : utilise des dégradés doux, des formes géométriques CSS ou des icônes SVG inline simples. Jamais de lien vers une image externe.
- Évite l'aspect « généré » : pas de violet-bleu par défaut partout, pas de 6 sections identiques, pas de texte lorem ipsum. Écris un vrai contenu crédible et spécifique au sujet.

## Responsive et qualité
- `<meta name="viewport" content="width=device-width, initial-scale=1">`, `box-sizing: border-box` global.
- Grilles avec `display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr))`.
- Menu mobile : bouton burger simple en JS qui bascule une classe.
- Animations discrètes : apparition des sections au scroll avec `IntersectionObserver` (opacité + translation 16 px, 500 ms, `cubic-bezier(0.4,0,0.2,1)`), respect de `prefers-reduced-motion`.
- Accessibilité : contraste ≥ 4.5:1, balises sémantiques (`header, nav, main, section, footer`), `alt` ou `aria-label` sur les éléments décoratifs, boutons réels pour les actions.
- Formulaire : `label` associés, `required`, message de confirmation en JS sans rechargement.

## Avant de rendre
Relis le fichier : titre `<title>` rempli, aucune URL externe, aucune section vide, le bouton principal mène quelque part, ça tient sur mobile (une colonne). Vise 150 à 300 lignes : complet mais sans bavardage CSS. Dis à l'utilisateur en deux phrases ce que tu as fait et ce qu'il peut demander à changer (couleurs, textes, sections).
