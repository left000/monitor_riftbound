from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import re
import time
from bs4 import BeautifulSoup
import requests

# Legge i token segreti dall'ambiente di GitHub Actions
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, "
        "like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,it-IT,it;q=0.8,en-US,en;q=0.7",
}

ALLOWED_SETS = ["Origins", "Spiritforged", "Unleashed", "Vendetta"]
FORBIDDEN_SETS = ["Radiance"]

PRODUCT_KEYWORDS = {
    "case": [
        "case",
        "6x",
        "6 booster box",
        "display case",
        "caja de 6",
        "carton",
        "x6",
        "master case",
        "caja nodriza",
        "expositor de 6",
        "masterbox",
        "caja master",
        "pack de 6",
        "6x booster",
        "sealed case",
        "caja de 6 unidades",
        "display de 6",
        "cartone",
        "box da 6",
        "espositore da 6",
    ],
    "display_24": [
        "24",
        "booster display",
        "booster box",
        "slim booster box",
        "caja de sobres",
        "caja expositora",
        "display de 24",
        "box 24",
        "caja suelta",
        "booster pack box",
        "caja de 24",
        "expositor de 24",
        "display box",
        "box di bustine",
        "display da 24",
    ],
}

TERMINI_ESAURITO = [
    "agotado",
    "agotados",
    "sold out",
    "sin stock",
    "no disponible",
    "out of stock",
    "sin existencias",
    "proximamente",
    "próximamente",
    "coming soon",
    "reservar",
    "reserva",
    "pre-order",
    "preventa",
    "reposición",
    "esaurito",
    "esauriti",
    "senza scorte",
    "non disponibile",
    "in arrivo",
    "notifica",
    "preordine",
]

ALL_STORES = {
    "Spagna - Negozi & Specializzati": {
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
        "Dungeon Marvels": "https://www.dungeonmarvels.com/",
        "JJCollection": "https://www.jjcollection.es/",
        "Montalfan": "https://montalfan.com/",
        "El Duelista": "https://www.elduelista.com/",
        "Puerto Fantasy": "https://www.puertofantasy.es/",
        "Don Mazo": "https://www.donmazo.com/",
        "Madrid Norte TCG": "https://madridnortetcg.com/",
        "Shark Games": "https://sharkgames.es/",
        "Rebellion": "https://rebellion.es/",
        "TCG Parada": "https://www.tcgparada.com/",
        "TPK Hobby Games": "https://www.tpkhobbygames.com/",
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
        "Riot Games Merch": "https://merch.riotgames.com/",
        "The Golden Rabbit Shop": (
            "https://thegoldenrabbitshop.es/categoria-producto/riftbound/"
        ),
        "Otakuya TCG": "https://tcg.otakuya.es/collections/tcg-de-riftbound",
        "Hyker Card House": "https://hykercardhouse.com/marca/riftbound/",
        "Grille Cards": "https://grillecards.com/",
        "TCG Level": "https://tcglevel.com/collections/riftbound",
        "Micelion Games": (
            "https://miceliongames.com/product-category/juegos-tcg/"
        ),
        "Wizard TCG": "https://www.wizardtcg.com/collections/rifbound",
        "TCG Academy": "https://www.tcgacademy.es/riftbound/",
        "Cosmic Blazar": "https://cosmicblazar.store/catalogo?game=rift",
        "Origen Juegos": (
            "https://www.origenjuegos.com/tienda/producto/riftbound-origins"
        ),
        "Three Stones Games": (
            "https://threestonesgames.com/collections/riftbound"
        ),
    },
    "Italia - Negozi & Specializzati": {
        "MOBA Store": "https://www.mobastore.it",
        "OP SHOP": "https://opshop.it",
        "Magic Store": "https://www.magicstore.it",
        "iWozGaming": "https://iwozgaming.it",
        "Golden Store Roma": "https://goldenstoreroma.it",
        "Magliana Nerd": "https://www.magliananerd.it",
        "Galactus": "https://galactus.it",
        "Games Inn": "https://www.gamesinn.it",
        "Games Time": "https://www.gamestime.it",
        "Goblin Srl": "https://www.goblin.it",
        "MagoMatto": "https://www.magomatto.com",
        "Cards Capital City": "https://cardscapitalcity.it",
        "Titan Gaming Center": "https://titangamingcenter.com",
        "IL REGNO": "https://ilregno.it",
        "ManaWeb": "https://manaweb.it",
        "La Tana delle Pulci": "https://latanadellepulci.it",
        "Dadi e Draghi": "https://www.dadiedraghi.com",
        "Spazio Nerd": "https://spazionerd.it",
        "Lost Legion": "https://lostlegion.it",
        "B Games Bologna": "https://bgamesbologna.it",
        "ONGAME": "https://ongame.it",
        "Funside": "https://www.funside.it",
        "Magicards": "https://magicards.it",
        "Toon Kingdom": "https://toonkingdom.it",
        "The Magic Spot": "https://themagicspot.it",
        "Star Shop": "https://www.starshop.it",
        "Firenze Comics and Games": "https://firenzecomicsandgames.it",
        "Carta Magna": "https://cartamagna.it",
        "The Realm": "https://therealm.it",
        "La Gilda": "https://lagildadibusto.it",
        "Dungeon Street": "https://dungeonstreet.it",
        "4X Trading": "https://4xtrading.it",
        "Il Covo del Nerd": "https://www.ilcovodelnerd.it",
        "Pryce": "https://pryce.it",
        "Teca Rara": "https://tecarara.it",
        "Zero One": "https://zero-one.it",
        "Anime Shop Italia": "https://animeshopitalia.it",
        "Magic Merchant": "https://www.magicmerchant.it",
        "Gameology": "https://www.gameology.it",
        "Arcano Games": "https://www.arcanogames.it",
        "Collector's Inn": "https://collectorsinn.it",
        "Sanctum TCG": "https://sanctumtcg.it",
        "TheManaShop": "https://themanashop.it",
    },
}


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


