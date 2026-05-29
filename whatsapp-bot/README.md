# WhatsApp Bot (Baileys Web Session)

## Setup
```bash
cd whatsapp-bot
cp .env.example .env
```

Isi `.env`:
- `WA_CONNECTION` = `qr` atau `pairing`
- `WA_PAIRING_NUMBER` (wajib jika `pairing`, format internasional tanpa `+`)
- `WA_SESSION_DIR` (folder session, default `wa-session`)
- `WA_OWNER_NUMBER` (nomor owner yang menerima notifikasi)
- `WA_DISABLE_TERMINAL_QR` (jika `true`, QR tidak tampil di terminal)
- `WA_BOT_NUMBER` (override tampilan nomor bot; tidak mengubah akun WhatsApp)
- `WA_BACKEND_URL` (default `http://localhost:8000`)
- `WA_NOTIFICATION_POLL_MS` (interval polling notifikasi)
- `WA_SEND_LATEST_ON_START` (kirim notifikasi terbaru saat bot online)
- `PAGE_NOTIFICATION_URL` (opsional)

## Run
```bash
npm install
npm run dev
```

Build & run:
```bash
npm run build
npm start
```

## Pairing / QR
- Jika `WA_CONNECTION=qr`, QR akan muncul di terminal.
- Jika `WA_CONNECTION=pairing`, pairing code akan tampil di terminal.

## Notes
- Dedupe cache default 10 menit.
- Untuk Redis: set `REDIS_URL`.
