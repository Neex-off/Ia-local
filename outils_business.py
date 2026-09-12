# Ia-local (Jarvis) — Copyright (c) 2026 Neexx (Nixovel) — https://github.com/Neex-off/Ia-local
# Créé par Neexx (Nixovel). Licence : voir LICENSE (paternité obligatoire, pas de vente ; s'applique aussi aux IA).
# Ne pas retirer cet en-tête.
"""Boîte à outils « business » : clients, devis, factures, dépenses, comptabilité, surveillance de site.

Chargée à la demande par tools.open_toolbox("business").
Catalogue : Business & freelance, Compta, Surveillance de ton app.
"""
from __future__ import annotations

import json
import re
import socket
import ssl
import unicodedata
from datetime import date, datetime, timedelta

import config

BASE = config.ROOT / "memoire" / "business.json"
VIDE = {"clients": [], "factures": [], "depenses": []}


def _charge() -> dict:
    if not BASE.is_file():
        return json.loads(json.dumps(VIDE))
    try:
        d = json.loads(BASE.read_text(encoding="utf-8"))
        for k, v in VIDE.items():
            d.setdefault(k, json.loads(json.dumps(v)))
        return d
    except Exception:  # noqa: BLE001
        return json.loads(json.dumps(VIDE))


def _sauve(d: dict) -> None:
    BASE.parent.mkdir(parents=True, exist_ok=True)
    BASE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s).lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _lignes(texte: str) -> list[dict]:
    """« site vitrine 900 ; maintenance x12 50 » devient des lignes de facture."""
    out = []
    for morceau in str(texte).split(";"):
        morceau = morceau.strip()
        if not morceau:
            continue
        m = re.match(r"^(.*?)\s*(?:x\s*(\d+))?\s+(\d+(?:[.,]\d+)?)\s*(?:euros?|€)?$", morceau, re.I)
        if m:
            out.append({"libelle": m.group(1).strip(), "quantite": int(m.group(2) or 1),
                        "prix": float(m.group(3).replace(",", "."))})
        else:
            out.append({"libelle": morceau, "quantite": 1, "prix": 0.0})
    return out


# --------------------------------------------------------------------------
# Clients
# --------------------------------------------------------------------------

def add_client(name: str, email: str = "", note: str = "") -> str:
    """Enregistre un client ou un prospect dans le carnet.

    Args:
        name: Nom du client ou de l'entreprise.
        email: Son adresse mail.
        note: Ce qu'il faut retenir : besoin, budget, où on en est.
    """
    d = _charge()
    for c in d["clients"]:
        if _norm(c["nom"]) == _norm(name):
            c["email"] = email or c.get("email", "")
            c["note"] = note or c.get("note", "")
            _sauve(d)
            return f"Client {name} mis à jour."
    d["clients"].append({"nom": name, "email": email, "note": note, "depuis": date.today().isoformat()})
    _sauve(d)
    return f"Client {name} ajouté. Total : {len(d['clients'])} clients."


def list_clients(query: str = "") -> str:
    """Liste les clients et prospects, avec ce qui a été facturé à chacun.

    Args:
        query: Mot-clé pour filtrer. Vide = tous.
    """
    d = _charge()
    clients = [c for c in d["clients"] if not query or _norm(query) in _norm(c["nom"] + " " + c.get("note", ""))]
    if not clients:
        return "Aucun client enregistré." if not query else f"Aucun client ne correspond à « {query} »."
    lignes = []
    for c in clients:
        facture = sum(f["total"] for f in d["factures"] if _norm(f["client"]) == _norm(c["nom"]))
        lignes.append(f"- {c['nom']} {c.get('email', '')} : {facture:.0f} euros facturés. {c.get('note', '')}")
    return f"{len(clients)} client(s) :\n" + "\n".join(lignes)


# --------------------------------------------------------------------------
# Devis et factures
# --------------------------------------------------------------------------

