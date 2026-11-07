# GitHub Sentinel Tracker

Bot pemantau repositori GitHub multi-repo berbasis GitHub Actions yang mengirim notifikasi langsung ke channel atau thread Discord melalui Webhook.

## Struktur File
```text
├── .github/
│   └── workflows/
│       └── track.yml        # Workflow GitHub Actions (Cron 06:00 & 18:00 UTC)
├── repos.json               # Konfigurasi repositori target, filter, dan webhook
├── tracker.py               # Skrip logika pemantau GitHub API & Discord sender
├── requirements.txt         # Dependensi Python (requests)
└── .gitignore               # Mengabaikan cache & file lokal
```

## Langkah Setup Cepat
1. Buat repositori baru di GitHub dan upload semua file dari zip ini.
2. Di GitHub Repository, masuk ke **Settings** > **Actions** > **General**:
   - Pada bagian **Workflow permissions**, pilih **Read and write permissions**, lalu klik **Save**.
3. Di **Settings** > **Secrets and variables** > **Actions** > **New repository secret**:
   - `DISCORD_WEBHOOK_URL`: Webhook default Discord Anda.
   - Tambahkan secret lain jika menggunakan webhook terpisah (misal `DISCORD_WEBHOOK_SHARED`, `DISCORD_WEBHOOK_DESKTOP`).
4. Edit `repos.json` sesuai repositori dan thread ID yang ingin Anda pantau.
5. Jalankan pertama kali secara manual via tab **Actions** > **Multi-Repo Sentinel Tracker** > **Run workflow**.
