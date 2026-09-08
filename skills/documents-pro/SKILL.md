---
name: documents-pro
description: Rédiger et produire des documents professionnels en français (lettre, rapport, CV, compte rendu, devis, présentation) en PDF, Word ou HTML, avec la bonne structure et le bon ton. À utiliser dès qu'on demande un document, une lettre, un rapport, un CV.
---

<!-- Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — voir LICENSE -->

# Documents professionnels

## Démarche
1. Identifie le type de document et son destinataire. Demande UNE précision si une information indispensable manque (nom, date, montant) ; sinon fais des hypothèses raisonnables et signale-les entre crochets dans le texte, ex. [Nom de l'entreprise].
2. Rédige le contenu complet en français correct, sans fautes, sans anglicismes inutiles.
3. Produis le fichier : create_pdf pour un PDF, create_docx pour Word, write_file pour HTML ou Markdown. Nom de fichier clair sans espaces : `lettre-motivation-2026-09.pdf`.
4. Ouvre-le avec open_file et résume en deux phrases.

## Mise en forme (create_pdf / create_docx)
- Titre du document dans le paramètre `title`.
- Dans `content` : lignes `# ` pour les sous-titres, `- ` pour les puces, ligne vide entre les paragraphes.
- Paragraphes courts (3 à 5 lignes). Une idée par paragraphe.

## Lettre (motivation, réclamation, résiliation, administrative)
- En-tête : expéditeur (nom, adresse, e-mail, téléphone), puis destinataire, puis lieu et date à droite (« Paris, le 8 septembre 2026 »).
- Objet en gras : « Objet : Candidature au poste de … ».
- Formule d'appel : « Madame, Monsieur, » si inconnu.
- Corps en 3 paragraphes : pourquoi j'écris ; ce que j'apporte ou ce que je demande ; ce que je propose ensuite.
- Formule de politesse standard : « Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées. »
- Signature.

## CV
- En-tête : nom, titre du poste visé, ville, e-mail, téléphone, lien.
- Sections dans l'ordre : Profil (3 lignes), Expériences (du plus récent au plus ancien : poste, entreprise, dates, 3 puces de résultats chiffrés), Formation, Compétences (groupées), Langues, Centres d'intérêt (facultatif).
- Verbes d'action, résultats mesurables (« +30 % de … »), une page si moins de 10 ans d'expérience.

## Rapport / compte rendu
- Résumé de 5 lignes en tête (contexte, constat, décision).
- Sections numérotées : Contexte, Analyse, Recommandations, Prochaines étapes (qui, quoi, quand).
- Chiffres dans des listes, pas noyés dans les phrases.

## Devis / facture (structure)
- Émetteur, client, numéro, date, validité.
- Tableau en puces : désignation, quantité, prix unitaire HT, total HT ; puis TVA et TTC.
- Conditions de paiement et mention légale.

## Ton
- Professionnel, direct, sans jargon inutile. Vouvoiement par défaut. Pas d'émojis.
- Pour un document interne ou personnel, ton plus simple, phrases courtes.