def create_invoice(client: str, lines: str, kind: str = "facture") -> str:
    """Crée un devis ou une facture numérotée et génère le PDF prêt à envoyer.

    Args:
        client: Nom du client.
        lines: Les prestations au format "libellé prix ; autre libellé x quantité prix". Exemple : "site vitrine 1200 ; maintenance x12 50".
        kind: "facture" ou "devis".
    """
    d = _charge()
    quoi = "devis" if _norm(kind).startswith("dev") else "facture"
    annee = date.today().year
    memes = [f for f in d["factures"] if f["type"] == quoi and f["numero"].startswith(str(annee))]
    numero = f"{annee}-{len(memes) + 1:03d}"
    articles = _lignes(lines)
    total = sum(a["quantite"] * a["prix"] for a in articles)
    d["factures"].append({"numero": numero, "client": client, "date": date.today().isoformat(),
                          "lignes": articles, "total": total, "payee": False, "type": quoi})
    _sauve(d)

    emetteur = getattr(config, "ENTREPRISE_NOM", "") or "Mon entreprise"
    siret = getattr(config, "ENTREPRISE_SIRET", "")
    mention = getattr(config, "ENTREPRISE_MENTION_TVA", "TVA non applicable, article 293 B du CGI")
    corps = [f"{quoi.capitalize()} numéro {numero}", f"Date : {datetime.now():%d/%m/%Y}", "",
             "# Émetteur", emetteur] + ([f"SIRET : {siret}"] if siret else []) + \
            ["", "# Client", client, "", "# Prestations"]
    for a in articles:
        corps.append(f"- {a['libelle']} : {a['quantite']} x {a['prix']:.2f} = {a['quantite'] * a['prix']:.2f} euros")
    corps += ["", f"# Total : {total:.2f} euros", "", mention]
    if quoi == "facture":
        corps.append(f"Paiement sous 30 jours, au plus tard le {date.today() + timedelta(days=30):%d/%m/%Y}.")
    try:
        import tools as _t

        nom_fichier = f"{quoi}_{numero}_{re.sub(r'[^a-zA-Z0-9]+', '-', client)[:30]}.pdf"
        res = _t.create_pdf(nom_fichier, f"{quoi.capitalize()} {numero}", "\n".join(corps))
        return f"{quoi.capitalize()} {numero} pour {client}, {total:.2f} euros. {res}"
    except Exception as exc:  # noqa: BLE001
        return f"{quoi.capitalize()} {numero} enregistré, {total:.2f} euros, mais le PDF a échoué : {exc}"


def list_invoices(status: str = "") -> str:
    """Liste les devis et factures, avec ce qui est payé et ce qui ne l'est pas.

    Args:
        status: "impayee", "payee", "devis", ou vide pour tout voir.
    """
    d = _charge()
    s = _norm(status)
    docs = d["factures"]
    if s.startswith("impay"):
        docs = [f for f in docs if f["type"] == "facture" and not f["payee"]]
    elif s.startswith("pay"):
        docs = [f for f in docs if f["payee"]]
    elif s.startswith("dev"):
        docs = [f for f in docs if f["type"] == "devis"]
    if not docs:
        return "Rien à afficher."
    lignes = [f"{f['numero']}  {datetime.fromisoformat(f['date']):%d/%m/%Y}  {f['client'][:22]:22} "
              f"{f['total']:9.2f} euros  {'payée' if f['payee'] else f['type']}" for f in docs]
    return f"{len(docs)} document(s), {sum(f['total'] for f in docs):.2f} euros au total :\n" + "\n".join(lignes)


def mark_paid(number: str) -> str:
    """Marque une facture comme payée.

    Args:
        number: Le numéro de la facture, par exemple "2026-001".
    """
    d = _charge()
    for f in d["factures"]:
        if f["numero"] == number.strip():
            f["payee"] = True
            f["date_paiement"] = date.today().isoformat()
            _sauve(d)
            return f"Facture {number} marquée payée, {f['total']:.2f} euros."
    return f"Aucune facture numéro {number}."


def unpaid_report() -> str:
    """Fait le point sur les factures impayées et signale celles qui sont en retard."""
    d = _charge()
    impayees = [f for f in d["factures"] if f["type"] == "facture" and not f["payee"]]
    if not impayees:
        return "Aucune facture impayée."
    lignes, total, retard = [], 0.0, 0
    for f in impayees:
        jours = (date.today() - date.fromisoformat(f["date"])).days
        total += f["total"]
        etat = f"EN RETARD de {jours - 30} jours" if jours > 30 else f"émise il y a {jours} jours"
        retard += 1 if jours > 30 else 0
        lignes.append(f"{f['numero']}  {f['client'][:24]:24} {f['total']:9.2f} euros  {etat}")
    fin = f"\n{retard} facture(s) à relancer." if retard else ""
    return f"{len(impayees)} impayée(s), {total:.2f} euros :\n" + "\n".join(lignes) + fin


