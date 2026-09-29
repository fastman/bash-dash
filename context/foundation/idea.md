# bash-dash — pomysł projektu

> Dokument wejściowy do `/10x-shape`. Podsumowuje całą rozmowę, w której omówiliśmy pomysł
> (sesja w katalogu `~/src/cmdchallenge`, 2026-09-29). Zawiera kontekst, podjęte decyzje z
> uzasadnieniem, odrzucone alternatywy oraz szczegóły techniczne kodu źródłowego, z którego
> korzystamy.

## 1. Kontekst i cel

- Bierzemy udział w hackathonie jako **firma partnerska**. Mamy własne stoisko. Celem jest
  zainteresowanie uczestników firmą i **zachęcenie ich do aplikowania** (rekrutacja).
- Pomysł: mały **side-quest** dla uczestników hackathonu. To nie jest główne zadanie wydarzenia,
  a nasze stoisko jest raczej niszowe, więc spodziewamy się umiarkowanego ruchu (dziesiątki,
  najwyżej kilkaset osób w ciągu wydarzenia).
- Uczestnik wchodzi na prostą stronę, rozwiązuje zadania z linuksowego shella (bash) przez
  **5 minut** i dostaje wynik. Wynik ma być nie tylko dobrze/źle, ale **lepiej/gorzej**, bo
  budujemy **ranking** („Hall of fame”) wyświetlany jako dashboard przy stoisku.
- Na koniec uczestnik dostaje **tajny kod** (6 cyfr), z którym podchodzi do stoiska po
  nagrodę. Obsługa stoiska musi móc **zweryfikować wynik** po tym kodzie.
- Interfejs może być **bardzo prosty**.

## 2. Inspiracja i źródło: cmdchallenge