def estrai_prezzo_pulito(elemento_html):
  if not elemento_html:
    return "N/D"
  testo = elemento_html.get_text()
  prezzi = re.findall(
      r"(?:€\s*\d+[\.,]?\d*|\d+[\.,]?\d*\s*€|\d+[\.,]?\d*\s*EUR)",
      testo,
      re.IGNORECASE,
  )
  if prezzi:
    return prezzi[-1].strip()
  return "N/D"


def check_store_stock(store_name, url):
  print(f"[*] Analizzando store ({store_name}) -> {url}")
  try:
    response = requests.get(url, headers=HEADERS, timeout=10)
    if response.status_code != 200:
      return []

    html = response.text
    soup = BeautifulSoup(html, "html.parser")
    found_products = []
    seen_urls = set()

    product_items = soup.find_all(
        ["div", "li", "article"],
        class_=lambda x: x
        and any(
            term in x.lower()
            for term in ["product", "item", "card", "grid", "prodotto"]
        ),
    )
    if not product_items:
      product_items = soup.find_all(
          "div",
          class_=lambda x: x and ("col" in x.lower() or "box" in x.lower()),
      )

    for item in product_items:
      title_elem = item.find(
          ["h2", "h3", "a"],
          class_=lambda x: x
          and (
              "title" in x.lower()
              or "name" in x.lower()
              or "prodotto" in x.lower()
          ),
      )
      if not title_elem:
        title_elem = item.find("a")

      if not title_elem:
        continue

      product_title = title_elem.get_text(strip=True)
      product_link = (
          title_elem.get("href", "")
          if title_elem.name == "a"
          else (item.find("a")["href"] if item.find("a") else "")
      )

      if product_link and product_link.startswith("/"):
        base_url = "/".join(url.split("/")[:3])
        product_link = base_url + product_link

      if not product_link or product_link in seen_urls:
        continue

      title_lower = product_title.lower()
      item_text = item.get_text().lower()

      if "riftbound" not in title_lower and "riftbound" not in item_text:
        continue

      if any(
          f in title_lower or f in item_text
          for f in [r.lower() for r in FORBIDDEN_SETS]
      ):
        continue

      # Esclusione rigida di altre lingue
      lingue_da_escludere = [
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
      if any(
          lang in title_lower or lang in item_text
          for lang in lingue_da_escludere
      ):
        continue

      if any(
          bad in title_lower
          for bad in [
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
      ):
        continue

      matched_set = None
      full_search_text = title_lower + " " + item_text
      for s in ALLOWED_SETS:
        if s.lower() in full_search_text:
          matched_set = s
          break

      if not matched_set:
        continue

      is_case = any(
          term in full_search_text for term in PRODUCT_KEYWORDS["case"]
      )
      is_display_24 = any(
          term in full_search_text for term in PRODUCT_KEYWORDS["display_24"]
      )

      if is_case:
        product_type = "CASE (6x Box)"
      elif is_display_24:
        product_type = "BOOSTER BOX (24 Display)"
      else:
        continue

      # --- CONTROLLO ESAURITO MIGLIORATO ---
      is_exhausted = any(term in item_text for term in TERMINI_ESAURITO)

      # Controlla tutti i bottoni/pulsanti all'interno dell'articolo per attributi "disabled" o testi esauriti
      buttons = item.find_all(["button", "input", "a"])
      for btn in buttons:
        btn_txt = btn.get_text().lower()
        if btn.has_attr("disabled") or any(
            t in btn_txt
            for t in [
                "agotado",
                "esaurito",
                "sold out",
                "avísame",
                "avvisami",
                "reservar",
                "prenota",
            ]
        ):
          is_exhausted = True
          break

      # Controlla classi CSS comuni di Shopify/WooCommerce per esaurito
      all_classes_str = " ".join(
          [
              cls
              for elem in item.find_all(True)
              for cls in elem.get("class", [])
          ]
      ).lower()
      if any(
          term in all_classes_str
          for term in [
              "sold-out",
              "out-of-stock",
              "disabled",
              "agotado",
              "esaurito",
          ]
      ):
        is_exhausted = True

      if is_exhausted:
        continue
      # -------------------------------------

      price_elem = item.find(class_=lambda x: x and "price" in x.lower())
      price = estrai_prezzo_pulito(price_elem)

      seen_urls.add(product_link)

      found_products.append({
          "store": store_name,
          "url": product_link,
          "set": matched_set,
          "type": product_type,
          "title": product_title,
          "price": price,
          "status": "DISPONIBILE",
      })

    return found_products
  except Exception:
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
        if region not in report_by_region:
          report_by_region[region] = []
        report_by_region[region].extend(available)

  messaggio_telegram = "🚨 *RIFTBOUND ALERT: PRODOTTI DISPONIBILI!* 🚨\n\n"
  trovati_prodotti = False

  if report_by_region:
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
    inviato = manda_notifica_telegram(messaggio_telegram)
    if inviato:
      print("[OK] Prodotti trovati e notifica inviata su Telegram!")
    else:
      print("[!] Prodotti trovati ma invio Telegram FALLITO.")
  else:
    print("[INFO] Nessun prodotto disponibile in questo momento.")