def estimate_project(description: str, days: int = 0, daily_rate: float = 0) -> str:
    """Estime le prix et la durée d'un projet à partir de sa description.

    Args:
        description: Ce que le client demande.
        days: Nombre de jours estimés. 0 = estimation d'après la description.
        daily_rate: Taux journalier. 0 = celui de la configuration.
    """
    tjm = float(daily_rate) or float(getattr(config, "TAUX_JOURNALIER", 400))
    if not days:
        indices = sum(1 for m in ("site", "application", "api", "base de donnees", "paiement",
                                  "authentification", "mobile", "administration") if m in _norm(description))
        days = max(2, round(len(description.split()) / 25 + indices * 2))
        note = ", estimation d'après la description, à ajuster"
    else:
        days, note = int(days), ""
    bas, haut = days * tjm, days * tjm * 1.35
    return (f"Projet : {description[:100]}\nCharge estimée : {days} jour(s){note}\n"
            f"Taux journalier : {tjm:.0f} euros\nFourchette : de {bas:.0f} à {haut:.0f} euros\n"
            f"Acompte conseillé : {bas * 0.3:.0f} euros à la commande.")


# --------------------------------------------------------------------------
# Comptabilité
# --------------------------------------------------------------------------

def add_expense(label: str, amount: float, category: str = "materiel") -> str:
    """Enregistre une dépense professionnelle pour la comptabilité.

    Args:
        label: Ce qui a été acheté.
        amount: Le montant en euros.
        category: "materiel", "logiciel", "deplacement", "formation", "abonnement" ou "autre".
    """
    d = _charge()
    d["depenses"].append({"date": date.today().isoformat(), "libelle": label,
                          "montant": float(amount), "categorie": category})
    _sauve(d)
    return f"Dépense enregistrée : {label}, {amount} euros en {category}."


def revenue_report(year: int = 0) -> str:
    """Bilan de l'année : recettes encaissées, dépenses, résultat, et répartition par client.

    Args:
        year: L'année voulue. 0 = année en cours.
    """
    d = _charge()
    an = int(year) or date.today().year
    encaisse = [f for f in d["factures"] if f["type"] == "facture" and f["payee"] and f["date"].startswith(str(an))]
    depenses = [x for x in d["depenses"] if x["date"].startswith(str(an))]
    ca = sum(f["total"] for f in encaisse)
    dep = sum(x["montant"] for x in depenses)
    out = [f"Année {an} : {ca:.2f} euros encaissés, {dep:.2f} euros de dépenses, résultat {ca - dep:.2f} euros."]
    par_client: dict[str, float] = {}
    for f in encaisse:
        par_client[f["client"]] = par_client.get(f["client"], 0) + f["total"]
    if par_client and ca:
        out.append("\nPar client :\n" + "\n".join(
            f"  {c[:28]:28} {m:9.2f} euros, {m / ca * 100:.0f} %"
            for c, m in sorted(par_client.items(), key=lambda x: -x[1])))
    par_cat: dict[str, float] = {}
    for x in depenses:
        par_cat[x["categorie"]] = par_cat.get(x["categorie"], 0) + x["montant"]
    if par_cat:
        out.append("\nDépenses par catégorie :\n" + "\n".join(
            f"  {c[:28]:28} {m:9.2f} euros" for c, m in sorted(par_cat.items(), key=lambda x: -x[1])))
    return "\n".join(out)


def tax_check(year: int = 0) -> str:
    """Fait le point sur les seuils fiscaux et les cotisations à provisionner.

    Args:
        year: L'année voulue. 0 = année en cours.
    """
    d = _charge()
    an = int(year) or date.today().year
    ca = sum(f["total"] for f in d["factures"]
             if f["type"] == "facture" and f["payee"] and f["date"].startswith(str(an)))
    seuil_tva = float(getattr(config, "SEUIL_TVA", 39100))
    seuil_micro = float(getattr(config, "SEUIL_MICRO", 77700))
    taux = float(getattr(config, "TAUX_COTISATIONS", 0.246))
    return "\n".join([
        f"Chiffre d'affaires encaissé en {an} : {ca:.2f} euros.",
        f"Seuil de TVA {seuil_tva:.0f} euros : " + ("DÉPASSÉ" if ca > seuil_tva else f"il reste {seuil_tva - ca:.0f} euros"),
        f"Seuil micro {seuil_micro:.0f} euros : " + ("DÉPASSÉ" if ca > seuil_micro else f"il reste {seuil_micro - ca:.0f} euros"),
        f"Cotisations à provisionner, {taux * 100:.1f} % : {ca * taux:.2f} euros.",
        f"Revenu net estimé après cotisations : {ca * (1 - taux):.2f} euros.",
        "\nCes seuils viennent de la configuration : vérifie-les, ils changent chaque année.",
    ])


