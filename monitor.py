#!/usr/bin/env python3
"""
Monitor orari lezioni - Università di Bergamo
Ingegneria Informatica Magistrale - Anno 1
"""

import requests
import json
import os
import hashlib
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# ── Configurazione ──────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SNAPSHOT_FILE = "snapshot.json"

# Corsi da monitorare (confronto case-insensitive, anche parziale)
CORSI_INTERESSATI = [
    "GESTIONE AZIENDALE",
    "OPTIMIZATION",
    "STATISTICAL LEARNING",
    "INTELLIGENZA ARTIFICIALE",
    "RETI DI TELECOMUNICAZIONI",
    "TEORIA DELL'INFORMAZIONE E DELLA TRASMISSIONE (TIT)",
]

# URL base del portale con i parametri fissi del tuo corso
BASE_URL = "https://logistica.unibg.it/PortaleStudenti/index.php"
PARAMS = {
    "view": "easycourse",
    "form-type": "corso",
    "include": "corso",
    "txtcurr": "1 - PERCORSO COMUNE",
    "anno": "2025",
    "scuola": "ScuoladiIngegneria",
    "corso": "38-270",
    "anno2[]": "PDS0-2012|1",
    "visualizzazione_orario": "list",   # lista = più facile da parsare
    "_lang": "it",
    "all_events": "1",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# ── Scraping ────────────────────────────────────────────────────────────────

def fetch_schedule() -> list[dict]:
    """Scarica la pagina orari e restituisce una lista di eventi."""
    resp = requests.get(BASE_URL, params=PARAMS, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events = []

    # Il portale EasyCourse usa tag <li class="event-item"> oppure tabelle.
    # Proviamo entrambe le strutture comuni.

    # Struttura 1: div/li con classe "evento" o "event"
    for el in soup.find_all(["li", "div"], class_=lambda c: c and "event" in c.lower()):
        text = el.get_text(" ", strip=True)
        if _corso_interessato(text):
            events.append({"raw": text, "html_hash": hashlib.md5(str(el).encode()).hexdigest()})

    # Struttura 2: righe di tabella (fallback)
    if not events:
        for row in soup.find_all("tr"):
            text = row.get_text(" ", strip=True)
            if _corso_interessato(text) and len(text) > 20:
                events.append({"raw": text, "html_hash": hashlib.md5(str(row).encode()).hexdigest()})

    # Struttura 3: testo libero nella pagina (ultimo fallback - hash globale)
    if not events:
        page_text = soup.get_text(" ", strip=True)
        relevant_lines = [
            line.strip()
            for line in page_text.splitlines()
            if _corso_interessato(line) and len(line.strip()) > 15
        ]
        for line in relevant_lines:
            events.append({"raw": line, "html_hash": hashlib.md5(line.encode()).hexdigest()})

    return events


def _corso_interessato(text: str) -> bool:
    t = text.upper()
    return any(corso.upper() in t for corso in CORSI_INTERESSATI)


# ── Confronto snapshot ──────────────────────────────────────────────────────

def load_snapshot() -> dict:
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_snapshot(data: dict):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def compute_fingerprint(events: list[dict]) -> str:
    combined = "|".join(sorted(e["html_hash"] for e in events))
    return hashlib.sha256(combined.encode()).hexdigest()


# ── Telegram ────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()


def build_diff_message(old_events: list, new_events: list) -> str:
    old_hashes = {e["html_hash"] for e in old_events}
    new_hashes = {e["html_hash"] for e in new_events}

    added = [e for e in new_events if e["html_hash"] not in old_hashes]
    removed = [e for e in old_events if e["html_hash"] not in new_hashes]

    lines = ["🔔 <b>Cambiamento orari rilevato!</b>", f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}", ""]

    if added:
        lines.append("✅ <b>Nuovi/modificati:</b>")
        for e in added[:10]:  # max 10 per non superare il limite Telegram
            lines.append(f"  • {e['raw'][:200]}")

    if removed:
        lines.append("")
        lines.append("❌ <b>Rimossi/modificati:</b>")
        for e in removed[:10]:
            lines.append(f"  • {e['raw'][:200]}")

    lines.append("")
    lines.append("👉 Controlla: logistica.unibg.it")
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Avvio controllo orari...")

    try:
        events = fetch_schedule()
    except Exception as e:
        print(f"Errore durante il fetch: {e}")
        send_telegram(f"⚠️ Errore monitor orari UniBG:\n<code>{e}</code>")
        raise

    print(f"  → {len(events)} eventi trovati per i corsi selezionati")

    snapshot = load_snapshot()
    old_events = snapshot.get("events", [])
    old_fingerprint = snapshot.get("fingerprint", "")

    new_fingerprint = compute_fingerprint(events)

    if new_fingerprint != old_fingerprint:
        print("  → CAMBIAMENTO RILEVATO! Invio notifica Telegram...")
        if old_fingerprint:  # non notificare al primo avvio
            msg = build_diff_message(old_events, events)
            send_telegram(msg)
        else:
            print("  → Primo avvio: salvo snapshot iniziale senza notifica.")

        save_snapshot({"events": events, "fingerprint": new_fingerprint,
                       "last_updated": datetime.now().isoformat()})
    else:
        print("  → Nessun cambiamento.")

    print("  → Done.")


if __name__ == "__main__":
    main()
