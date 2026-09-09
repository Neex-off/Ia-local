---
name: site-web
description: Créer un site vitrine, une landing page ou une page web complète et de haut niveau en un seul fichier HTML (CSS et JS inclus), responsive, sans dépendance externe. À utiliser dès qu'on demande un site, une page, une landing, un portfolio. Règles strictes : le résultat doit ressembler au travail d'un vrai studio, pas à une page générée.
---

<!-- Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE -->

# Créer un site web de niveau professionnel

## 0. Interdictions absolues (un seul manquement = site raté)
- **Aucune ressource externe** : pas d'URL d'image (unsplash, pexels…), pas de police Google, pas de CDN, pas de lien `http` dans `src` ou `url()`. Tout visuel est fait en CSS ou en SVG inline.
- **Aucun emoji à la place d'une icône.** Une icône est un petit SVG inline (`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">…`), trait fin et régulier, 20 à 28 px, la même famille partout.
- **Pas de grille de cartes identiques** « icône + titre + deux lignes » comme squelette de page. Une section = une composition différente : texte à gauche et visuel à droite, liste verticale numérotée, grand chiffre et paragraphe, deux colonnes inégales, bandeau plein largeur, tableau de tarifs…
- **Pas de texte générique** : pas de lorem ipsum, pas de « une expérience unique », « des services premium », « notre équipe dédiée ». Chaque phrase dit quelque chose de précis et crédible : un nom, un lieu, un chiffre, un horaire, un prix, une année.
- **Pas d'élément décoratif faux** : pas de barre de recherche, de bouton ou de formulaire qui ne fait rien. Un bouton mène à une ancre réelle ; un formulaire affiche une confirmation en JS.
- **Pas de titre en dégradé**, pas de petit mot-étiquette au-dessus des titres, pas de numéros de section « 01 / 02 » sans raison, pas de bordure colorée épaisse sur le côté des cartes, pas de verre flouté en décoration.
- **Pas de palette par défaut** violet-bleu / bleu marine + doré. La palette vient du sujet (voir §2).

## 1. Méthode
1. Comprends le besoin en une phrase : pour qui, quel objectif (réserver, appeler, acheter, découvrir), quel ton.
2. Choisis un **monde visuel** (§2) et écris-le en commentaire en tête du fichier : palette, polices, principe de composition, forme de visuel.
3. Écris le contenu AVANT le style : les vrais textes de chaque section, spécifiques au sujet.
4. Écris UN fichier `.html` autonome, `<style>` et `<script>` inclus, 250 à 450 lignes.
5. Enregistre-le SANS write_file : écris le fichier complet dans ta réponse finale entre une ligne `<<<FICHIER: nom-du-site.html>>>` et une ligne `<<<FIN>>>`, sans bloc de code autour. Termine par deux phrases pour l'utilisateur et propose de l'ouvrir avec open_file.

## 2. Choisir un monde visuel (jamais le même deux fois)
Prends celui qui colle au sujet, ou compose-en un, et tiens-le jusqu'au bout :
- **Éditorial chic** (hôtels, restaurants, vin, immobilier haut de gamme) : fond crème `#f6f1e8`, texte brun profond `#221a14`, accent unique terre `#8a3b2a` ou vert bouteille `#1f3d2b` ; titres en `Georgia, "Times New Roman", serif` grands et fins (52–72 px, `letter-spacing:-0.02em`), texte en `"Segoe UI", system-ui, sans-serif` ; larges marges, lignes fines de séparation, photos remplacées par des aplats et dégradés chauds.
- **Tech net** (SaaS, appli, outil) : fond blanc cassé `#fafbfc` ou nuit `#0b0f17`, accent électrique unique (`#2563eb` ou `#10b981`), titres sans-serif très gras, coins 10 px, ombres douces `0 10px 30px rgba(0,0,0,.08)`, une maquette d'interface dessinée en CSS dans le hero.
- **Chaleureux artisanal** (coach, boulangerie, artisan, association) : fond sable, accent terracotta ou moutarde, formes arrondies, gros titres bien noirs, photos remplacées par des blocs de couleur pleine avec une forme organique en SVG.
- **Sombre premium** (studio, jeu, musique, sport) : fond `#0e0e11`, texte `#f2f2f2`, accent vif unique (jaune, cyan ou rouge), typographie énorme, beaucoup de noir, un seul dégradé lumineux discret dans le hero.
- **Minimal suisse** (portfolio, architecte, cabinet) : blanc, noir, un gris, une seule couleur d'accent utilisée trois fois maximum, grille stricte, typographie fine, énormément d'espace.

