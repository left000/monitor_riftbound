from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# Metti DEBUG=1 nelle variabili d'ambiente per vedere perché i prodotti vengono scartati
DEBUG = os.environ.get("DEBUG") == "1"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,it-IT,it;q=0.8,en-US,en;q=0.7",
}

ALLOWED_SETS = ["Origins", "Spiritforged", "Unleashed", "Vendetta"]
FORBIDDEN_SETS = ["Radiance"]

# Valori schema.org che indicano un prodotto acquistabile
IN_STOCK_SCHEMA = ("instock", "limitedavailability", "onlineonly")

TERMINI_ESAURITO = [
    "agotado",
    "agotados",
    "sold out",
    "sin stock",
    "no disponible",
    "out of stock",
    "unavailable",
    "sin existencias",
    "existencias insuficientes",
    "insuficientes",
    "proximamente",
    "próximamente",
    "coming soon",
    "reservar",
    "reserva",
    "pre-order",
    "preorder",
    "preventa",
    "reposición",
    "esaurito",
    "esauriti",
    "senza scorte",
    "non disponibile",
    "non ordinabile",
    "in arrivo",
    "notifica",
    "preordine",
    "avísame",
    "avvisami",
    "épuisé",
]

LINGUE_DA_ESCLUDERE = [
    "italiano",
    "italian",
    "italienne",
    "español",
    "spanish",
    "espanol",
    "castellano",
    "francais",
    "french",
    "français",
    "deutsch",
    "german",
    "alemán",
    "chinese",
    "chino",
    "中文",
    "日本語",
    "japanese",
]

PAROLE_ESCLUSE = [
    "starter deck",
    "showdown deck",
    "champion deck",
    "5 buste",
    "5 packs",
    "blister",
    "vault",
    "proving grounds",
    "sanctum",
    "bundle",
]

RE_CASE = re.compile(
    r"\b(case|6x|x6|master ?case|masterbox|carton|cartone)\b"
    r"|caja de 6|caja master|caja nodriza|display de 6|expositor de 6"
    r"|box da 6|espositore da 6|pack de 6|6 booster box",
    re.IGNORECASE,
)
RE_DISPLAY_24 = re.compile(
    r"\b24\b|booster (box|display)|display|caja de sobres|caja expositora"
    r"|box di bustine",
    re.IGNORECASE,
)

