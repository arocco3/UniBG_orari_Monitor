#!/usr/bin/env python3
"""
Monitor orari lezioni - Università di Bergamo
Ingegneria Informatica Magistrale - Anno 1
Chiama grid_call.php direttamente e salva schedule.json per la dashboard.
"""

import requests
import json
import os
import hashlib
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

TELEGRAM_TOKEN  = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

SNAPSHOT_FILE  = "snapshot.json"
SCHEDULE_FILE  = "schedule.json"   # letto dalla dashboard HTML

CORSI_INTERESSATI = [
    "GESTIONE AZIENDALE",
    "OPTIMIZATION",
    "STATISTICAL LEARNING",
    "INTELLIGENZA ARTIFICIALE",
    "RETI DI TELECOMUNICAZIONE (principi e laboratorio)",
    "TEORIA DELL'INFORMAZIONE E DELLA TRASMISSIONE (TIT)",
]

COLORI_CORSO = {
    "GESTIONE AZIENDALE":           "#4F46E5",
    "OPTIMIZATION":                  "#0891B2",
    "STATISTICAL LEARNING":          "#059669",
    "INTELLIGENZA ARTIFICIALE":      "#7C3AED",
    "RETI DI TELECOMUNICAZIONE (principi e laboratorio)":     "#DC2626",
    "TEORIA DELL'INFORMAZIONE E DELLA TRASMISSIONE (TIT)":      "#D97706",
}

GRID_URL = "https://logistica.unibg.it/PortaleStudenti/grid_call.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Referer": "https://logistica.unibg.it/PortaleStudenti/index.php",
    "X-Requested-With": "XMLHttpRequest",
}

def fetch_weeks(num_weeks: int = 8) -> list[dict]:
    all_cells = []
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())

    for w in range(num_weeks):
        date_str = (monday + timedelta(weeks=w)).strftime("%d-%m-%Y")
        payload = {
            "form-type":              "corso",
            "anno":                   "2025",
            "scuola":                 "ScuoladiIngegneria",
            "corso":                  "38-270",
            "anno2[]":                "PDS0-2012|1",
            "visualizzazione_orario": "cal",
            "date":                   date_str,
            "_lang":                  "it",
            "all_events":             "1",
        }
        try:
            r = requests.post(GRID_URL, data=payload, headers=HEADERS, timeout=30)
            r.raise_for_status()
            print(f"  → settimana {date_str}: status {r.status_code}, risposta {r.text[:300]}")
            data = r.json()
            celle = data.get("celle", [])
            print(f"     celle totali: {len(celle)}")
            if celle:
                print(f"     primo corso: {celle[0].get('nome_insegnamento', 'N/A')}")
            all_cells.extend(celle)
        except Exception as e:
            print(f"  Errore settimana {date_str}: {e}")

    return all_cells


def _corso_interessato(nome: str) -> bool:
    n = nome.upper()
    return any(c.upper() in n for c in CORSI_INTERESSATI)


def _colore(nome: str) -> str:
    n = nome.upper()
    for chiave, colore in COLORI_CORSO.items():
        if chiave.upper() in n:
            return colore
    return "#6B7280"


def parse_cells(cells: list[dict]) -> list[dict]:
    """Filtra e normalizza le celle nei corsi di interesse."""
    events = []
    seen = set()
    for c in cells:
        nome = c.get("nome_insegnamento", "")
        if not _corso_interessato(nome):
            continue
        uid = f"{c.get('id')}_{c.get('data')}_{c.get('ora_inizio')}"
        if uid in seen:
            continue
        seen.add(uid)

        # Estrai docenti puliti (strip HTML)
        docente_raw = c.get("docente", "")
        docente = BeautifulSoup(docente_raw, "html.parser").get_text(", ") if "<" in docente_raw else docente_raw

        events.append({
            "id":         c.get("id"),
            "nome":       nome,
            "colore":     _colore(nome),
            "data":       c.get("data"),           # "25-05-2026"
            "giorno":     c.get("GiornoCompleto"), # "lunedì 25 maggio 2026"
            "ora_inizio": c.get("ora_inizio"),
            "ora_fine":   c.get("ora_fine"),
            "aula":       c.get("aula", ""),
            "docente":    docente,
            "tipo":       c.get("tipo", ""),
            "annullato":  c.get("Annullato", "0") == "1",
        })

    events.sort(key=lambda e: (e["data"].split("-")[::-1], e["ora_inizio"]))
    return events


