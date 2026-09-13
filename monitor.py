#!/usr/bin/env python3
"""
Monitor orari lezioni - Università di Bergamo
Ingegneria Informatica Magistrale - Anno 1
"""

import requests
import json
import os
import hashlib
from datetime import datetime

# ── Configurazione ──────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "LOCAL_TEST_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "LOCAL_TEST_ID")

SNAPSHOT_FILE = "snapshot.json"

# Corsi da monitorare (confronto case-insensitive, anche parziale)
CORSI_INTERESSATI = [
    "ADAPTIVE LEARNING, ESTIMATION AND SUPERVISION OF DYNAMICAL SYSTEMS",
    "ADVANCED DATA MANAGEMENT AND LABORATORY",
    "STATISTICS FOR HIGH DIMENSIONAL DATA AND COMPSTAT LAB",
    "LINGUAGGI FORMALI E COMPILATORI",
]

# Endpoint API diretto
BASE_URL = "https://logistica.unibg.it/PortaleStudenti/grid_call.php"

# Payload estratto dal traffico di rete (Form Data)
PAYLOAD = {
    "view": "easycourse",
    "form-type": "corso",
    "include": "corso",
    "txtcurr": "2 - PERCORSO COMUNE",
    "anno": "2026",
    "scuola": "ScuoladiIngegneria",
    "corso": "38-270",
    "anno2[]": "PDS0-2012|2",
    "visualizzazione_orario": "cal",
    "date": datetime.now().strftime("%d-%m-%Y"), # ATTENZIONE: Questo parametro potrebbe definire la settimana specifica.
    "periodo_didattico": "S1",
    "_lang": "it",
    "list": "",
    "week_grid_type": "-1",
    "ar_codes_": "",
    "ar_select_": "",
    "col_cells": "0",
    "empty_box": "0",
    "only_grid": "0",
    "highlighted_date": "0",
    "all_events": "0",
    "faculty_group": "0"
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest" # Importante per simulare la chiamata AJAX
}

# ── Interrogazione API ──────────────────────────────────────────────────────

def fetch_schedule() -> list[dict]:
    """Interroga l'API JSON e restituisce una lista di eventi normalizzata."""
    # Usiamo POST invece di GET, passando il PAYLOAD in formato form-urlencoded (data=)
    resp = requests.post(BASE_URL, data=PAYLOAD, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    
    try:
        data = resp.json()
    except json.JSONDecodeError:
        raise ValueError("L'API non ha restituito un JSON valido. Controlla il payload.")

    events = []
    
    # Se 'celle' non esiste o è vuoto, restituisce una lista vuota
    celle = data.get("celle", [])

    for cella in celle:
        nome_corso = cella.get("nome_insegnamento", "Sconosciuto")
        
        if _corso_interessato(nome_corso):
            data_lez = cella.get("data", "")
            orario = cella.get("orario", "")
            aula = cella.get("aula", "Non assegnata")
            annullato = cella.get("Annullato", "0")
            
            # Formattiamo il testo che verrà mostrato su Telegram
            stato_icona = "❌ [ANNULLATA]" if annullato == "1" else "🔹"
            raw_text = f"{stato_icona} {nome_corso} | {data_lez} {orario} | {aula}"
            
            # Creiamo l'hash solo sui dati strutturati essenziali
            core_data = f"{nome_corso}|{data_lez}|{orario}|{aula}|{annullato}"
            event_hash = hashlib.md5(core_data.encode()).hexdigest()
            
            # Manteniamo le stesse chiavi del tuo vecchio script per non rompere il resto del codice
            events.append({"raw": raw_text, "html_hash": event_hash})

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
        lines.append("✅ <b>Nuovi inserimenti o Modifiche:</b>")
        for e in added[:10]:
            lines.append(f"  • {e['raw']}")

    if removed:
        lines.append("")
        lines.append("❌ <b>Lezioni rimosse o Sostituite:</b>")
        for e in removed[:10]:
            lines.append(f"  • {e['raw']}")

    lines.append("")
    lines.append("👉 Controlla il portale studenti per i dettagli.")
    return "\n".join(lines)

# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().isoformat()}] Avvio controllo orari via API...")

    try:
        events = fetch_schedule()
    except Exception as e:
        print(f"Errore durante il fetch: {e}")
        send_telegram(f"⚠️ Errore API UniBG:\n<code>{e}</code>")
        raise

    print(f"  → {len(events)} lezioni trovate per i corsi selezionati.")

    snapshot = load_snapshot()
    old_events = snapshot.get("events", [])
    old_fingerprint = snapshot.get("fingerprint", "")

    new_fingerprint = compute_fingerprint(events)

    if new_fingerprint != old_fingerprint:
        print("  → CAMBIAMENTO RILEVATO! Invio notifica Telegram...")
        if old_fingerprint:
            msg = build_diff_message(old_events, events)
            send_telegram(msg)
        else:
            print("  → Primo avvio con il nuovo sistema: salvo snapshot iniziale senza notificare.")

        save_snapshot({
            "events": events, 
            "fingerprint": new_fingerprint,
            "last_updated": datetime.now().isoformat()
        })
    else:
        print("  → Nessun cambiamento rilevato nello schedule.")

    print("  → Esecuzione terminata.")

if __name__ == "__main__":
    main()