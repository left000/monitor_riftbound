from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import time
from bs4 import BeautifulSoup
import requests

# Legge i token segreti direttamente dall'ambiente di GitHub Actions
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
    "Spagna - Marketplace & Grandi e-Commerce": {
        "CardZone": "https://cardzone.es/collections/riftbound-league-of-legends",
        "Gameria": "https://gameria.es/76-league-of-legends-riftbound",
        "Metrópolis Center": "https://metropolis-center.com",
        "Zacatrus": "https://zacatrus.es",
        "GAME": "https://www.game.es",
        "TopDeck": "https://topdeck.es/collections/all",
        "Dungeon Marvels": "https://dungeonmarvels.com",
    },
    "Spagna - Negozi Specializzati & Catene (Gruppo 1)": {
        "Factory Cards": "https://factorycards.es",
        "Micelion Games": "https://miceliongames.com",
        "Padis Store": (
            "https://www.padis-store.com/en/443-riftbound-league-of-legends-tcg"
        ),
        "Madrid Norte TCG": (
            "https://madridnortetcg.com/en/collections/riftbound-tcg"
        ),
        "Metamorph Center": "https://metamorphcenter.com",
        "El Duelista": "https://elduelista.com",
        "Ninpo Store": "https://ninpostore.com",
        "La Guarida Juegos": "https://laguaridajuegos.com",
        "Gladius Games": "https://gladiusgames.es",
        "Velkarion": "https://velkarion.com",
        "Aquijabara Store": "https://aquijabara.com",
        "Generación X Carranza": "https://generacionx.es",
        "Kingdom Wargames": "https://kingdomwargames.es",
        "Tempest Store": "https://tempeststore.es",
        "OZ Juegos": (
            "https://ozjuegos.com/categoria-producto/juegos-de-cartas/riftbound-league-of-legends-tcg/"
        ),
        "Júpiter Juegos": "https://jupiterjuegos.com",
    },
    "Spagna - Negozi Specializzati & Catene (Gruppo 2)": {
        "Epic Hit Store": "https://epichitstore.com",
        "HoloPlaza TCG": "https://holoplazatcg.com",
        "JJCollection": "https://jjcollection.es",
        "Saruman Games": "https://sarumangames.com",
        "G3 TCG": "https://g3tcg.com",
        "Estalia Games": "https://estaliagames.com",
        "La Forja": "https://laforjajuegos.com",
        "CardCrack": "https://cardcrack.es",
        "Empire Games": (
            "https://www.empiregames.es/categoria-producto/juegos-de-cartas-coleccionables/league-of-legends-tcg-riftbound/"
        ),
        "A Dado y Pluma": "https://adadoypluma.com",
        "Unchained Games": "https://unchainedgames.es",
        "Tini Games": "https://tinigames.es",
        "TCG Legacy": "https://tcglegacy.es",
        "IngenioBCN": "https://ingeniobcn.com",
        "La Tienda Scum": "https://latiendascum.com",
        "Matsuri Comics": "https://matsuricomics.com",
    },
    "Spagna - Negozi Specializzati & Catene (Gruppo 3)": {
        "Toreka Games": "https://torekagames.com",
        "El Nexo SF": "https://elnexosf.com",
        "Magic Event": "https://magicevent.es",
        "La Escotilla": "https://laescotillajuegos.com",
        "City of Cards": "https://cityofcards.es",
        "Aether Alicante": "https://aetheralicante.com",
        "Daruma Games": "https://darumagames.es",
        "Arcane Hall": "https://arcanehall.es",
        "Rift Nexus Game Store": "https://riftnexus.es",
        "ELIUS": "https://elius.es",
        "Pulsar Store": "https://pulsarstore.es",
        "Júpiter Juegos Castellón": "https://jupiterjuegoscastellon.com",
        "La Torre Karin Store": "https://latorrekarin.com",
        "TPK Hobby & Games": "https://tpkhobby.es",
        "Júpiter Juegos Ourense": "https://jupiterjuegosourense.com",
        "La Plaza Bilbao": "https://laplazabilbao.com",
    },
    "Spagna - Collezionismo & Community TCG (Gruppo 4)": {
        "Cartas Mencey": "https://cartasmencey.com",
        "TCG Parada": "https://tcgparada.com",
        "Ludicón": "https://ludicon.es",
        "Magic Mallorca": "https://magicmallorca.com",
        "Monarka TCG": "https://monarkatcg.com",
        "Tierra616": "https://tierra616.es",
        "AllInTCG": "https://allintcg.es",
        "BaruZcard": "https://baruzcard.com",
        "Bescards": "https://bescards.com",
        "BimbaCards": "https://bimbacards.com",
        "Break The Case": "https://breakthecase.es",
        "CanaryPop": "https://canarypop.es",
        "Cardverse": "https://cardverse.es",
        "Checollect": "https://checollect.com",
        "Dabas": "https://dabas.es",
        "Distrito Zero": "https://distritozero.es",
        "Freak Corp": "https://freakcorp.es",
        "Gamescape": "https://gamescape.es",
        "Golden Pulls Cards": "https://goldenpullscards.com",
        "GrilleCards": "https://grillecards.com",
        "HeroFreaks": "https://herofreaks.com",
        "Homelands": "https://homelands.es",
    },
    "Spagna - Ultime novità e Collezionismo (Gruppo 5)": {
        "Ikigai Comics": "https://ikigaicomics.com",
        "Indústria 61": "https://industria61.com",
        "Kame House Cards": "https://kamehousecards.com",
        "KeepSeven": "https://keepseven.es",
        "KuriGames": "https://kurigames.com",
        "La Tienda de las Cartas": "https://latiendadelascartas.com",
        "LorcanosTCG": "https://lorcanostcg.es",
        "Lotus Valley": "https://lotusvalley.es",
        "Magic Omens": "https://magicomens.com",
        "MagicNerd": "https://magicnerd.es",
        "ManaTCG": "https://manatcg.es",
        "Manavortex": "https://manavortex.es",
        "Merchfox": "https://merchfox.com",
        "Minas de Moria": "https://minasdemoria.com",
        "Mono de Juegos": (
            "https://www.monodejuegos.shop/categoria-producto/trading-cards/riftbound/"
        ),
        "Monsters Collectors": "https://monsterscollectors.com",
        "Otakura": "https://otakura.com",
        "Otakuya": "https://otakuya.es",
        "Pocketcards": "https://pocketcards.es",
        "Plaza TCG": "https://plazatcg.com",
        "Plugstars": "https://plugstars.es",
        "Poke-Geek": "https://poke-geek.com",
        "PokeBros": "https://pokebros.es",
        "PokeCards Store": "https://pokecardsstore.es",
        "PokeFamily": "https://pokefamily.es",
        "PokeTalk": "https://poketalk.es",
        "Pokeca": "https://pokeca.es",
        "Psydeck": "https://psydeck.com",
        "RelicTCG": "https://relictcg.es",
        "Snooop": "https://snooop.es",
        "Solo Hits": "https://solohits.es",
        "StarGeek": "https://stargeek.es",
        "SunnyStore": "https://sunnystore.es",
        "TCG Level": "https://tcglevel.es",
        "TCGdirect": "https://tcgdirect.es",
        "Templars Arena": "https://templarsarena.com",
        "Tsuki Center": "https://tsukicenter.com",
        "Universe TCG": "https://universetcg.es",
        "Vicol TCG": "https://vicoltcg.com",
        "VintiCards": "https://vinticards.com",
        "Yonko TCG": "https://yonkotcg.es",
    },
    "Italia - Negozi e Fumetterie Principali (Gruppo 1)": {
        "MOBA Store": "https://www.mobastore.it",
        "OP SHOP": "https://opshop.it",
        "Magic Store": "https://www.magicstore.it",
        "iWozGaming": "https://iwozgaming.it",
        "Golden Store Roma Talenti": "https://goldenstoreroma.it",
        "Magliana Nerd": "https://www.magliananerd.it",
        "Galactus Roma": "https://galactus.it",
        "Galactus Tuscolana": "https://galactus.it",
        "Galactus Tiburtina": "https://galactus.it",
        "Games Inn": "https://www.gamesinn.it",
        "Games Time Torino Centro": "https://www.gamestime.it",
        "Goblin Srl": "https://www.goblin.it",
        "MagoMatto": "https://www.magomatto.com",
    },
    "Italia - Specializzati TCG & Collezionismo (Gruppo 2)": {
        "Cards Capital City Cormano": "https://cardscapitalcity.it",
        "Titan Gaming Center": "https://titangamingcenter.com",
        "IL REGNO": "https://ilregno.it",
        "ManaWeb": "https://manaweb.it",
        "La Tana delle Pulci": "https://latanadellepulci.it",
        "Dadi e Draghi": "https://www.dadiedraghi.com",
        "Spazio Nerd": "https://spazionerd.it",
        "Lost Legion": "https://lostlegion.it",
        "B Games Bologna": "https://bgamesbologna.it",
        "ONGAME": "https://ongame.it",
        "Funside Katané": "https://www.funside.it",
        "Magicards": "https://magicards.it",
        "Toon Kingdom": "https://toonkingdom.it",
        "The Magic Spot": "https://themagicspot.it",
    },
    "Italia - Distribuzione e Hobby Store (Gruppo 3)": {
        "Star Shop Firenze Distribuzione": "https://www.starshop.it",
        "Firenze Comics and Games": "https://firenzecomicsandgames.it",
        "Carta Magna": "https://cartamagna.it",
        "The Realm": "https://therealm.it",
        "La Gilda di Busto": "https://lagildadibusto.it",
        "Dungeon Street": "https://dungeonstreet.it",
        "4X Trading Shop & Play": "https://4xtrading.it",
        "Starshop Lucca": "https://starshoplucca.it",
        "Topgame": "https://topgame.it",
        "Il Covo del Nerd": "https://www.ilcovodelnerd.it",
        "Pryce": "https://pryce.it",
        "Teca Rara": "https://tecarara.it",
        "Zero One": "https://zero-one.it",
        "Anime Shop Italia": "https://animeshopitalia.it",
    },
    "Italia - Videogames, Nerd & Geek Shop (Gruppo 4)": {
        "Time Out Videogames": "https://timeoutvideogames.it",
        "Iconic Cards": "https://iconiccards.it",
        "Games-Shop": "https://games-shop.it",
        "Magic Merchant": "https://www.magicmerchant.it",
        "Ludosport": "https://ludosport.net",
        "GameOnly": "https://gameonly.it",
        "Gameology": "https://www.gameology.it",
        "Arcano Games": "https://www.arcanogames.it",
        "Fumettopoli": "https://fumettopoli.it",
        "TCG Factory Milano": "https://tcgfactory.it",
        "Collector's Inn": "https://collectorsinn.it",
        "LaBotteSecrete": "https://labottesecrete.it",
        "Sanctum TCG": "https://sanctumtcg.it",
        "TheManaShop": "https://themanashop.it",
    },
    "Italia - Collezionismo Estero ed Europeo (Gruppo 5)": {
        "YottoStore": "https://yottostore.com",
        "Vega-TCG": "https://vega-tcg.com",
        "SunEaterGames": "https://suneatergames.com",
        "Emporium del D20": "https://emporiumd20.it",
        "Runik GS Events": "https://runik.it",
        "GGCollectorsGames": "https://ggcollectorsgames.com",
        "EuropeTCG": "https://europetcg.com",
        "NeyzerTCG": "https://neyzertcg.com",
        "AdventureTCG": "https://adventuretcg.com",
        "MO-CARDS": "https://mo-cards.com",
        "Multivers Paris": "https://www.multivers.fr",
        "PhyrexianMTG": "https://phyrexianmtg.com",
        "BoardCraft": "https://boardcraft.fr",
        "Parkage": "https://www.parkage.com",
        "Ludeek09": "https://ludeek09.fr",
        "Antre des Geeks": "https://www.antredesgeeks.com",
    },
    "Italia - Ultime Aggiunte e Reti Nazionali (Gruppo 6)": {
        "Magic Warrior Mestre": "https://magicwarrior.it",
        "MonkeyCards": "https://monkeycards.it",
        "Mana Flask": "https://manaflask.it",
        "ASD Il Rifugio": "https://asdilrifugio.it",
        "Alpha Comix": "https://alphacomix.it",
        "Dark Zone": "https://darkzone.it",
        "December Dungeon": "https://decemberdungeon.it",
        "The Match Store": "https://thematchstore.it",
        "Games Academy Catania": "https://www.gamesacademy.it",
        "Funside": "https://www.funside.it",
        "La Gilda Store": "https://lagildastore.it",
        "Cards Capital City": "https://cardscapitalcity.it",
        "Games Inn Torino": "https://www.gamesinn.it",
        "Firenze Comics & Games": "https://firenzecomicsandgames.it",
        "Star Shop": "https://www.starshop.it",
        "Carta Magna Firenze": "https://cartamagna.it",
        "The Realm Firenze": "https://therealm.it",
        "Titan Gaming Center Milano": "https://titangamingcenter.com",
        "Games Time": "https://www.gamestime.it",
        "Galactus": "https://galactus.it",
        "Il Regno": "https://ilregno.it",
        "Magic Store Italia": "https://www.magicstore.it",
        "OP Shop Milano": "https://opshop.it",
        "Manicomix": "https://www.manicomix.com",
        "Manicomix Distribuzione": "https://www.manicomix.com",
    },
}