ALL_STORES = {
    "Spagna - Negozi & Specializzati": {
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
        "TCG Map Spain": "https://tcgmapspain.com/",
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
        "Riot Games Merch": "https://merch.riotgames.com/",
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
    },
    "Italia - Negozi & Specializzati": {
        "MOBA Store": "https://www.mobastore.it/?s=riftbound&post_type=product",
        "OP SHOP": "https://opshop.it/?s=riftbound&post_type=product",
        "Magic Store": "https://www.magicstore.it/?s=riftbound&post_type=product",
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


def log(msg):
    if DEBUG:
        print(msg)


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------
def _invia_singolo(testo):
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


def manda_notifica_telegram(testo):
    """Invia il messaggio spezzandolo se supera il limite di 4096 caratteri."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] Errore Telegram: Token o Chat ID mancanti.")
        return False

    chunks, current = [], ""
    for line in testo.split("\n"):
        if len(current) + len(line) + 1 > 3800:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)

    return all([_invia_singolo(c) for c in chunks])


# --------------------------------------------------------------------------
# Prezzo e disponibilità
# --------------------------------------------------------------------------
def estrai_prezzo_pulito(elemento_html):
    if not elemento_html:
        return "N/D"
    testo = elemento_html.get_text(" ")
    prezzi = re.findall(
        r"(?:€\s*\d+[\.,]?\d*|\d+[\.,]?\d*\s*€|\d+[\.,]?\d*\s*EUR)",
        testo,
        re.IGNORECASE,
    )
    if prezzi:
        return prezzi[-1].strip()
    return "N/D"


def _walk_jsonld(soup):
    """Restituisce tutti i nodi dict presenti nei JSON-LD della pagina."""
    nodes = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                nodes.append(node)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
    return nodes


def _norm_availability(value):
    return str(value).lower().replace(" ", "").rsplit("/", 1)[-1]


def _availability_values(soup):
    values = []
    for node in _walk_jsonld(soup):
        av = node.get("availability")
        if isinstance(av, str):
            values.append(_norm_availability(av))
    for meta in soup.find_all(
        "meta", attrs={"property": re.compile(r"availability$", re.I)}
    ):
        if meta.get("content"):
            values.append(_norm_availability(meta["content"]))
    for meta in soup.find_all(
        "meta", attrs={"itemprop": re.compile(r"^availability$", re.I)}
    ):
        if meta.get("content"):
            values.append(_norm_availability(meta["content"]))
    for link in soup.find_all("link", attrs={"itemprop": "availability"}):
        if link.get("href"):
            values.append(_norm_availability(link["href"]))
    return values


def _price_from_jsonld(soup):
    for node in _walk_jsonld(soup):
        price = node.get("price") or node.get("lowPrice")
        if price not in (None, ""):
            try:
                return f"{float(str(price).replace(',', '.')):.2f} €"
            except ValueError:
                continue
    return None


def verifica_disponibilita_prodotto_reale(product_url):
    """Apre la pagina prodotto. Segnala disponibile SOLO con prova positiva."""
    try:
        res = requests.get(product_url, headers=HEADERS, timeout=8)
        if res.status_code != 200:
            log(f"[stock] {product_url} -> HTTP {res.status_code}")
            return False, "N/D"

        soup = BeautifulSoup(res.text, "html.parser")

        # 1) Dati strutturati: i più affidabili
        avail = _availability_values(soup)
        if avail:
            in_stock = any(a in IN_STOCK_SCHEMA for a in avail)
            log(f"[stock] {product_url} -> schema avail={avail} -> {in_stock}")
        else:
            # 2) Fallback: classi del body + form/bottone di acquisto reale
            body_cls = (
                " ".join(soup.body.get("class", [])).lower() if soup.body else ""
            )
            if "outofstock" in body_cls or "out-of-stock" in body_cls:
                log(f"[stock] {product_url} -> body class esaurito")
                return False, "N/D"

            form = (
                soup.find(
                    "form",
                    action=re.compile(r"/cart/add|add-to-cart|add_to_cart", re.I),
                )
                or soup.find(
                    "form", id=re.compile(r"addtocart|add-to-cart|product", re.I)
                )
                or soup.find(
                    "form",
                    class_=re.compile(
                        r"^cart$|\bcart\b.*\bvariations|variations_form|product-form|add-to-cart",
                        re.I,
                    ),
                )
            )
            if not form:
                log(f"[stock] {product_url} -> nessun form di acquisto")
                return False, "N/D"

            btn = (
                form.find("button", attrs={"type": "submit"})
                or form.find("button")
                or form.find("input", attrs={"type": "submit"})
            )
            if (
                not btn
                or btn.has_attr("disabled")
                or btn.get("aria-disabled") == "true"
            ):
                log(f"[stock] {product_url} -> bottone assente/disabilitato")
                return False, "N/D"

            txt = (btn.get_text() or btn.get("value", "")).lower()
            in_stock = not any(t in txt for t in TERMINI_ESAURITO)
            log(f"[stock] {product_url} -> bottone '{txt.strip()}' -> {in_stock}")

        if not in_stock:
            return False, "N/D"

        price = _price_from_jsonld(soup)
        if not price:
            price_elem = soup.find(class_=re.compile("price", re.I))
            price = estrai_prezzo_pulito(price_elem) if price_elem else "N/D"
        return True, price
    except Exception as e:
        log(f"[stock] {product_url} -> errore {e}")
        return False, "N/D"


# --------------------------------------------------------------------------
# Scansione dello store
# --------------------------------------------------------------------------
def check_store_stock(store_name, url):
    print(f"[*] Analizzando store ({store_name}) -> {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        found_products = []
        seen_urls = set()

        # Parto dai link: ogni link con titolo è un candidato prodotto.
        # In questo modo titolo, link e contenitore corrispondono sempre.
        for a in soup.find_all("a", href=True):
            product_title = a.get_text(" ", strip=True)
            if not product_title:
                # molti temi mettono il titolo nell'attributo title
                product_title = (a.get("title") or "").strip()
            if not product_title:
                continue

            product_link = urljoin(url, a["href"]).split("#")[0]
            if not product_link.startswith("http") or product_link in seen_urls:
                continue

            title_lower = product_title.lower()
            search_text = title_lower + " " + product_link.lower()

            if "riftbound" not in search_text:
                continue

            if any(f.lower() in search_text for f in FORBIDDEN_SETS):
                continue
            if any(lang in search_text for lang in LINGUE_DA_ESCLUDERE):
                continue
            if any(bad in search_text for bad in PAROLE_ESCLUSE):
                continue

            matched_set = next(
                (s for s in ALLOWED_SETS if s.lower() in search_text), None
            )
            if not matched_set:
                continue

            if RE_CASE.search(search_text):
                product_type = "CASE (6x Box)"
            elif RE_DISPLAY_24.search(search_text):
                product_type = "BOOSTER BOX (24 Display)"
            else:
                continue

            seen_urls.add(product_link)

            # Verifica approfondita sulla pagina del prodotto
            in_stock, real_price = verifica_disponibilita_prodotto_reale(
                product_link
            )
            if not in_stock:
                continue

            if real_price == "N/D":
                # provo il prezzo dell'anteprima, nel contenitore più vicino
                container = a.find_parent(["li", "article", "div"])
                if container:
                    price_elem = container.find(
                        class_=re.compile("price", re.I)
                    )
                    real_price = estrai_prezzo_pulito(price_elem)

            if real_price == "N/D":
                log(f"[skip] {product_link} -> prezzo non trovato")
                continue

            found_products.append(
                {
                    "store": store_name,
                    "url": product_link,
                    "set": matched_set,
                    "type": product_type,
                    "title": product_title,
                    "price": real_price,
                    "status": "DISPONIBILE",
                }
            )

        return found_products
    except Exception as e:
        log(f"[!] {store_name}: errore {e}")
        return []


def process_store(region, store_name, store_url):
    results = check_store_stock(store_name, store_url)
    available = [p for p in results if "DISPONIBILE" in p["status"]]
    return region, available


if __name__ == "__main__":
    print("=== Avvio scansione totale SPAGNA + ITALIA ===")
    report_by_region = {}

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = []
        for region, stores in ALL_STORES.items():
            for store_name, store_url in stores.items():
                futures.append(
                    executor.submit(process_store, region, store_name, store_url)
                )

        for future in as_completed(futures):
            region, available = future.result()
            if available:
                report_by_region.setdefault(region, []).extend(available)

    messaggio_telegram = "🚨 *RIFTBOUND ALERT: PRODOTTI DISPONIBILI!* 🚨\n\n"
    trovati_prodotti = False

    for region, products in report_by_region.items():
        messaggio_telegram += f"📍 *{region}*\n"
        for prod in products:
            trovati_prodotti = True
            messaggio_telegram += (
                f"• [{prod['store']}]({prod['url']}) - *{prod['set']}* "
                f"({prod['type']}) -> *{prod['price']}*\n"
            )
        messaggio_telegram += "\n"

    if trovati_prodotti:
        if manda_notifica_telegram(messaggio_telegram):
            print("[OK] Prodotti trovati e notifica inviata su Telegram!")
        else:
            print("[!] Prodotti trovati ma invio Telegram FALLITO.")
    else:
        print("[INFO] Nessun prodotto disponibile in questo momento.")