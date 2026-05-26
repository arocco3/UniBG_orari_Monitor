# 📅 Monitor Orari — Università di Bergamo
### Ingegneria Informatica Magistrale · Anno 1

Monitora automaticamente gli orari delle lezioni e ti avvisa su **Telegram** quando cambiano.

---

## Come funziona

1. GitHub Actions esegue `monitor.py` **ogni ora** (7:00–22:00, lun–sab)
2. Lo script scarica la pagina degli orari e confronta con lo snapshot precedente
3. Se rileva cambiamenti nei tuoi corsi → ricevi un messaggio Telegram con i dettagli

---

## Setup (15 minuti, una tantum)

### Passo 1 — Crea un bot Telegram

1. Apri Telegram e cerca **@BotFather**
2. Manda `/newbot` e segui le istruzioni (scegli un nome tipo "UniBG Orari Bot")
3. BotFather ti darà un **token** tipo `123456789:AAFabc...` → salvalo

### Passo 2 — Ottieni il tuo Chat ID

1. Manda un qualsiasi messaggio al bot appena creato
2. Apri nel browser: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   (sostituisci `<TOKEN>` con il tuo token)
3. Nel JSON cerca `"chat": {"id": XXXXXXXXX}` → quel numero è il tuo **Chat ID**

### Passo 3 — Crea il repository GitHub

1. Vai su [github.com](https://github.com) e crea un nuovo repo (es. `unibg-orari-monitor`)
2. Carica questi file nel repo:
   ```
   monitor.py
   .github/
   └── workflows/
       └── monitor.yml
   ```
   *(il file `snapshot.json` verrà creato automaticamente al primo avvio)*

### Passo 4 — Aggiungi i secret

Nel tuo repo GitHub: **Settings → Secrets and variables → Actions → New repository secret**

Aggiungi questi due secret:

| Nome | Valore |
|------|--------|
| `TELEGRAM_TOKEN` | il token del bot (es. `123456789:AAFabc...`) |
| `TELEGRAM_CHAT_ID` | il tuo chat ID (es. `987654321`) |

### Passo 5 — Attiva il workflow

1. Vai su **Actions** nel tuo repo
2. Se vedi un avviso "Workflows aren't running", clicca **"I understand my workflows, go ahead and enable them"**
3. Clicca su **"Monitor Orari UniBG"** → **"Run workflow"** per fare un test manuale

Al primo avvio lo script salva lo snapshot iniziale **senza mandare notifiche**.
Dal secondo avvio in poi, qualsiasi cambiamento ti verrà notificato.

---

## Corsi monitorati

- GESTIONE AZIENDALE
- OPTIMIZATION
- STATISTICAL LEARNING
- INTELLIGENZA ARTIFICIALE
- RETI DI TELECOMUNICAZIONI
- TEORIA DELL'INFORMAZIONE E DELLA TRASMISSIONE (TIT)

Per aggiungere/rimuovere corsi, modifica la lista `CORSI_INTERESSATI` in `monitor.py`.

---

## Struttura file

```
.
├── monitor.py              # script principale
├── snapshot.json           # snapshot degli orari (aggiornato automaticamente)
└── .github/
    └── workflows/
        └── monitor.yml     # workflow GitHub Actions
```

---

## Troubleshooting

**Non ricevo notifiche al test manuale**
→ Assicurati di aver mandato almeno un messaggio al bot prima di fare il test.
→ Verifica che i secret siano corretti (senza spazi prima/dopo).

**Il workflow fallisce con errore di rete**
→ Il portale dell'università potrebbe essere down momentaneamente. Riprova.

**Voglio cambiare la frequenza di controllo**
→ Modifica la riga `cron:` in `monitor.yml`. Usa [crontab.guru](https://crontab.guru) per generare l'espressione.

**La pagina ha cambiato struttura e non trova i corsi**
→ Apri una issue o modifica i selettori in `fetch_schedule()` in `monitor.py`.
