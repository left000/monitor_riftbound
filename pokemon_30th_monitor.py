#!/usr/bin/env python3
"""Pokémon 30th Anniversary stock checker - Spagna + Italia.

Script separato e indipendente per il monitoraggio dei prodotti
del 30° Anniversario Pokémon (box, collezioni, display) sui negozi IT/ES.
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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN_POKEMON") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID_POKEMON") or os.environ.get("TELEGRAM_CHAT_ID")
DEBUG = os.environ.get("DEBUG") == "1"
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "12"))
CACHE_FILE = os.environ.get("CACHE_FILE_PKM", "pokemon_stores_cache.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,it-IT,it;q=0.8,en-US,en;q=0.7",
}

# Parole chiave per intercettare il 30th anniversario Pokémon
ALLOWED_KEYWORDS = [
    "30th", "30 anniversary", "30 aniversario", "30 anniversario", 
    "anniversary collection", "celebrations", "celebration"
]

MIN_PRICE = 15.0  # Soglia minima di prezzo plausibile in EUR
QUERIES = ["pokemon 30th", "pokemon anniversary", "pokemon celebrations"]
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

PAROLE_ESCLUSE = [
    "playmat", "tapete", "tappetino", "sleeves", "fundas", "binder",
    "carpeta", "deck box", "portamazzi", "storage", "dice", "dados", "token",
    "poster", "album", "gift", "regalo",
]

NON_PRODUCT_PATH = [
    "/collections/", "/collection/", "/categoria", "/category", "/categories",
    "/tag/", "/marca", "/brand", "/search", "/blog/", "/pages/",
]

# --------------------------------------------------------------------------
# Lista completa dei Negozi (Spagna + Italia)
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
# Funzioni Utility
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
    except requests.RequestException:
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

def classify_pokemon(title, url):
    path = urlparse(url).path
    text = f"{title} {path}".lower().replace("-", " ").replace("_", " ")

    if "pokemon" not in text and "pokémon" not in text:
        return None
    if not any(kw in text for kw in ALLOWED_KEYWORDS):
        return None
    if any(bad in text for bad in PAROLE_ESCLUSE):
        return None
    if any(t in text for t in TERMINI_PREORDER):
        return None

    return "Pokémon 30th Anniversary"

def detect_platform(html):
    low = html.lower()
    if "cdn.shopify.com" in low or "myshopify.com" in low:
        return "shopify"
    if "woocommerce" in low or "wp-content" in low:
        return "woocommerce"
    return "generic"

def api_shopify(base):
    items = {}
    for q in QUERIES:
        url = f"{base}/search/suggest.json?q={quote_plus(q)}&resources[type]=product&resources[limit]=10"
        r = fetch(url)
        if r is None or r.status_code != 200:
            continue
        try:
            prods = r.json()["resource_results"]["results"]["products"]
        except Exception:
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
    url = f"{base}/wp-json/wc/store/v1/products?search=pokemon&per_page=50"
    r = fetch(url)
    if r is None or r.status_code != 200:
        return []
    try:
        data = r.json()
    except Exception:
        return []
    items = []
    for p in data:
        try:
            prices = p.get("prices", {}) or {}
            price = None
            if prices.get("price"):
                price = int(prices["price"]) / 100
            items.append({
                "title": htmllib.unescape(p.get("name", "")),
                "url": p.get("permalink", ""),
                "in_stock": bool(p.get("is_in_stock")),
                "price": price,
            })
        except Exception:
            continue
    return items

def extract_from_html(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    for a in soup.find_all("a", href=True):
        link = urljoin(page_url, a["href"]).split("#")[0]
        title = a.get_text(" ", strip=True) or a.get("title") or ""
        if "pokemon" not in (title + " " + link).lower():
            continue
        out[link] = {"title": title, "url": link, "in_stock": None, "price": None}
    return list(out.values())

def verifica_pagina(url):
    r = fetch(url)
    if r is None or r.status_code != 200:
        return None, None, "rete/http"
    soup = BeautifulSoup(r.text, "html.parser")
    
    # Controllo esaurito approfondito sulla singola pagina
    full_text = soup.get_text().lower()
    if any(t in full_text for t in TERMINI_ESAURITO):
        form = soup.find("form", action=re.compile(r"cart/add|add-to-cart", re.I))
        if not form:
            return False, None, "testo esaurito"
            
    el = soup.find(class_=re.compile("price", re.I))
    price = estrai_prezzo(el)
    return True, price, "ok"

def process_store(country, name, hint, cached):
    info = {"name": name, "country": country, "status": "ok"}
    p = urlparse(hint)
    base = f"{p.scheme}://{p.netloc}"
    
    candidates = {}
    home = fetch(base + "/")
    platform = detect_platform(home.text) if home and home.status_code == 200 else "generic"

    if platform == "shopify":
        for item in api_shopify(base):
            candidates[item["url"]] = item
    elif platform == "woocommerce":
        for item in api_woocommerce(base):
            candidates[item["url"]] = item

    found = []
    for it in candidates.values():
        if not classify_pokemon(it["title"], it["url"]):
            continue
        stock, page_price, _ = verifica_pagina(it["url"])
        if not stock:
            continue
        price = page_price if page_price else it["price"]
        if price and price < MIN_PRICE:
            continue
            
        found.append({
            "store": name, "country": country, "url": it["url"],
            "set": "30th Anniversary", "title": it["title"], "price": price,
        })
    return country, found, info

def manda_notifica_telegram(testo):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        res = requests.post(url, json=payload, timeout=10)
        return res.json().get("ok", False)
    except Exception:
        return False

if __name__ == "__main__":
    print("=== Avvio scansione Pokémon 30th Anniversary (Spagna + Italia) ===")
    report_by_region = {}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_store, c, name, hint, {}): name for c, stores in STORES.items() for name, hint in stores.items()}
        for future in as_completed(futures):
            country, available, _ = future.result()
            if available:
                report_by_region.setdefault(country, []).extend(available)

    msg = "⚡ *POKÉMON 30TH ANNIVERSARY ALERT!* ⚡\n\n"
    has_items = False
    for country, prods in report_by_region.items():
        msg += f"📍 *{country}*\n"
        for p in prods:
            has_items = True
            msg += f"• [{p['store']}]({p['url']}) - *{p['title']}* -> *{fmt_price(p['price'])}*\n"
        msg += "\n"

    if has_items:
        manda_notifica_telegram(msg)
        print("[OK] Notifica Pokémon inviata!")
    else:
        print("[INFO] Nessun prodotto del 30° anniversario disponibile.")