- Bazą jest projekt **cmdchallenge** (strona https://cmdchallenge.com/). Są w nim łamigłówki
  w shellu: użytkownik wpisuje **jedną komendę**, a serwer uruchamia ją w izolowanym
  kontenerze Docker i sprawdza wynik.
- Lokalny klon: `~/src/cmdchallenge` (upstream: gitlab.com/jarv/cmdchallenge), commit
  `09a3d7ad1d6ca78bc3ad90c5bf7dda85b1087a42`.
- **Licencja MIT** (Copyright (c) 2017-2020 john@jarv.org). Kopiując kod, trzeba zachować
  plik LICENSE i informację o prawach autorskich (np. `sandbox/LICENSE` plus wzmianka w README).

### 2.1 Architektura oryginału (wynik analizy)

- **Frontend:** vanilla JS SPA w `site/` (`main.js`, `index.html`, `sass/`), oparty na jQuery,
  jquery.terminal, routie, commonmark i highlight.js, budowany Vite. Zestaw zadań wybiera
  subdomena (`oops.`, `12days.`).
- **Backend:** Go 1.24, `cmdchallenge/cmd/runcmd/runcmd.go`, port `:8181`. Endpointy:
  - `POST /c/r`: uruchom komendę (pola `slug`, `cmd` w base64)
  - `GET /c/s?slug=`: najczęstsze poprawne rozwiązania innych użytkowników
  - `/metrics`: Prometheus
  - `/debug/pprof/`
  - statyki
- **Persistencja:** SQLite (`internal/store/sqlstore.go`) jako cache wyników według
  (cmd, slug, version). Brak kont i sesji; postęp użytkownika jest w `localStorage`.
- **Deployment:** `docker-compose.yml` z serwisami `cmd`, `cmd-no-bin`, `runcmd` i `caddy`.
  Produkcja działa na jednej maszynie (`bin/deploy`: docker save, scp, docker load, systemd).
  Terraformu i usług chmurowych nie ma.

### 2.2 Zadania (challenges)

- Źródło prawdy to `cmdchallenge/internal/challenge/challenges.yaml`, wbudowany w binarkę Go
  (`go:embed`). Kopia dla frontendu jest w `site/challenges.json`.
- Format YAML (opisany w komentarzu na górze pliku) ma pola: `slug`, `version`, `dir` (domyślnie
  = slug), `img`, `description` (markdown/HTML), `disp_title`, `example` (wzorcowe rozwiązanie),
  `expected_output` (`lines`, `order`, `ignore_non_matching`, `re_sub`, `regex`),
  `expected_failures`, `completions`, `tags`, `emoji`, `learn`, `author`.
- Jest **59 zadań** w 3 zestawach:
  - **zestaw główny: 42 zadania bez tagów**, od `hello_world` do `IPv4_listening_ports`, ułożone
    mniej więcej od najłatwiejszego do najtrudniejszego;
  - `12days`: 12 zadań;
  - `oops`: 5 zadań, na obrazie `cmd-no-bin` z usuniętymi `/bin` i `/usr/bin`.
- Kolejność zestawu głównego w YAML: hello_world, current_working_directory, list_files,
  print_file_contents, last_lines, create_file, create_directory, copy_file, move_file,
  create_symlink, delete_files, remove_files_with_extension, find_string_in_a_file,
  search_for_files_containing_string, search_for_files_by_extension,
  search_for_string_in_files_recursive, extract_ip_addresses, count_files, simple_sort,
  count_string_in_line, split_on_a_char, print_number_sequence, replace_text_in_files,
  sum_all_numbers, just_the_files, remove_extensions_from_files, replace_spaces_in_filenames,
  dirs_containing_files_with_extension, files_starting_with_a_number, print_nth_line,
  reverse_readme, remove_duplicate_lines, find_primes, print_common_lines, print_line_before,
  print_files_if_different, nested_dirs, find_tabs_in_a_file, remove_files_without_extension,
  remove_files_with_a_dash, print_sorted_by_key, IPv4_listening_ports.
- Pliki fixture dla zadań leżą w `cmdchallenge/var/challenges/<dir>/` i są wbudowane w obraz
  (`ADD var/ /var/`). Katalog roboczy komendy to `/var/challenges/<dir>`.

### 2.3 Piaskownica: to przejmujemy bez zmian

Najcenniejsza część oryginału to **uruchamianie komendy i sprawdzanie odpowiedzi**, które
dzieje się **w całości wewnątrz kontenera**:

- `cmdchallenge/Dockerfile-cmd` buduje obraz Ubuntu 22.04. W środku jest binarka Go `runcmd`
  (`/usr/local/bin/runcmd`), pakiety `jq bc rename bsdmainutils man file` oraz `var/challenges`.
- Wywołanie z hosta (`internal/challenge/runner.go:95-155`):

  ```
  docker run --network none --memory 100m -w /var/challenges/<dir> cmd:<arch> \
      runcmd -cmd -slug <slug> <komenda zakodowana w base64>
  ```

- Wewnątrz kontenera `runcmd -cmd` (`internal/runcmd/runcmd.go`) robi cztery rzeczy:
  - uruchamia `bash -O globstar -c <cmd>` z **timeoutem 5 s** (SIGKILL na grupę procesów);
  - porównuje wyjście z `expected_output`;
  - uruchamia **randomizery** (`internal/challenge/randomizers.go`, ok. 250 linii): ponownie
    wykonuje komendę na zmienionych danych, żeby nie przechodziło `echo <oczekiwany wynik>`;
  - wykonuje **specjalne sprawdzenia** dla części zadań (`internal/challenge/checks.go`, ok.
    500 linii), np. stanu plików lub procesów.
- Wynik trafia na **stdout jako JSON** (struktura `CmdResponse` w
  `internal/challenge/server.go:34`, klucze to nazwy pól Go, wszystkie opcjonalne):
  `{"Correct": bool, "Output": str, "Error": str, "ErrorInternal": str, "ExitCode": int}`.
  Niezerowy kod wyjścia kontenera oznacza błąd wewnętrzny.
- Timeout całego kontenera po stronie hosta wynosi 6 s (`internal/config/config.go`).
- Oszacowanie opóźnienia: od kilkuset ms do ok. 1 s na komendę (tworzenie i start kontenera).
  To szacunek, nie pomiar. Przy randomizerach komenda wykonuje się drugi raz.
- **Decyzja:** nie przepisujemy tej logiki (checks i randomizery) do Pythona. Kopiujemy moduł
  Go razem z `Dockerfile-cmd` i `var/` do katalogu `sandbox/` i budujemy z niego obraz. Backend
  w Pythonie tylko uruchamia kontener i czyta JSON. Tryb serwerowy binarki Go nie jest używany.

### 2.4 Znalezione problemy w oryginale (istotne dla nas)

**Bezpieczeństwo:**
- Serwer ma dostęp do `/var/run/docker.sock`, co w praktyce oznacza roota na hoście.
- Kontenery gracza działają jako root i nie mają `PidsLimit`, `CapDrop`, `ReadonlyRootfs` ani
  limitu CPU, więc fork bomba i zajęcie CPU są możliwe.
- Kontenery są usuwane tylko przy timeoucie; po poprawnym zakończeniu zostają i się gromadzą.
- `/metrics` i `/debug/pprof` są publicznie dostępne. Rate limit za reverse proxy może
  traktować wszystkich jako jeden adres IP.

**Źródła odpowiedzi:**
- `site/challenges.json` jest w paczce JS i zawiera `example` (wzorcowe rozwiązanie) oraz
  `expected_output`. Widać to w devtools.
- UI ma okienko „solutions” (`/c/s`) z rozwiązaniami innych graczy.
- W stopce jest link do repozytorium na GitLabie.
- `challenges.yaml` jest wbudowany w binarkę `runcmd` w kontenerze, więc `strings` wyciągnie
  odpowiedzi z wnętrza zadania.
- Zadania są publiczne od lat, rozwiązania łatwo znaleźć w internecie, a ChatGPT/Claude
  rozwiąże je od ręki.

## 3. Decyzje: filozofia i uczciwość

- **Nie walczymy z „oszukiwaniem”.** To świadoma decyzja.
  - Kto odkryje, że odpowiedzi są w kodzie strony, ma z tego skorzystać: to dobry kandydat do
    pracy. Odpowiedzi mogą pozostać „do odkrycia” (np. w pliku JSON ładowanym przez
    frontend) jako **ukryta nagroda dla dociekliwych**. W nowym frontendzie trzeba je tam
    umieścić **celowo**, bo przy przepisaniu nie znajdą się tam same z siebie. Wyciąganie ich
    przez `strings` z binarki w kontenerze też jest w porządku.
  - Kto zna zadania z cmdchallenge, dobrze rokuje i może błysnąć.
  - Korzystanie z ChatGPT/Claude jest dozwolone. Sprawne używanie AI to plus, a przy limicie
    czasu kopiowanie i wklejanie i tak nie da świetnego wyniku.
- **Usuwamy tylko bezpośrednie linki do odpowiedzi:** link do repozytorium na GitLabie/GitHubie,
  okienko z rozwiązaniami innych graczy (`/c/s`), wszelkie „show solution”. Na stronie nie
  może być żadnego linku prowadzącego do odpowiedzi.
- **Blokujemy dostęp z publicznego internetu**, żeby przypadkowi anonimowi gracze nie wbijali
  kosmicznych wyników. Mechanizm: **kod QR z tokenem wydarzenia** (sekcja 4.1).
- Bezpieczeństwo: stoisko jest niszowe, więc nie spodziewamy się intensywnych ataków.
  Uczestnicy hackathonu na pewno jednak spróbują coś zepsuć. Wystarczy:
  - uruchomić całość w **maszynie wirtualnej ze snapshotem** (łatwe przywrócenie);
  - dodać tanie utwardzenie kontenerów (sekcja 5.3);
  - robić **kopię bazy poza VM**, bo przywrócenie snapshotu inaczej skasowałoby ranking.

## 4. Decyzje: rozgrywka i funkcje

### 4.1 Wejście
- Uczestnik skanuje **kod QR przy stoisku**. Adres zawiera **tajny token wydarzenia**
  (np. `https://…/?t=<token>`). Bez tokenu nie da się rozpocząć gry. Rozwiązanie działa też na
  danych komórkowych, bez zależności od Wi-Fi organizatora.
  - Odrzucone: lista dozwolonych IP sieci wydarzenia (trzeba je znać wcześniej, a osoby na
    LTE by nie weszły) oraz praca wyłącznie w sieci lokalnej przy stoisku (zależność od Wi-Fi).
- Ekran startowy: pole **nick** (wymagane), opcjonalnie **e-mail**. Innych danych nie zbieramy.
- Na ekranie startowym **wprost opisujemy zasady**: 5 minut, zadania po kolei, każda wpisana
  komenda liczy się jako podejście, mniej podejść jest lepiej.
- Po kliknięciu „Start” serwer zakłada **sesję** i zapisuje czas startu.

### 4.2 Quiz
- Zadania to **42 z zestawu głównego**, w oryginalnej kolejności (od łatwych do trudnych).
  Bez `12days` i `oops`, bo są mniej przewidywalne pod względem trudności.
- **Stała kolejność, bez pomijania.** Dopóki zadanie nie jest rozwiązane poprawnie, gracz nie
  przechodzi dalej. Kto utknie, zostaje na tym zadaniu do końca czasu.
- **Każda wpisana komenda to podejście**, także rozpoznawcze (`ls`, `cat plik`). W cmdchallenge
  nie ma osobnego przycisku „wyślij”: każda komenda jest od razu odpowiedzią. Działa to jak
  code golf i nagradza myślenie przed pisaniem.
  - Odrzucone: osobny „tryb podglądu”, w którym komenda się wykonuje, ale nie liczy się jako
    podejście (więcej pracy, trudniejsze do wytłumaczenia).
- Limit wynosi **5 minut**, liczony **po stronie serwera** od startu sesji. Licznik w
  przeglądarce jest tylko informacyjny. Odświeżenie strony nie resetuje czasu, a gra jest
  kontynuowana w tej samej sesji. Komendy wysłane po upływie czasu nie są liczone.
- Quiz kończy się po 5 minutach **albo** po rozwiązaniu wszystkich 42 zadań (mało
  prawdopodobne). Wtedy gracz trafia na ekran podsumowania.
- UI jak w cmdchallenge: opis zadania plus terminal (jquery.terminal albo prostsze pole z
  historią), widoczne wyjście komendy i informacja, czy było poprawne.

### 4.3 Punktacja i ranking
1. **Liczba rozwiązanych zadań**, malejąco.
2. Przy remisie **liczba podejść** (wszystkich wysłanych komend), rosnąco.
3. Przy dalszym remisie **czas ostatniego poprawnego rozwiązania** liczony od startu sesji,
   rosnąco. To propozycja, żeby rozstrzygać remisy deterministycznie.

Rozszerzamy punktację tylko o te kryteria. Nie ma punktów za trudność zadania.

### 4.4 Ekran podsumowania
- Liczba rozwiązanych zadań, liczba podejść, **miejsce w rankingu**.
- **Unikalny, losowy kod 6-cyfrowy**, przypisany do tej sesji i zapisany w bazie. Z nim gracz
  idzie do stoiska po nagrodę. Później po tym kodzie identyfikujemy użytkowników, np. prosimy
  o podanie 6-cyfrowego numeru.
- Warto dodać CTA rekrutacyjne (np. „Aplikuj do nas: …”). Treść jest do ustalenia.

### 4.5 Hall of fame (dashboard)
- Osobna strona z rankingiem, **automatycznie odświeżana**, do wyświetlenia na ekranie przy
  stoisku. Pokazuje top N: miejsce, nick, liczbę zadań i liczbę podejść.
- Nie pokazuje e-maili ani kodów.
- Nie pokazuje ukrytych (zmoderowanych) nicków.

### 4.6 Panel admina (obsługa stoiska)
- Dostęp chroniony hasłem, np. **Django admin**.
- **Wyszukiwanie po kodzie 6-cyfrowym:** nick, e-mail, wynik, podejścia, miejsce, czas.
- **Moderacja nicków jest konieczna:** ukrycie nicku z Hall of fame bez kasowania wyniku (albo
  podmiana nicku).
- Przydatne: oznaczenie „nagroda wydana”, ręczne unieważnienie lub korekta wyniku.

### 4.7 Jedno podejście na osobę
- **Nice to have.** Najlepiej zablokować drugie podejście. Bez kont da się to zrobić tylko
  „miękko”: znacznik w przeglądarce (cookie lub localStorage), ewentualnie unikalność nicku.
  Tryb incognito to obejdzie, co przy tej skali akceptujemy.

### 4.8 Dane osobowe
- Zbieramy tylko nick i opcjonalny e-mail. Nie chcemy rozbudowanych procedur RODO.
- Jeśli zostanie pole e-mail, wystarczy przy nim krótka informacja o celu. Uwaga: e-mail to dane
  osobowe; nick raczej nie.

## 5. Decyzje techniczne

### 5.1 Nowy projekt zamiast forka
- **Nowy projekt w Pythonie** (autor zna go lepiej niż Go) na **Django**.
- Uzasadnienie wyboru Django zamiast FastAPI: **Django admin za darmo** (wyszukiwanie po kodzie,
  moderacja nicków, „nagroda wydana”). Tego obsługa stoiska potrzebuje w trakcie wydarzenia.
- Z cmdchallenge dziedziczymy tylko **zadania** i **piaskownicę kontenerową** (sekcja 2.3).
  Backendu w Go, cache rozwiązań, obsługi subdomen i Prometheusa nie przenosimy.
- Odrzucone:
  - **czysty fork:** zmiany w Go, którego autor zna słabiej, plus balast niepotrzebnych funkcji;
  - **przepisanie od zera, łącznie ze sprawdzaniem:** checks i randomizery to ok. 750 linii
    żmudnej, podatnej na błędy logiki, która nie daje nic nowego.

### 5.2 Proponowana struktura
- `sandbox/`: skopiowany moduł Go z cmdchallenge (`cmdchallenge/` z `cmd/`, `internal/`,
  `var/`, `go.mod`, `Dockerfile-cmd`) plus LICENSE. Służy tylko do zbudowania obrazu `cmd`.
  Zmiany minimalne albo żadne.
- Aplikacja Django:
  - modele: sesja/gracz (nick, e-mail, kod, start, koniec, liczba rozwiązanych, liczba podejść,
    czas ostatniego rozwiązania, ukryty, nagroda wydana), opcjonalnie log podejść (komenda,
    slug, poprawność, czas);
  - endpointy: start sesji (token + nick), stan sesji (bieżące zadanie, pozostały czas),
    wysłanie komendy, podsumowanie, dane rankingu;
  - wywołanie kontenera przez bibliotekę `docker` (Python SDK);
  - lista zadań, opisy i kolejność czytane z tego samego `challenges.yaml` (filtr: brak tagów).
- Frontend: proste strony serwowane przez Django (start, quiz z terminalem, podsumowanie,
  Hall of fame). Mogą to być szablony Django plus trochę JS.
- Bez cache wyników według (cmd, slug). Każde podejście się liczy, więc komendę można po
  prostu wykonać. Ewentualny cache to optymalizacja na później.

### 5.3 Utwardzenie piaskownicy (tanie, do zrobienia)
- Parametry kontenera:
  - `network_mode="none"` i limit pamięci (jak w oryginale);
  - **`pids_limit`** (ochrona przed fork bombą);
  - **limit CPU** (`nano_cpus`);
  - **`cap_drop=["ALL"]`**, jeśli nie psuje zadań (do sprawdzenia);
  - **usuwanie kontenera po zakończeniu** (`remove`/`auto_remove`);
  - timeout po stronie hosta ok. 6 s i kill kontenera.
- Limit długości komendy: 300 znaków (jak w oryginale).
- Rate limit per sesja, np. jedna komenda na raz i minimalny odstęp.
- Brak publicznych endpointów diagnostycznych.
- Aplikacja ma dostęp do `docker.sock`, więc całość działa w **dedykowanej VM**.

### 5.4 Deployment
- **Jedna VM** (np. w chmurze), na której działa tylko ta aplikacja. Snapshot przed
  wydarzeniem pozwala szybko przywrócić maszynę.
- Baza SQLite wystarczy. **Kopia pliku bazy co kilka minut poza VM**, żeby snapshot nie
  kasował rankingu.
- HTTPS (np. Caddy jako reverse proxy).
- Obsługa architektury amd64/arm64 jak w oryginale (`BUILD_ARCH`).

## 6. Otwarte kwestie (do doprecyzowania w /10x-shape)

- Treść CTA rekrutacyjnego i nagrody (czy zależą od miejsca/wyniku, czy są za udział).
- Czy e-mail zostaje (opcjonalny), czy rezygnujemy z niego całkiem.
- Czy nick musi być unikalny.
- Jak dokładnie zostawić „ukrytą nagrodę dla dociekliwych” (odpowiedzi w JSON dostępnym
  z frontendu). Czy i jak łatwo ma być je znaleźć.
- Rozmiar top N w Hall of fame i częstotliwość odświeżania. Czy wyróżniać świeże wyniki.
- Czy któreś z 42 zadań trzeba wyciąć lub przestawić, np. gdy wymaga uprawnień, które
  odbierzemy przez `cap_drop`, albo jest zbyt nieczytelne.
- Hosting VM (dostawca), domena, termin hackathonu i czas na przygotowanie.