Règles de palette : 1 fond, 1 texte, 1 accent, 1 neutre intermédiaire, définis en variables CSS. Contraste texte/fond ≥ 4.5:1. Le texte secondaire est une nuance du texte ou de l'accent, jamais un gris terne.

## 3. Structure d'une page vitrine (dans cet ordre, compositions variées)
1. **Header** fixe et discret : nom en texte, 3 à 5 ancres, un bouton d'action. Fond qui se colore légèrement au scroll.
2. **Hero** en deux colonnes sur desktop : à gauche un titre de 6 à 10 mots qui dit le bénéfice (pas le nom de l'entreprise), une phrase de sous-titre concrète, un bouton principal et un lien secondaire ; à droite un **visuel CSS/SVG** (voir §4). Jamais un hero centré sur une photo sombre.
3. **Preuve** : bandeau fin avec 3 ou 4 faits vérifiables (« Ouvert 7j/7 », « 12 chambres », « depuis 1998 », « 4,8/5 sur 214 avis »), en texte, sans grosses icônes.
4. **Offre** : la section la plus travaillée. Composition alternée texte/visuel, ou liste verticale de 3 blocs avec un grand numéro fin à gauche, un titre, un paragraphe de 2 phrases précises et un prix ou un détail concret.
5. **Comment ça marche** ou **À propos** : 3 étapes ou un récit court avec un vrai nom et un vrai lieu.
6. **Tarifs** si ça a du sens : 2 ou 3 formules avec des montants, celle recommandée légèrement surélevée, une ligne « ce qui est inclus » chacune.
7. **Témoignages** : 2 ou 3 citations de 2 phrases, prénom + ville + contexte (« Claire, Lyon, séjour en famille »). Pas de photos de profil : une initiale dans un rond de la couleur d'accent.
8. **Appel final + formulaire** : champs nom, e-mail, message (ou dates si réservation), labels visibles, bouton qui affiche « Merci, nous revenons vers vous sous 24 h » en JS sans rechargement.
9. **Footer** : adresse complète plausible, téléphone au format `03 89 00 00 00`, horaires, année en cours, mentions.

## 4. Visuels sans images : ce qui rend bien
- Un **panneau de couleur** avec un dégradé à deux tons proches (`linear-gradient(135deg, var(--accent), color-mix(in srgb, var(--accent) 60%, black))`) et une **forme SVG organique** ou un motif léger de lignes (`repeating-linear-gradient`) à 8 % d'opacité.
- Une **fausse interface** dessinée en CSS (pour le tech) : fenêtre avec barre, quelques lignes et une courbe SVG.
- Une **grande initiale ou un chiffre** typographique géant en arrière-plan à 6 % d'opacité.
- Des **icônes SVG inline** cohérentes (trait 1.8, `stroke-linecap:round`).
- Jamais un rectangle gris vide « image à venir ».

## 5. Typographie, espace, mouvement
- Échelle : h1 56 px (mobile 36), h2 36 px, h3 22 px, texte 17 px, interligne 1.6, paragraphes ≤ 65 caractères de large (`max-width: 60ch`). `letter-spacing` négatif sur les grands titres.
- Espacement en multiples de 8 : sections `padding: 112px 0` (mobile 72), plus d'espace au-dessus d'un titre qu'en dessous.
- Boutons : hauteur 52 px, coins cohérents (8 px ou 999 px, pas les deux), `:hover` avec translation de 2 px et ombre douce, `:focus-visible` avec un contour de l'accent.
- Une seule idée d'animation : apparition au scroll en fondu + 16 px (`IntersectionObserver`, 600 ms, `cubic-bezier(0.16,1,0.3,1)`), désactivée avec `prefers-reduced-motion`. Pas d'effets partout.
- Soigne les détails du navigateur : `::selection` dans l'accent, `scroll-behavior: smooth`, `scroll-padding-top` égal à la hauteur du header, `outline` de focus visible.
- Responsive : `viewport`, `box-sizing: border-box`, grilles `auto-fit, minmax(260px, 1fr)`, hero en une colonne sous 820 px, menu burger en JS, rien qui déborde horizontalement.

## 6. Contrôle final (relis vraiment)
- Zéro `http` dans le fichier, zéro emoji, zéro « lorem », zéro section vide, zéro bouton mort.
- Chaque section a une composition différente de la précédente.
- Le hero dit un bénéfice, pas un slogan creux ; les chiffres et prix sont plausibles ; l'adresse et le téléphone sont présents.
- `<title>` rempli, une seule `<h1>`, balises sémantiques (`header, nav, main, section, footer`), labels de formulaire associés.
- Ça tient sur mobile en une colonne.