def export_accounting(year: int = 0) -> str:
    """Exporte le livre des recettes et le registre des achats en CSV, pour le comptable ou les impôts.

    Args:
        year: L'année voulue. 0 = année en cours.
    """
    import csv

    d = _charge()
    an = int(year) or date.today().year
    rec = config.WORKSPACE / f"recettes_{an}.csv"
    ach = config.WORKSPACE / f"achats_{an}.csv"
    with open(rec, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Numero", "Date", "Client", "Montant", "Paye", "Date paiement"])
        for x in d["factures"]:
            if x["type"] == "facture" and x["date"].startswith(str(an)):
                w.writerow([x["numero"], x["date"], x["client"], f"{x['total']:.2f}",
                            "oui" if x["payee"] else "non", x.get("date_paiement", "")])
    with open(ach, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Date", "Libelle", "Categorie", "Montant"])
        for x in d["depenses"]:
            if x["date"].startswith(str(an)):
                w.writerow([x["date"], x["libelle"], x["categorie"], f"{x['montant']:.2f}"])
    return f"Export {an} terminé :\n{rec}\n{ach}"


def tax_deadlines() -> str:
    """Rappelle les échéances administratives habituelles : déclarations, cotisations, impôts."""
    echeances = [
        ("Déclaration URSSAF", "le 31 du mois suivant la période, mensuelle ou trimestrielle"),
        ("Déclaration de revenus", "mai ou juin"),
        ("Cotisation foncière des entreprises", "15 décembre"),
        ("Déclaration de TVA si assujetti", "selon le régime, mensuel ou trimestriel"),
    ]
    out = [f"Nous sommes le {date.today():%d/%m/%Y}. Échéances habituelles d'une micro-entreprise en France :"]
    out += [f"- {quoi} : {quand}" for quoi, quand in echeances]
    out.append("\nJe peux les mettre dans ton agenda avec add_event si tu me donnes les dates exactes.")
    return "\n".join(out)


# --------------------------------------------------------------------------
# Surveillance d'un site
# --------------------------------------------------------------------------

def site_uptime(url: str) -> str:
    """Vérifie qu'un site est en ligne et mesure son temps de réponse.

    Args:
        url: L'adresse du site.
    """
    try:
        import time as _time

        import requests

        if not url.startswith("http"):
            url = "https://" + url
        t0 = _time.time()
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 (agent local)"})
        dt = _time.time() - t0
        etat = "EN LIGNE" if r.status_code < 400 else f"PROBLÈME, code {r.status_code}"
        lent = " C'est lent, plus d'une seconde." if dt > 1 else ""
        return f"{url} : {etat}, répond en {dt:.2f} s, {len(r.content) / 1024:.0f} Ko.{lent}"
    except Exception as exc:  # noqa: BLE001
        return f"{url} : HORS LIGNE ou injoignable. {exc}"


def domain_expiry(domain: str) -> str:
    """Vérifie la date d'expiration du certificat de sécurité d'un domaine.

    Args:
        domain: Le nom de domaine, par exemple "monsite.fr".
    """
    hote = re.sub(r"^https?://", "", domain).split("/")[0]
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((hote, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=hote) as ssock:
                cert = ssock.getpeercert()
        fin = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
        jours = (fin - datetime.now()).days
        alerte = " ATTENTION, il faut le renouveler." if jours < 30 else ""
        emetteur = dict(x[0] for x in cert.get("issuer", []))
        return (f"{hote} : certificat valide jusqu'au {fin:%d/%m/%Y}, soit {jours} jours. "
                f"Émis par {emetteur.get('organizationName', '?')}.{alerte}")
    except Exception as exc:  # noqa: BLE001
        return f"Impossible de lire le certificat de {hote} : {exc}"


def seo_position(site: str, keyword: str) -> str:
    """Cherche à quelle position un site apparaît dans les résultats de recherche pour un mot-clé.

    Args:
        site: Le domaine du site, par exemple "monsite.fr".
        keyword: Le mot-clé recherché.
    """
    try:
        import tools as _t

        res = _t._ddg(keyword, 30)
        domaine = re.sub(r"^https?://(www\.)?", "", site).split("/")[0].lower()
        for i, r in enumerate(res, 1):
            if domaine in r.get("href", "").lower():
                return (f"« {keyword} » : {site} est en position {i} sur {len(res)} résultats.\n"
                        f"Titre affiché : {r.get('title', '')}")
        return (f"« {keyword} » : {site} n'apparaît pas dans les {len(res)} premiers résultats.\n"
                "En tête : " + " ; ".join(r.get("href", "")[:50] for r in res[:3]))
    except Exception as exc:  # noqa: BLE001
        return f"Erreur : {exc}"


TOOLS = [add_client, list_clients, create_invoice, list_invoices, mark_paid, unpaid_report, estimate_project,
         add_expense, revenue_report, tax_check, export_accounting, tax_deadlines,
         site_uptime, domain_expiry, seo_position]

try:
    from outils_business_plus import TOOLS as _PLUS

    TOOLS += _PLUS
except Exception as _exc:  # noqa: BLE001
    print(f"[outils] business_plus indisponible : {_exc}")