def manda_notifica_telegram(testo):
  if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print(
        "[!] Errore Telegram: Token o Chat ID mancanti tra le variabili"
        " d'ambiente."
    )
    return False
  url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
  payload = {"chat_id": TELEGRAM_CHAT_ID, "text": testo, "parse_mode": "Markdown"}
  try:
    res = requests.post(url, json=payload, timeout=10)
    data = res.json()
    if not data.get("ok"):
      print(f"[!] Errore da Telegram API: {data.get('description')}")
      return False
    return True
  except Exception as e:
    print(f"[!] Errore di connessione a Telegram: {e}")
    return False


def check_store_stock(store_name, url):
  print(f"[*] Analizzando store ({store_name}) -> {url}")
  try:
    response = requests.get(url, headers=HEADERS, timeout=8)
    if response.status_code != 200:
      return []

    html = response.text
    if (
        "myshopify.com" in html
        or "shopifycdn.com" in html
        or "Shopify.shop" in html
    ):
      print(f"[-] Escluso {store_name}: Piattaforma Shopify rilevata.")
      return []

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
      if any(lang in title_lower or lang in item_text for lang in lingue_da_escludere):
        continue

      if (
          "lingua" in item_text
          or "language" in item_text
          or "idioma" in item_text
      ):
        if (
            "ital" in item_text
            or "frances" in item_text
            or "allemand" in item_text
            or "alemán" in item_text
            or "chino" in item_text
            or "espan" in item_text
        ):
          if (
              "english" not in item_text
              and "inglese" not in item_text
              and "ingles" not in item_text
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
        product_type = "CASE (6x Booster Box)"
      elif is_display_24:
        product_type = "CAJA SUELTA (24 Booster Display)"
      else:
        continue

      seen_urls.add(product_link)

      is_exhausted = any(term in item_text for term in TERMINI_ESAURITO)
      badges = item.find_all(
          class_=lambda x: x
          and any(
              b in x.lower()
              for b in [
                  "agotado",
                  "esaurito",
                  "sold-out",
                  "out-of-stock",
                  "disabled",
              ]
          )
      )
      if badges:
        for badge in badges:
          if any(
              t in badge.get_text().lower()
              for t in [
                  "agotado",
                  "esaurito",
                  "sold out",
                  "sin stock",
                  "non disponibile",
              ]
          ):
            is_exhausted = True
            break

      buy_button = item.find(
          ["button", "a", "input"],
          class_=lambda x: x
          and any(
              b in x.lower()
              for b in [
                  "add",
                  "comprar",
                  "cart",
                  "btn",
                  "acquista",
                  "carrello",
              ]
          ),
      )
      if buy_button:
        btn_text = buy_button.get_text().lower()
        if any(
            t in btn_text
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
        if buy_button.has_attr("disabled"):
          is_exhausted = True

      if is_exhausted:
        continue

      price_elem = item.find(class_=lambda x: x and "price" in x.lower())
      price = (
          price_elem.get_text(strip=True)
          if price_elem
          else "Prezzo non trovato"
      )

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
  except Exception as e:
    return []


def process_store(region, store_name, store_url):
  results = check_store_stock(store_name, store_url)
  available = [
      p
      for p in results
      if "DISPONIBILE" in p["status"] or "EN STOCK" in p["status"]
  ]
  return region, available


if __name__ == "__main__":
  print("=== Avvio scansione totale SPAGNA + ITALIA (SOLO INGLESE) ===")
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

  report_content = (
      "# REPORT DISPONIBILITÀ RIFTBOUND (SPAGNA + ITALIA - SOLO INGLESE)\n\n"
  )
  report_content += (
      f"*Data e ora scansione:* {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
  )
  report_content += "---\n\n"

  messaggio_telegram = "🚨 *RIFTBOUND ALERT: PRODOTTI DISPONIBILI!* 🚨\n\n"
  trovati_prodotti = False

  if not report_by_region:
    report_content += "Nessun prodotto trovato.\n"
  else:
    for region, products in report_by_region.items():
      report_content += f"## 📍 {region}\n\n"
      messaggio_telegram += f"*{region}*\n"
      for prod in products:
        trovati_prodotti = True
        report_content += f"### [{prod['store']}]({prod['url']})\n"
        report_content += f"- **Set:** {prod['set']}\n"
        report_content += f"- **Formato:** {prod['type']}\n"
        report_content += f"- **Prezzo:** {prod['price']}\n\n"
        report_content += "---\n\n"

        messaggio_telegram += (
            f"• [{prod['store']}]({prod['url']}) - *{prod['set']}* ({prod['price']})\n"
        )
      messaggio_telegram += "\n"

  file_name = "report_riftbound_spagna_italia_inglese.md"
  with open(file_name, "w", encoding="utf-8") as f:
    f.write(report_content)

  if trovati_prodotti:
    inviato = manda_notifica_telegram(messaggio_telegram)
    if inviato:
      print("[OK] Prodotti trovati e notifica inviata su Telegram!")
    else:
      print(
          "[!] Prodotti trovati ma invio Telegram FALLITO. Controlla il log"
          " sopra."
      )
  else:
    print(
        "[INFO] Nessun prodotto disponibile in questo momento. Telegram non"
        " disturbato."
    )