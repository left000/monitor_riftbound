#!/usr/bin/env python3
"""Riftbound stock checker - Spagna + Italia.

Per ogni negozio:
  1. rileva la piattaforma (Shopify, WooCommerce, PrestaShop, Magento, altro)
  2. cerca i prodotti con l'API della piattaforma (se esiste) e/o con la
     pagina di ricerca HTML (prova automaticamente più URL possibili)
  3. filtra: solo Booster Box (24) e Case (6x) dei set ammessi, in inglese
  4. verifica lo stock sulla pagina del prodotto con PROVA POSITIVA
  5. manda su Telegram solo i prodotti realmente acquistabili

Variabili d'ambiente:
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   obbligatorie per le notifiche
  DEBUG=1                                log dettagliato dei motivi di scarto
  MAX_WORKERS=12                         negozi analizzati in parallelo
  NOTIFY_ONLY_NEW=1                      avvisa solo per prodotti nuovi
  STATE_FILE=state.json                  file di stato per NOTIFY_ONLY_NEW
  CACHE_FILE=stores_cache.json           cache degli URL di ricerca trovati
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

# Prezzi minimi plausibili (EUR): sotto questa soglia il prodotto è scartato
MIN_PRICE = {"display": 50.0, "case": 250.0}

QUERIES = ["riftbound booster box", "riftbound display", "riftbound case"]

IN_STOCK_SCHEMA = ("instock", "limitedavailability", "onlineonly")

# Testi (su bottoni o pagine) che indicano NON acquistabile adesso
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
    "/it/cerca?controller=search&s=riftbound",
    "/es/buscar?controller=search&s=riftbound",
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
    + SEARCH_PATHS_PRESTA[:5]
    + ["/search.php?search_query=riftbound"]
)

NON_PRODUCT_PATH = [
    "/collections/", "/collection/", "/categoria", "/category", "/categories",
    "/tag/", "/marca", "/brand", "/search", "/blog/", "/pages/",
]

# --------------------------------------------------------------------------
# Negozi. L'URL è solo un "suggerimento": lo script rileva da solo
# la piattaforma e prova più URL di ricerca. Per aggiungere un negozio
# basta una riga con la home (o la pagina collezione Riftbound).
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# Negozi VERIFICATI: ho trovato prodotti Riftbound (box/display) reali in
# vendita su questi siti con una ricerca web. Hanno la priorità.
# Basta la home: lo script rileva da solo piattaforma e URL di ricerca.
# --------------------------------------------------------------------------
STORES_VERIFICATI = {
    "Italia": {
        "CarteMagic": "https://www.cartemagic.com/",
        "Otakura": "https://otakura.com/",
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
    "Spagna": {
        "Universe TCG": "https://www.universetcg.com/",
        "Dungeon Marvels": "https://dungeonmarvels.com/",
        "Gigamesh": "https://gigamesh.com/",
        "La Escotilla Juegos": "https://laescotillajuegos.com/",
        "Micelion Games": "https://miceliongames.com/",
        "Manavortex": "https://manavortex.es/",
        "Gameria": "https://gameria.es/",
        "EGD Games": "https://egdgames.com/",
        "El Bastión del Sur": "https://www.elbastiondelsur.com/",
        "Card Center": "https://cardcenter.es/",
        "Friki Galaxy": "https://frikigalaxy.com/",
        "Card Crack": "https://cardcrack.com/",
        "Card Cosmos ES": "https://cardcosmos.es/",
    },
}

# --------------------------------------------------------------------------
# Negozi DA VERIFICARE (lista originale): molti domini potrebbero non
# esistere. Lo script li prova lo stesso, salta subito quelli morti e te li
# elenca nel report finale così puoi toglierli.
# --------------------------------------------------------------------------
STORES_DA_VERIFICARE = {
    "Spagna": {
        "Factory Cards TCG": "https://factorycardstcg.com/search?q=riftbound",
        "TopDeck": "https://topdeck.es/collections/all?q=riftbound",
        "Zial TCG": "https://www.zialtcg.com/?s=riftbound&post_type=product",
        "Ninpo Store": "https://ninpostore.com/search?q=riftbound",
        "La Cueva Roja": "https://lacuevaroja.com/?s=riftbound&post_type=product",
        "Magic Event GN": "https://www.magiceventgn.com/search?q=riftbound",
        "Ingenio BCN": "https://ingeniobcn.es/search?q=riftbound",
        "Monarka TCG": "https://monarkatcg.store/search?q=riftbound",
        "Padis Store": "https://www.padisl5r.com/en/443-riftbound-league-of-legends-tcg",
        "Empire Games": "https://www.empiregames.es/categoria-producto/juegos-de-cartas-coleccionables/league-of-legends-tcg-riftbound/",
        "Ateneo Comics": "https://www.ateneocomics.com/?s=riftbound&post_type=product",
        "Nymeria Comics": "https://www.nymeriacomics.com/?s=riftbound&post_type=product",
        "Tempest Store": "https://www.tempeststore.com/search?q=riftbound",
        "Paladin Store": "https://paladinstore.es/search?q=riftbound",
        "Pulsar Store": "https://pulsarstore.com/search?q=riftbound",
        "Manavortex": "https://manavortex.es/search?q=riftbound",
        "La Forja de Cartas": "https://www.laforjadecartas.com/?s=riftbound&post_type=product",
        "La Escotilla Juegos": "https://laescotillajuegos.com/?s=riftbound&post_type=product",
        "La Jugonzona": "https://www.lajugonzona.shop/search?q=riftbound",
        "Warlotus": "https://warlotus.com/search?q=riftbound",
        "TCG Mansion": "https://tcgmansion.com/search?q=riftbound",
        "TCG Factory": "https://tcgfactory.com/search?q=riftbound",
        "Panda Games": "https://pandagames.es/search?q=riftbound",
        "OZ Juegos": "https://www.ozjuegos.com/categoria-producto/juegos-de-cartas/riftbound-league-of-legends-tcg/",
        "Hero Freaks": "https://www.herofreaks.com/search?q=riftbound",
        "HoloPlaza TCG": "https://holoplazatcg.com/search?q=riftbound",
        "AllInTCG": "https://allintcg.com/search?q=riftbound",
        "Dungeon Marvels": "https://dungeonmarvels.com/catalogsearch/result/?q=riftbound",
        "JJCollection": "https://www.jjcollection.es/search?q=riftbound",
        "Montalfan": "https://montalfan.com/?s=riftbound&post_type=product",
        "El Duelista": "https://elduelista.com/search?q=riftbound",
        "Puerto Fantasy": "https://www.puertofantasy.es/?s=riftbound&post_type=product",
        "Don Mazo": "https://www.donmazo.com/?s=riftbound&post_type=product",
        "Madrid Norte TCG": "https://madridnortetcg.com/en/collections/riftbound-tcg",
        "Shark Games": "https://sharkgames.es/search?q=riftbound",
        "Rebellion": "https://rebellion.es/s?q=riftbound",
        "TCG Parada": "https://www.tcgparada.com/search?q=riftbound",
        "TPK Hobby Games": "https://www.tpkhobby.es/search?q=riftbound",
        "Epic Hit Store": "https://www.epichitstore.es/search?q=riftbound",
        "Estalia Córdoba": "https://estaliacordoba.com/?s=riftbound&post_type=product",
        "Metamorph Center": "https://metamorphcenter.com/search?q=riftbound",
        "Shiny Hit": "https://shinyhit.com/search?q=riftbound",
        "TCG Multiverse": "https://www.tcgmultiverse.es/search?q=riftbound",
        "Colossal Store": "https://www.colossalstore.es/search?q=riftbound",
        "El Orco Rojo": "https://www.elorcorojo.com/?s=riftbound&post_type=product",
        "Generación X": "https://www.generacionx.es/search?q=riftbound",
        "Llibreria Kritik": "https://www.llibreriakritik.com/?s=riftbound&post_type=product",
        "Lorcanos": "https://www.lorcanos.com/search?q=riftbound",
        "La Guarida Juegos": "https://laguaridajuegos.com/search?q=riftbound",
        "City of Cards": "https://cityof.cards/search?q=riftbound",
        "Isekai Alcorcón": "https://isekai-alcorcon.es/search?q=riftbound",
        "Velkarion": "https://velkarion.com/search?q=riftbound",
        "Zacatrus": "https://zacatrus.es/catalogsearch/result/?q=riftbound",
        "Metropolis Center": "https://metropolis-center.com/catalogsearch/result/?q=riftbound",
        "Gameria": "https://gameria.es/76-league-of-legends-riftbound",
        "Super Collectors": "https://www.supercollectors.es/search?q=riftbound",
        "Dracotienda": "https://dracotienda.com/catalogsearch/result/?q=riftbound",
        "StarGeek": "https://www.stargeek.es/search?q=riftbound",
        "CardZone": "https://cardzone.es/collections/riftbound-league-of-legends",
        "Gigamesh": "https://gigamesh.com/?s=riftbound&post_type=product",
        "Saruman Games": "https://sarumangames.es/search?q=riftbound",
        "Comic Stores": "https://comicstores.es/search?q=riftbound",
        "Kanto Cards": "https://kantocards.com/search?q=riftbound",
        "Pokemillon": "https://www.pokemillon.com/?s=riftbound&post_type=product",
        "La Torre Karin Store": "https://latorrekarinstore.es/",
        "Ulduar": "https://www.ulduar.es/?s=riftbound&post_type=product",
        "Imperio Friki": "https://imperiofriki.com/?s=riftbound&post_type=product",
        "SunnyStore": "https://sunnystore.es/search?q=riftbound",
        "The Golden Rabbit Shop": "https://thegoldenrabbitshop.es/categoria-producto/riftbound/",
        "Otakuya TCG": "https://tcg.otakuya.es/collections/tcg-de-riftbound",
        "Hyker Card House": "https://hykercardhouse.com/marca/riftbound/",
        "Grille Cards": "https://grillecards.com/search?q=riftbound",
        "TCG Level": "https://tcglevel.com/collections/riftbound",
        "Micelion Games": "https://miceliongames.com/product-category/juegos-tcg/",
        "Wizard TCG": "https://www.wizardtcg.com/collections/rifbound",
        "TCG Academy": "https://www.tcgacademy.es/riftbound/",
        "Cosmic Blazar": "https://cosmicblazar.store/catalogo?game=rift",
        "Origen Juegos": "https://www.origenjuegos.com/tienda/producto/riftbound-origins",
        "Three Stones Games": "https://threestonesgames.com/collections/riftbound",
        "Universe TCG": "https://universetcg.es/",
    },
    "Italia": {
        "MOBA Store": "https://www.mobastore.it/?s=riftbound&post_type=product",
        "OP SHOP": "https://opshop.it/?s=riftbound&post_type=product",
        "iWozGaming": "https://iwozgaming.it/?s=riftbound&post_type=product",
        "Golden Store Roma": "https://goldenstoreroma.it/?s=riftbound&post_type=product",
        "Magliana Nerd": "https://www.magliananerd.it/?s=riftbound&post_type=product",
        "Galactus": "https://galactus.it/?s=riftbound&post_type=product",
        "Games Inn": "https://www.gamesinn.it/?s=riftbound&post_type=product",
        "Games Time": "https://www.gamestime.it/?s=riftbound&post_type=product",
        "Goblin Srl": "https://www.goblin.it/?s=riftbound&post_type=product",
        "MagoMatto": "https://www.magomatto.com/?s=riftbound&post_type=product",
        "Cards Capital City": "https://cardscapitalcity.it/?s=riftbound&post_type=product",
        "Titan Gaming Center": "https://titangamingcenter.com/?s=riftbound&post_type=product",
        "IL REGNO": "https://ilregno.it/?s=riftbound&post_type=product",
        "ManaWeb": "https://manaweb.it/?s=riftbound&post_type=product",
        "La Tana delle Pulci": "https://latanadellepulci.it/?s=riftbound&post_type=product",
        "Dadi e Draghi": "https://www.dadiedraghi.com/?s=riftbound&post_type=product",
        "Spazio Nerd": "https://spazionerd.it/?s=riftbound&post_type=product",
        "Lost Legion": "https://lostlegion.it/?s=riftbound&post_type=product",
        "B Games Bologna": "https://bgamesbologna.it/?s=riftbound&post_type=product",
        "ONGAME": "https://ongame.it/?s=riftbound&post_type=product",
        "Funside": "https://www.funside.it/?s=riftbound&post_type=product",
        "Magicards": "https://magicards.it/?s=riftbound&post_type=product",
        "Toon Kingdom": "https://toonkingdom.it/?s=riftbound&post_type=product",
        "The Magic Spot": "https://themagicspot.it/?s=riftbound&post_type=product",
        "Star Shop": "https://www.starshop.it/?s=riftbound&post_type=product",
        "Firenze Comics and Games": "https://firenzecomicsandgames.it/?s=riftbound&post_type=product",
        "Carta Magna": "https://cartamagna.it/?s=riftbound&post_type=product",
        "The Realm": "https://therealm.it/?s=riftbound&post_type=product",
        "La Gilda": "https://lagildadibusto.it/?s=riftbound&post_type=product",
        "Dungeon Street": "https://dungeonstreet.it/?s=riftbound&post_type=product",
        "4X Trading": "https://4xtrading.it/?s=riftbound&post_type=product",
        "Il Covo del Nerd": "https://www.ilcovodelnerd.it/?s=riftbound&post_type=product",
        "Pryce": "https://pryce.it/?s=riftbound&post_type=product",
        "Teca Rara": "https://tecarara.it/?s=riftbound&post_type=product",
        "Zero One": "https://zero-one.it/?s=riftbound&post_type=product",
        "Anime Shop Italia": "https://animeshopitalia.it/?s=riftbound&post_type=product",
        "Magic Merchant": "https://www.magicmerchant.it/catalog/advanced_search_result.php?keywords=riftbound",
        "Gameology": "https://www.gameology.it/?s=riftbound&post_type=product",
        "Arcano Games": "https://www.arcanogames.it/?s=riftbound&post_type=product",
        "Collector's Inn": "https://collectorsinn.it/?s=riftbound&post_type=product",
        "Sanctum TCG": "https://sanctumtcg.it/?s=riftbound&post_type=product",
        "TheManaShop": "https://themanashop.it/?s=riftbound&post_type=product",
    },
}


def _build_all_stores():
    merged = {}
    for source in (STORES_VERIFICATI, STORES_DA_VERIFICARE):
        for country, stores in source.items():
            bucket = merged.setdefault(country, {})
            seen_domains = {urlparse(u).netloc.replace("www.", "") for u in bucket.values()}
            for name, url in stores.items():
                dom = urlparse(url).netloc.replace("www.", "")
                if dom in seen_domains:
                    continue  # stesso dominio già presente tra i verificati
                bucket[name] = url
                seen_domains.add(dom)
    return merged


ALL_STORES = _build_all_stores()


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


# --------------------------------------------------------------------------
# Classificazione dei prodotti (solo titolo + URL, mai il testo della pagina)
# --------------------------------------------------------------------------
def classify(title, url):
    """Ritorna (set, tipo) oppure None se il prodotto non interessa."""
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


# --------------------------------------------------------------------------
# Rilevamento piattaforma
# --------------------------------------------------------------------------
def detect_platform(html):
    low = html.lower()
    if "cdn.shopify.com" in low or "myshopify.com" in low or "shopify.theme" in low:
        return "shopify"
    if "woocommerce" in low:
        return "woocommerce"
    if "prestashop" in low or 'id="js-product-list' in low:
        return "prestashop"
    if "magento" in low or "mage/cookies" in low or "catalogsearch" in low:
        return "magento"
    if "wp-content" in low:
        return "woocommerce"
    return "generic"


# --------------------------------------------------------------------------
# Sorgenti di prodotti: API e HTML
# --------------------------------------------------------------------------
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


# --------------------------------------------------------------------------
# Verifica stock sulla pagina del prodotto (tri-state: True / False / None)
#   True  = prova positiva di disponibilità
#   False = prova esplicita di esaurito
#   None  = nessuna prova (es. pagina caricata via JavaScript)
# --------------------------------------------------------------------------
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

    # Shopify: endpoint .js con disponibilità e prezzo affidabili
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

    # 1) dati strutturati
    avail = _availability_values(soup, nodes)
    if avail:
        return any(a in IN_STOCK_SCHEMA for a in avail), price, f"schema {avail}"

    # 2) classi del body
    body_cls = " ".join(soup.body.get("class", [])).lower() if soup.body else ""
    if "outofstock" in body_cls or "out-of-stock" in body_cls:
        return False, price, "body class"

    # 3) form + bottone di acquisto reale
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


# --------------------------------------------------------------------------
# Analisi di un singolo negozio
# --------------------------------------------------------------------------
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
        # Nessuna risposta dalla home: provo anche l'URL indicato, se non
        # risponde nemmeno quello il dominio è morto -> niente altre richieste.
        if fetch(hint) is None:
            info["status"] = "DOMINIO MORTO (nessuna risposta di rete)"
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

    # --- API della piattaforma ---
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

    # --- Pagine HTML ---
    priority = []
    if cached.get("search_url"):
        priority.append(cached["search_url"])
    priority.append(hint)
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

    # --- Filtro e verifica stock ---
    found = []
    for it in candidates.values():
        cl = classify(it["title"], it["url"])
        if not cl:
            continue
        if not es_pagina_prodotto(it["url"]):
            log(f"[skip] {it['url']} -> non è una pagina prodotto")
            continue
        if it["in_stock"] is False:
            log(f"[skip] {it['url']} -> esaurito (API)")
            continue

        set_name, tipo = cl
        stock, page_price, why = verifica_pagina(it["url"])
        if stock is None:
            # senza prova dalla pagina, mi fido solo se l'API dice "disponibile"
            stock = bool(it["in_stock"])
            why += " -> uso dato API" if stock else " -> nessuna prova"
        log(f"[stock] {it['url']} -> {stock} ({why})")
        if not stock:
            continue

        price = page_price if page_price is not None else it["price"]
        if not prezzo_plausibile(tipo, price):
            log(f"[skip] {it['url']} -> prezzo implausibile {price}")
            continue

        found.append({
            "store": name, "country": country, "url": it["url"],
            "set": set_name, "type": TIPO_LABEL[tipo],
            "title": it["title"], "price": price,
        })
    return country, found, info


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------
def _invia_singolo(testo):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": testo,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        res = requests.post(url, json=payload, timeout=15)
        data = res.json()
        if not data.get("ok"):
            print(f"[!] Errore Telegram API: {data.get('description')}")
            return False
        return True
    except Exception as e:
        print(f"[!] Errore connessione Telegram: {e}")
        return False


def manda_notifica_telegram(righe):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Errore Telegram: Token o Chat ID mancanti.")
        return False
    chunks, current = [], ""
    for line in righe:
        if len(current) + len(line) + 1 > 3800:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return all([_invia_singolo(c) for c in chunks])


def _load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Impossibile salvare {path}: {e}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
def main():
    print("=== Avvio scansione SPAGNA + ITALIA ===", flush=True)
    cache = _load_json(CACHE_FILE, {})
    new_cache = dict(cache)

    all_found, infos = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = []
        for country, stores in ALL_STORES.items():
            for name, hint in stores.items():
                futures.append(
                    ex.submit(process_store, country, name, hint, cache.get(name, {}))
                )
        for fut in as_completed(futures):
            try:
                country, found, info = fut.result()
            except Exception as e:
                print(f"[!] Errore imprevisto: {e}")
                continue
            all_found.extend(found)
            infos.append(info)
            new_cache[info["name"]] = {
                "platform": info["platform"], "search_url": info["search_url"],
            }

    _save_json(CACHE_FILE, new_cache)

    # --- Report diagnostico (utile per capire quali negozi sistemare) ---
    morti = [i for i in infos if i["status"].startswith("DOMINIO MORTO")]
    ko = [i for i in infos if i["status"] != "ok" and i not in morti]
    print(f"\nNegozi analizzati: {len(infos)} | morti: {len(morti)} | con problemi: {len(ko)}")
    if morti:
        print("\nDomini morti (da togliere da ALL_STORES):")
        for i in sorted(morti, key=lambda x: x["name"]):
            print(f"  - {i['name']}")
        _save_json("negozi_morti.json", sorted(i["name"] for i in morti))
    if ko:
        print("\nNegozi con problemi:")
        for i in sorted(ko, key=lambda x: x["name"]):
            print(f"  - {i['name']} [{i['platform']}]: {i['status']}")

    # --- Solo nuovi? ---
    to_notify = all_found
    if NOTIFY_ONLY_NEW:
        prev = set(_load_json(STATE_FILE, []))
        to_notify = [p for p in all_found if p["url"] not in prev]
        _save_json(STATE_FILE, sorted({p["url"] for p in all_found}))

    print(f"\nProdotti disponibili: {len(all_found)} (da notificare: {len(to_notify)})")
    for p in all_found:
        print(f"  [TROVATO] {p['store']} | {p['set']} | {p['type']} | {fmt_price(p['price'])}\n      {p['url']}")

    if not to_notify:
        print("[INFO] Nessun prodotto da notificare.")
        return

    righe = ["🚨 <b>RIFTBOUND ALERT: PRODOTTI DISPONIBILI!</b> 🚨", ""]
    for country in ALL_STORES:
        prods = sorted([p for p in to_notify if p["country"] == country],
                       key=lambda x: (x["store"], x["set"]))
        if not prods:
            continue
        righe.append(f"📍 <b>{htmllib.escape(country)}</b>")
        for p in prods:
            righe.append(
                f"• <a href=\"{htmllib.escape(p['url'], quote=True)}\">"
                f"{htmllib.escape(p['store'])}</a> - <b>{htmllib.escape(p['set'])}</b> "
                f"({htmllib.escape(p['type'])}) → <b>{htmllib.escape(fmt_price(p['price']))}</b>"
            )
        righe.append("")

    if manda_notifica_telegram(righe):
        print("[OK] Notifica inviata su Telegram!")
    else:
        print("[!] Prodotti trovati ma invio Telegram FALLITO.")


if __name__ == "__main__":
    main()