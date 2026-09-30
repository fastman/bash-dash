# bash-dash

Gra w basha na telefonie (5 minut, ranking, kod nagrody). Django + SQLite; każda komenda gracza
wykonuje się w utwardzonym kontenerze (sandbox).

## Demo w sieci lokalnej (Docker Compose)

Setup deweloperski/demo — bez HTTPS, bez kopii zapasowych (to osobne zadanie F-02).

```sh
cp .env.example .env      # uzupełnij SECRET_KEY, PUBLIC_URL (IP w LAN), hasło obsługi
docker compose up -d --build
```

Pierwszy start buduje obraz sandboxa (`bash-dash-sandbox:latest`) w Dockerze hosta, potem startuje
aplikacja. Na Apple Silicon / ARM ustaw `BUILD_PLATFORM=linux/arm64` w `.env`.

Adresy (port z `BASHDASH_PORT`, domyślnie 8000):

- `/` — gra (start wymaga tokenu z QR albo 6-cyfrowego kodu spod QR),
- `/staff/hall` — ekran rankingu z QR (otwórz go pod adresem z `BASHDASH_PUBLIC_URL`),
- `/staff` — wyszukiwanie kodu nagrody, `/admin/` — panel.

Koledzy z sieci biurowej łączą się pod `http://<IP-hosta>:8000`; jeśli host ma firewall, otwórz ten port.

### Dane

Baza leży na hoście w `./data/` (`db.sqlite3` + pliki WAL), więc przeżywa `docker compose down`
i przebudowę. Pliki należą do roota (kontener działa jako root).

- kopia zapasowa: zatrzymaj kontener (`docker compose stop app`) i skopiuj `./data/`,
- reset: `docker compose down && sudo rm -rf data`.

Przydatne: `docker compose logs -f app`, `docker compose up -d --build` po zmianach w kodzie.

### Uwaga bezpieczeństwa

Aplikacja montuje `/var/run/docker.sock` hosta (tak uruchamia sandbox) — to dostęp równoważny rootowi
na hoście. Ruch idzie po zwykłym HTTP. Używaj tylko w zaufanej sieci i tylko do demo.