def compute_fingerprint(events: list[dict]) -> str:
    combined = "|".join(
        f"{e['id']}_{e['data']}_{e['ora_inizio']}_{e['ora_fine']}_{e['aula']}"
        for e in sorted(events, key=lambda x: x["id"])
    )
    return hashlib.sha256(combined.encode()).hexdigest()


def save_schedule(events: list[dict]):
    payload = {
        "aggiornato": datetime.now().isoformat(),
        "lezioni": events,
    }
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def load_snapshot() -> dict:
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_snapshot(fp: str, events: list[dict]):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump({"fingerprint": fp, "events": events,
                   "last_updated": datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)


def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=15)
    r.raise_for_status()


def build_diff_message(old: list, new: list) -> str:
    old_ids = {e["id"] for e in old}
    new_ids = {e["id"] for e in new}
    old_map = {e["id"]: e for e in old}
    new_map = {e["id"]: e for e in new}

    added   = [new_map[i] for i in new_ids - old_ids]
    removed = [old_map[i] for i in old_ids - new_ids]
    changed = [
        new_map[i] for i in old_ids & new_ids
        if old_map[i]["ora_inizio"] != new_map[i]["ora_inizio"]
        or old_map[i]["aula"]      != new_map[i]["aula"]
        or old_map[i]["ora_fine"]  != new_map[i]["ora_fine"]
    ]

    lines = [f"🔔 <b>Cambiamento orari rilevato!</b>", f"📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}", ""]

    def fmt(e):
        ann = " ❌ ANNULLATA" if e.get("annullato") else ""
        return f"  • {e['nome']}{ann}\n    {e['giorno']} {e['ora_inizio']}–{e['ora_fine']} | {e['aula']}"

    if added:
        lines.append("✅ <b>Nuove lezioni:</b>")
        lines += [fmt(e) for e in added[:8]]
    if removed:
        lines.append("\n❌ <b>Lezioni rimosse:</b>")
        lines += [fmt(e) for e in removed[:8]]
    if changed:
        lines.append("\n✏️ <b>Orario/aula modificati:</b>")
        for e in changed[:8]:
            o = old_map[e["id"]]
            lines.append(f"  • {e['nome']}\n    {o['ora_inizio']}–{o['ora_fine']} {o['aula']} → {e['ora_inizio']}–{e['ora_fine']} {e['aula']}")

    lines += ["", "👉 logistica.unibg.it"]
    return "\n".join(lines)


def main():
    print(f"[{datetime.now().isoformat()}] Avvio controllo orari...")

    try:
        cells  = fetch_weeks(num_weeks=8)
        events = parse_cells(cells)
    except Exception as e:
        print(f"Errore fetch: {e}")
        send_telegram(f"⚠️ Errore monitor orari UniBG:\n<code>{e}</code>")
        raise

    print(f"  → {len(events)} lezioni trovate per i corsi selezionati")

    save_schedule(events)
    print(f"  → schedule.json aggiornato")

    snapshot = load_snapshot()
    old_events   = snapshot.get("events", [])
    old_fp       = snapshot.get("fingerprint", "")
    new_fp       = compute_fingerprint(events)

    if new_fp != old_fp:
        if old_fp:
            print("  → CAMBIAMENTO RILEVATO! Invio notifica Telegram...")
            send_telegram(build_diff_message(old_events, events))
        else:
            print("  → Primo avvio: snapshot iniziale salvato.")
        save_snapshot(new_fp, events)
    else:
        print("  → Nessun cambiamento.")

    print("  → Done.")


if __name__ == "__main__":
    main()
