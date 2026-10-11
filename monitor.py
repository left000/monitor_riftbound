#!/usr/bin/env python3
"""Riftbound stock checker - Spagna + Italia.

Per ogni negozio:
  1. rileva la piattaforma (Shopify, WooCommerce, PrestaShop, Magento, altro)
  2. compone l'URL di ricerca in autonomia partendo dalla home pulita
  3. filtra: solo Booster Box (24) e Case (6x) dei set ammessi, in inglese
  4. verifica lo stock sulla pagina del prodotto con PROVA POSITIVA
  5. manda su Telegram solo i prodotti realmente acquistabili
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import html as htmllib
import json
import os
import re
import threading
from urllib.parse import quote_plus, urljoin, urlparse

from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------------------------------
# Configurazione
# --------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
DEBUG = os.environ.get("DEBUG") == "1"
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "12"))
NOTIFY_ONLY_NEW = os.environ.get("NOTIFY_ONLY_NEW") == "1"
STATE_FILE = os.environ.get("STATE_FILE", "state.json")
CACHE_FILE = os.environ.get("CACHE_FILE", "stores_cache.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,it-IT,it;q=0.8,en-US,en;q=0.7",
}

ALLOWED_SETS = ["Origins", "Spiritforged", "Unleashed", "Vendetta"]
FORBIDDEN_SETS = ["Radiance"]

MIN_PRICE = {"display": 50.0, "case": 250.0}
QUERIES = ["riftbound booster box", "riftbound display", "riftbound case"]
IN_STOCK_SCHEMA = ("instock", "limitedavailability", "onlineonly")

TERMINI_ESAURITO = [
    "agotado", "agotados", "sold out", "sin stock", "no disponible",
    "out of stock", "unavailable", "sin existencias", "existencias insuficientes",
    "insuficientes", "proximamente", "próximamente", "coming soon", "reservar",
    "reserva", "pre-order", "preorder", "preventa", "reposición", "esaurito",
    "esauriti", "senza scorte", "non disponibile", "non ordinabile", "in arrivo",
    "notifica", "preordine", "avísame", "avvisami", "épuisé", "prenota",
]
TERMINI_PREORDER = ["pre-order", "preorder", "pre order", "preventa", "preordine"]

LINGUE_DA_ESCLUDERE = [
    "italiano", "italian", "italienne", "español", "spanish", "espanol",
    "castellano", "francais", "french", "français", "deutsch", "german",
    "alemán", "chinese", "chino", "中文", "日本語", "japanese", "korean",
    "coreano", "portuguese", "portugués",
]

PAROLE_ESCLUSE = [
    "starter deck", "showdown deck", "champion deck", "champions deck",
    "5 buste", "5 packs", "blister", "vault", "proving grounds", "sanctum",
    "bundle", "playmat", "tapete", "tappetino", "sleeves", "fundas", "binder",
    "carpeta", "deck box", "portamazzi", "storage", "dice", "dados", "token",
    "poster", "album", "gift", "regalo", "single card", "carta singola",
]

RE_CASE = re.compile(
    r"\b(case|master ?case|master ?box|carton|cartone|caja master|caja nodriza)\b"
    r"|\b6 ?x\b|\bx ?6\b|\b6 (booster )?(box|boxes|display|displays)\b"
    r"|caja de 6|display de 6|expositor de 6|box da 6|espositore da 6|pack de 6",
    re.IGNORECASE,
)
RE_DISPLAY = re.compile(
    r"\b24\b|booster (box|display)|\bdisplay\b|caja de sobres|caja expositora"
    r"|box di bustine",
    re.IGNORECASE,
)

SEARCH_PATHS_PRESTA = [
    "/search?controller=search&s=riftbound",
    "/index.php?controller=search&s=riftbound",
    "/cerca?controller=search&s=riftbound",
    "/ricerca?controller=search&s=riftbound",
    "/buscar?controller=search&s=riftbound",
    "/busqueda?controller=search&s=riftbound",
]
SEARCH_PATHS = {
    "shopify": ["/search?q=riftbound&type=product"],
    "woocommerce": ["/?s=riftbound&post_type=product", "/?s=riftbound"],
    "prestashop": SEARCH_PATHS_PRESTA,
    "magento": ["/catalogsearch/result/?q=riftbound"],
}
SEARCH_PATHS_GENERIC = (
    ["/search?q=riftbound", "/?s=riftbound&post_type=product",
     "/catalogsearch/result/?q=riftbound"]
    + SEARCH_PATHS_PRESTA[:3]
    + ["/search.php?search_query=riftbound"]
)

NON_PRODUCT_PATH = [
    "/collections/", "/collection/", "/categoria", "/category", "/categories",
    "/tag/", "/marca", "/brand", "/search", "/blog/", "/pages/",
]

# --------------------------------------------------------------------------
# Lista completa dei Negozi (con link puliti alla home)
# --------------------------------------------------------------------------
STORES = {
    "Spagna": {
        "Factory Cards TCG": "https://factorycardstcg.com/",
        "TopDeck": "https://topdeck.es/",
        "Zial TCG": "https://www.zialtcg.com/",
        "Ninpo Store": "https://ninpostore.com/",
        "La Cueva Roja": "https://lacuevaroja.com/",
        "Magic Event GN": "https://www.magiceventgn.com/",
        "Ingenio BCN": "https://ingeniobcn.es/",
        "Monarka TCG": "https://monarkatcg.store/",
        "Padis Store": "https://www.padisl5r.com/",
        "Empire Games": "https://www.empiregames.es/",
        "Ateneo Comics": "https://www.ateneocomics.com/",
        "Nymeria Comics": "https://www.nymeriacomics.com/",
        "Tempest Store": "https://www.tempeststore.com/",
        "Paladin Store": "https://paladinstore.es/",
        "Pulsar Store": "https://pulsarstore.com/",
        "Manavortex": "https://manavortex.es/",
        "La Forja de Cartas": "https://www.laforjadecartas.com/",
        "La Escotilla Juegos": "https://laescotillajuegos.com/",
        "La Jugonzona": "https://www.lajugonzona.shop/",
        "Warlotus": "https://warlotus.com/",
        "TCG Mansion": "https://tcgmansion.com/",
        "TCG Factory": "https://tcgfactory.com/",
        "Panda Games": "https://pandagames.es/",
        "OZ Juegos": "https://www.ozjuegos.com/",
        "Hero Freaks": "https://www.herofreaks.com/",
        "HoloPlaza TCG": "https://holoplazatcg.com/",
        "AllInTCG": "https://allintcg.com/",
        "Dungeon Marvels": "https://dungeonmarvels.com/",
        "JJCollection": "https://www.jjcollection.es/",
        "Montalfan": "https://montalfan.com/",
        "El Duelista": "https://elduelista.com/",
        "Puerto Fantasy": "https://www.puertofantasy.es/",
        "Don Mazo": "https://www.donmazo.com/",
        "Madrid Norte TCG": "https://madridnortetcg.com/",
        "Shark Games": "https://sharkgames.es/",
        "Rebellion": "https://rebellion.es/",
        "TCG Parada": "https://www.tcgparada.com/",
        "TPK Hobby Games": "https://www.tpkhobby.es/",
        "Epic Hit Store": "https://www.epichitstore.es/",
        "Estalia Córdoba": "https://estaliacordoba.com/",
        "Metamorph Center": "https://metamorphcenter.com/",
        "Shiny Hit": "https://shinyhit.com/",
        "TCG Multiverse": "https://www.tcgmultiverse.es/",
        "Colossal Store": "https://www.colossalstore.es/",
        "El Orco Rojo": "https://www.elorcorojo.com/",
        "Generación X": "https://www.generacionx.es/",
        "Llibreria Kritik": "https://www.llibreriakritik.com/",
        "Lorcanos": "https://www.lorcanos.com/",
        "La Guarida Juegos": "https://laguaridajuegos.com/",
        "City of Cards": "https://cityof.cards/",
        "TCG Map Spain": "https://tcgmapspain.com/",
        "Isekai Alcorcón": "https://isekai-alcorcon.es/",
        "Velkarion": "https://velkarion.com/",
        "Zacatrus": "https://zacatrus.es/",
        "Metropolis Center": "https://metropolis-center.com/",
        "Gameria": "https://gameria.es/",
        "Super Collectors": "https://www.supercollectors.es/",
        "Dracotienda": "https://dracotienda.com/",
        "StarGeek": "https://www.stargeek.es/",
        "CardZone": "https://cardzone.es/",
        "Gigamesh": "https://gigamesh.com/",
        "Saruman Games": "https://sarumangames.es/",
        "Comic Stores": "https://comicstores.es/",
        "Kanto Cards": "https://kantocards.com/",
        "Pokemillon": "https://www.pokemillon.com/",
        "La Torre Karin Store": "https://latorrekarinstore.es/",
        "Ulduar": "https://www.ulduar.es/",
        "Imperio Friki": "https://imperiofriki.com/",
        "SunnyStore": "https://sunnystore.es/",
        "The Golden Rabbit Shop": "https://thegoldenrabbitshop.es/",
        "Otakuya TCG": "https://tcg.otakuya.es/",
        "Hyker Card House": "https://hykercardhouse.com/",
        "Grille Cards": "https://grillecards.com/",
        "TCG Level": "https://tcglevel.com/",
        "Wizard TCG": "https://www.wizardtcg.com/",
        "TCG Academy": "https://www.tcgacademy.es/",
        "Cosmic Blazar": "https://cosmicblazar.store/",
        "Origen Juegos": "https://www.origenjuegos.com/",
        "Three Stones Games": "https://threestonesgames.com/",
        "Universe TCG": "https://universetcg.es/",
        "GAME España": "https://www.game.es/",
        "Arte 9": "https://arte9.com/",
        "Troopertoys": "https://troopertoys.com/",
        "EGD Games": "https://egdgames.com/",
        "El Bastión del Sur": "https://www.elbastiondelsur.com/",
        "Card Center": "https://cardcenter.es/",
        "Friki Galaxy": "https://frikigalaxy.com/",
        "Card Crack": "https://cardcrack.com/",
        "Card Cosmos ES": "https://cardcosmos.es/",
    },
    "Italia": {
        "MOBA Store": "https://www.mobastore.it/",
        "OP SHOP": "https://opshop.it/",
        "Magic Store": "https://www.magicstore.it/",
        "iWozGaming": "https://iwozgaming.it/",
        "Golden Store Roma": "https://goldenstoreroma.it/",
        "Magliana Nerd": "https://www.magliananerd.it/",
        "Galactus": "https://galactus.it/",
        "Games Inn": "https://www.gamesinn.it/",
        "Games Time": "https://www.gamestime.it/",
        "Goblin Srl": "https://www.goblin.it/",
        "MagoMatto": "https://www.magomatto.com/",
        "Cards Capital City": "https://cardscapitalcity.it/",
        "Titan Gaming Center": "https://titangamingcenter.com/",
        "IL REGNO": "https://ilregno.it/",
        "ManaWeb": "https://manaweb.it/",
        "La Tana delle Pulci": "https://latanadellepulci.it/",
        "Dadi e Draghi": "https://www.dadiedraghi.com/",
        "Spazio Nerd": "https://spazionerd.it/",
        "Lost Legion": "https://lostlegion.it/",
        "B Games Bologna": "https://bgamesbologna.it/",
        "ONGAME": "https://ongame.it/",
        "Funside": "https://www.funside.it/",
        "Magicards": "https://magicards.it/",
        "Toon Kingdom": "https://toonkingdom.it/",
        "The Magic Spot": "https://themagicspot.it/",
        "Star Shop": "https://www.starshop.it/",
        "Firenze Comics and Games": "https://firenzecomicsandgames.it/",
        "Carta Magna": "https://cartamagna.it/",
        "The Realm": "https://therealm.it/",
        "La Gilda": "https://lagildadibusto.it/",
        "Dungeon Street": "https://dungeonstreet.it/",
        "4X Trading": "https://4xtrading.it/",
        "Il Covo del Nerd": "https://www.ilcovodelnerd.it/",
        "Pryce": "https://pryce.it/",
        "Teca Rara": "https://tecarara.it/",
        "Zero One": "https://zero-one.it/",
        "Anime Shop Italia": "https://animeshopitalia.it/",
        "Magic Merchant": "https://www.magicmerchant.it/",
        "Gameology": "https://www.gameology.it/",
        "Arcano Games": "https://www.arcanogames.it/",
        "Collector's Inn": "https://collectorsinn.it/",
        "Sanctum TCG": "https://sanctumtcg.it/",
        "TheManaShop": "https://themanashop.it/",
        "Games Time Aversa": "https://gamestimeaversa.com/",
        "Dadi e Mattoncini": "https://www.dadiemattoncini.it/",
        "Magictime": "https://magictime.it/",
        "CarteMagic": "https://www.cartemagic.com/",
        "Ziller Store": "https://www.zillerstore.it/",
        "MagicNerd": "https://magicnerd.it/",
        "1UP RM": "https://1uprm.com/",
        "Magic Store Shop": "https://www.magicstoreshop.com/",
        "ONY TCG": "https://www.onytcg.it/",
        "Pulla Store": "https://pullastore.it/",
        "TCG Store": "https://tcg-store.it/",
        "Collector Store Cards": "https://collectorstorecards.it/",
        "Il Collezionista Impertinente": "https://ilcollezionistaimpertinente.com/",
        "Vendiloshop": "https://www.vendiloshop.it/",
    },
}

# --------------------------------------------------------------------------
# Utilità
# --------------------------------------------------------------------------
def log(msg):
    if DEBUG:
        print(msg, flush=True)

_local = threading.local()

def _session():
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        retry = Retry(
            total=1, backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        s.headers.update(HEADERS)
        _local.s = s
    return s

def fetch(url, timeout=12):
    try:
        return _session().get(url, timeout=timeout, allow_redirects=True)
    except requests.RequestException as e:
        log(f"[net] {url} -> {type(e).__name__}")
        return None

def to_float(s):
    s = str(s).strip().replace("\xa0", "").replace(" ", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

RE_PRICE = re.compile(
    r"(\d[\d.,]*\d|\d)\s*(?:€|EUR)|(?:€|EUR)\s*(\d[\d.,]*\d|\d)", re.IGNORECASE
)

def estrai_prezzo(elemento):
    if not elemento:
        return None
    testo = elemento.get_text(" ")
    trovati = RE_PRICE.findall(testo)
    if not trovati:
        return None
    a, b = trovati[-1]
    return to_float(a or b)

def fmt_price(p):
    return f"{p:.2f} €".replace(".", ",") if p is not None else "prezzo n/d"

def es_pagina_prodotto(url):
    path = urlparse(url).path.lower()
    if "/products/" in path:
        return True
    return not any(x in path for x in NON_PRODUCT_PATH)

def classify(title, url):
    path = urlparse(url).path
    text = f"{title} {path}".lower().replace("-", " ").replace("_", " ")

    if "riftbound" not in text and "riftbound" not in url.lower():
        return None
    if any(s.lower() in text for s in FORBIDDEN_SETS):
        return None
    if any(lang in text for lang in LINGUE_DA_ESCLUDERE):
        return None
    if any(bad in text for bad in PAROLE_ESCLUSE):
        return None
    if any(t in text for t in TERMINI_PREORDER):
        return None

    matched = next((s for s in ALLOWED_SETS if s.lower() in text), None)
    if not matched:
        return None

    if RE_CASE.search(text):
        return matched, "case"
    if RE_DISPLAY.search(text):
        return matched, "display"
    return None

TIPO_LABEL = {"case": "CASE (6x Box)", "display": "BOOSTER BOX (24 Display)"}

def prezzo_plausibile(tipo, price):
    if price is None:
        return True
    return price >= MIN_PRICE[tipo]

def detect_platform(html):
    low = html.lower()
    if "cdn.shopify.com" in low or "myshopify.com" in low or "shopify.theme" in low:
        return "shopify"
    if "woocommerce" in low or "wp-content" in low:
        return "woocommerce"
    if "prestashop" in low or 'id="js-product-list' in low:
        return "prestashop"
    if "magento" in low or "mage/cookies" in low or "catalogsearch" in low:
        return "magento"
    return "generic"

def api_shopify(base):
    items = {}
    for q in QUERIES:
        url = (
            f"{base}/search/suggest.json?q={quote_plus(q)}"
            "&resources[type]=product&resources[limit]=10"
        )
        r = fetch(url)
        if r is None or r.status_code != 200:
            if r is not None and r.status_code in (404, 403):
                break
            continue
        try:
            prods = r.json()["resource_results"]["results"]["products"]
        except (ValueError, KeyError, TypeError):
            break
        for p in prods:
            link = urljoin(base, p.get("url", "")).split("?")[0]
            price = to_float(p["price"]) if p.get("price") else None
            items[link] = {
                "title": p.get("title", ""),
                "url": link,
                "in_stock": bool(p.get("available")),
                "price": price,
            }
    return list(items.values())

def api_woocommerce(base):
    url = f"{base}/wp-json/wc/store/v1/products?search=riftbound&per_page=100"
    r = fetch(url)
    if r is None or r.status_code != 200:
        return []
    try:
        data = r.json()
    except ValueError:
        return []
    if not isinstance(data, list):
        return []
    items = []
    for p in data:
        try:
            prices = p.get("prices", {}) or {}
            price = None
            if prices.get("price") and prices.get("currency_code", "EUR") == "EUR":
                price = int(prices["price"]) / (10 ** int(prices.get("currency_minor_unit", 2)))
            items.append({
                "title": htmllib.unescape(p.get("name", "")),
                "url": p.get("permalink", ""),
                "in_stock": bool(p.get("is_in_stock")) and bool(p.get("is_purchasable", True)),
                "price": price,
            })
        except (ValueError, TypeError):
            continue
    return items

def extract_from_html(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        link = urljoin(page_url, href).split("#")[0]
        if not link.startswith("http"):
            continue
        if "/products/" in link:
            link = link.split("?")[0]

        title = a.get_text(" ", strip=True) or a.get("title") or a.get("aria-label") or ""
        if not title:
            img = a.find("img")
            if img:
                title = img.get("alt") or ""
        slug = urlparse(link).path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")

        if "riftbound" not in (title + " " + link).lower():
            continue

        score = ("riftbound" in title.lower(), len(title))
        prev = out.get(link)
        if prev is None or score > prev["_score"]:
            out[link] = {
                "title": title or slug, "url": link,
                "in_stock": None, "price": None, "_score": score,
            }
    for it in out.values():
        it.pop("_score", None)
    return list(out.values())

def _norm_av(v):
    return str(v).lower().replace(" ", "").rsplit("/", 1)[-1]

def _jsonld_nodes(soup):
    nodes = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            n = stack.pop()
            if isinstance(n, dict):
                nodes.append(n)
                stack.extend(n.values())
            elif isinstance(n, list):
                stack.extend(n)
    return nodes

def _availability_values(soup, nodes):
    vals = [_norm_av(n["availability"]) for n in nodes if isinstance(n.get("availability"), str)]
    for m in soup.find_all("meta", attrs={"property": re.compile(r"availability$", re.I)}):
        if m.get("content"):
            vals.append(_norm_av(m["content"]))
    for m in soup.find_all(attrs={"itemprop": re.compile(r"^availability$", re.I)}):
        v = m.get("content") or m.get("href")
        if v:
            vals.append(_norm_av(v))
    return vals

def _price_from_page(soup, nodes):
    for n in nodes:
        p = n.get("price") or n.get("lowPrice")
        if p not in (None, ""):
            f = to_float(p)
            if f:
                return f
    for prop in ("product:price:amount", "og:price:amount"):
        m = soup.find("meta", attrs={"property": prop})
        if m and m.get("content"):
            f = to_float(m["content"])
            if f:
                return f
    el = soup.find(class_=re.compile("price", re.I))
    return estrai_prezzo(el)

def verifica_pagina(url):
    path = urlparse(url).path
    if "/products/" in path:
        p = urlparse(url)
        r = fetch(f"{p.scheme}://{p.netloc}{path.rstrip('/')}.js")
        if r is not None and r.status_code == 200:
            try:
                d = r.json()
            except ValueError:
                d = None
            if isinstance(d, dict) and "available" in d:
                blob = (d.get("title", "") + " " + " ".join(d.get("tags", []) or [])).lower()
                if any(t in blob for t in TERMINI_PREORDER):
                    return False, None, "shopify preorder"
                price = d.get("price")
                if isinstance(price, int):
                    price = price / 100
                elif isinstance(price, str):
                    price = to_float(price)
                return bool(d["available"]), price, "shopify.js"

    r = fetch(url)
    if r is None:
        return None, None, "rete"
    if r.status_code in (404, 410):
        return False, None, f"http {r.status_code}"
    if r.status_code != 200:
        return None, None, f"http {r.status_code}"

    soup = BeautifulSoup(r.text, "html.parser")
    nodes = _jsonld_nodes(soup)
    price = _price_from_page(soup, nodes)

    avail = _availability_values(soup, nodes)
    if avail:
        return any(a in IN_STOCK_SCHEMA for a in avail), price, f"schema {avail}"

    body_cls = " ".join(soup.body.get("class", [])).lower() if soup.body else ""
    if "outofstock" in body_cls or "out-of-stock" in body_cls:
        return False, price, "body class"

    form = (
        soup.find("form", action=re.compile(r"/cart/add|add-to-cart|add_to_cart", re.I))
        or soup.find("form", id=re.compile(r"addtocart|add-to-cart", re.I))
        or soup.find("form", class_=re.compile(r"^cart$|variations_form|product-form|add-to-cart", re.I))
    )
    if not form:
        return None, price, "nessun form di acquisto"

    btn = (
        form.find("button", attrs={"type": "submit"})
        or form.find("button")
        or form.find("input", attrs={"type": "submit"})
    )
    if not btn or btn.has_attr("disabled") or btn.get("aria-disabled") == "true":
        return False, price, "bottone assente/disabilitato"

    txt = (btn.get_text() or btn.get("value", "")).lower()
    if any(t in txt for t in TERMINI_ESAURITO):
        return False, price, f"bottone '{txt.strip()}'"
    return True, price, "bottone attivo"

def _merge(candidates, items):
    for it in items:
        if not it.get("url"):
            continue
        cur = candidates.get(it["url"])
        if cur is None:
            candidates[it["url"]] = dict(it)
            continue
        if cur["in_stock"] is None:
            cur["in_stock"] = it["in_stock"]
        if cur["price"] is None:
            cur["price"] = it["price"]
        if len(it["title"]) > len(cur["title"]):
            cur["title"] = it["title"]

def _has_classified(items):
    return any(classify(i["title"], i["url"]) for i in items)

def process_store(country, name, hint, cached):
    info = {"name": name, "country": country, "platform": "?", "status": "ok",
            "search_url": cached.get("search_url")}
    print(f"[*] {name}", flush=True)

    p = urlparse(hint)
    base = f"{p.scheme}://{p.netloc}"
    platform = "generic"

    home = fetch(base + "/")
    if home is None:
        if fetch(hint) is None:
            info["status"] = "DOMINIO MORTO"
            info["platform"] = "-"
            print(f"[x] {name}: dominio non raggiungibile", flush=True)
            return country, [], info
        info["status"] = "home non raggiungibile"
    elif home.status_code == 200:
        fp = urlparse(home.url)
        base = f"{fp.scheme}://{fp.netloc}"
        platform = detect_platform(home.text)
    else:
        info["status"] = f"home HTTP {home.status_code}"
    info["platform"] = platform

    candidates = {}

    if platform == "shopify":
        apis = [api_shopify]
    elif platform == "woocommerce":
        apis = [api_woocommerce]
    elif platform == "generic":
        apis = [api_shopify, api_woocommerce]
    else:
        apis = []
    for fn in apis:
        _merge(candidates, fn(base))

    priority = []
    if cached.get("search_url"):
        priority.append(cached["search_url"])
    if hint.rstrip("/") != base.rstrip("/"):
        priority.append(hint)
    
    # Genera automaticamente i path di ricerca in base alla piattaforma
    fallback = [base + path for path in SEARCH_PATHS.get(platform, [])]
    fallback += [base + path for path in SEARCH_PATHS_GENERIC]

    tried = set()
    working = None
    for url in priority + fallback:
        if url in tried:
            continue
        tried.add(url)
        is_fallback = url in fallback and url not in priority
        if is_fallback and _has_classified(candidates.values()):
            break
        r = fetch(url)
        if r is None or r.status_code != 200:
            continue
        items = extract_from_html(r.text, r.url)
        _merge(candidates, items)
        if _has_classified(items):
            working = url
            if is_fallback:
                break

    if working:
        info["search_url"] = working

    if not candidates and info["status"] == "ok":
        info["status"] = "nessun risultato Riftbound"

    found = []
    for it in candidates.values():
        cl = classify(it["title"], it["url"])
        if not cl:
            continue
        if not es_pagina_prodotto(it["url"]):
            continue
        if it["in_stock"] is False:
            continue

        set_name, tipo = cl
        stock, page_price, why = verifica_pagina(it["url"])
        if stock is None:
            stock = bool(it["in_stock"])
        if not stock:
            continue

        price = page_price if page_price is not None else it["price"]
        if not prezzo_plausibile(tipo, price):
            continue

        found.append({
            "store": name, "country": country, "url": it["url"],
            "set": set_name, "type": TIPO_LABEL[tipo],
            "title": it["title"], "price": price,
        })
    return country, found, info


def manda_notifica_telegram(testo):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Errore Telegram: Token o Chat ID mancanti.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": testo,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        data = res.json()
        if not data.get("ok"):
            print(f"[!] Errore Telegram API: {data.get('description')}")
            return False
        return True
    except Exception as e:
        print(f"[!] Errore connessione Telegram: {e}")
        return False


if __name__ == "__main__":
    print("=== Avvio scansione totale SPAGNA + ITALIA ===")
    
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass

    report_by_region = {}
    new_cache = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for country, stores in STORES.items():
            for name, hint in stores.items():
                futures[executor.submit(process_store, country, name, hint, cache.get(name, {}))] = name

        for future in as_completed(futures):
            country, available, info = future.result()
            if info.get("search_url"):
                new_cache[info["name"]] = {"search_url": info["search_url"]}
            if available:
                if country not in report_by_region:
                    report_by_region[country] = []
                report_by_region[country].extend(available)

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(new_cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    messaggio_telegram = "🚨 *RIFTBOUND ALERT: PRODOTTI DISPONIBILI!* 🚨\n\n"
    trovati_prodotti = False

    if report_by_region:
        for country, products in report_by_region.items():
            messaggio_telegram += f"📍 *{country}*\n"
            for prod in products:
                trovati_prodotti = True
                prezzo_str = fmt_price(prod['price'])
                messaggio_telegram += (
                    f"• [{prod['store']}]({prod['url']}) - *{prod['set']}* "
                    f"({prod['type']}) -> *{prezzo_str}*\n"
                )
            messaggio_telegram += "\n"

    if trovati_prodotti:
        inviato = manda_notifica_telegram(messaggio_telegram)
        if inviato:
            print("[OK] Prodotti trovati e notifica inviata su Telegram!")
        else:
            print("[!] Prodotti trovati ma invio Telegram FALLITO.")
    else:
        print("[INFO] Nessun prodotto disponibile in questo momento.")