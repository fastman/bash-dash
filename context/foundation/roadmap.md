---
project: bash-dash
version: 1
status: draft                    # draft | active | locked
created: 2026-09-29
updated: 2026-09-29
prd_version: 1
main_goal: speed
top_blocker: time
---

# Roadmap: bash-dash

> Derived from `context/foundation/prd.md` (v1) + auto-researched codebase baseline.
> Edit-in-place; archive when superseded.
> Slices below are listed in dependency order. The "At a glance" table is the index.

## Vision recap

Firma ma niszowe stoisko na hackathonie i chce zainteresować uczestników rekrutacją. Uczestnik
skanuje kod QR, przez 5 minut rozwiązuje zadania w bashu na telefonie, dostaje miejsce w rankingu
i 6-cyfrowy kod do odbioru nagrody, a ranking (Hall of fame) na ekranie przy stoisku buduje
rywalizację. Twardy termin: wydarzenie 2026-10-03, więc kolejność jest podporządkowana
najkrótszej ścieżce przez wymagania konieczne (`main_goal: speed`), a główne ryzyko to czas.

## North star

**S-01: Gracz wpisuje komendę, sandbox ją wykonuje, a gracz widzi wynik weryfikacji** — to
najmniejszy przepływ od początku do końca, który dowodzi, że gra w ogóle działa: bez bezpiecznego
wykonania komendy w utwardzonym kontenerze nie ma produktu, a to też największa niewiadoma
techniczna (integracja, utwardzenie, ok. 6 s na komendę).

> „North star” (gwiazda przewodnia) oznacza tu najmniejszy kawałek od początku do końca, którego
> dostarczenie potwierdza, że produkt ma sens. Stawiamy go tak wcześnie, jak pozwalają zależności,
> bo reszta ma znaczenie tylko wtedy, gdy on działa.

## At a glance

| ID   | Change ID                     | Outcome (user can …)                                                                                     | Prerequisites | PRD refs                                    | Status   |
| ---- | ----------------------------- | -------------------------------------------------------------------------------------------------------- | ------------- | ------------------------------------------- | -------- |
| F-01 | sandbox-image-and-task-cut    | (foundation) obraz sandboxa zbudowany, zadania główne przetestowane pod utwardzeniem, niedziałające wycięte | —             | NFR (izolacja komend), FR-004               | done     |
| F-02 | event-vm-deploy               | (foundation) aplikacja działa na docelowej VM pod HTTPS, z kopią bazy poza VM i przećwiczonym odtworzeniem | —             | NFR (trwałość ~5 min), NFR (mobilna przeglądarka) | blocked  |
| S-01 | first-sandboxed-command       | gracz podaje nick, startuje i rozwiązuje zadania po kolei komendami wykonywanymi w sandboxie             | F-01          | US-01, FR-002, FR-003, FR-004, FR-005       | done     |
| S-02 | server-side-time-limit        | gracz widzi pozostały czas, po odświeżeniu wraca do tej samej sesji, a gra kończy się po 5 min lub po wszystkich zadaniach | S-01          | US-01, FR-006, FR-007                       | done |
| S-03 | summary-with-prize-code       | gracz po zakończeniu gry widzi liczbę zadań, podejść, miejsce w rankingu i unikalny 6-cyfrowy kod        | S-02          | US-01, FR-008                               | done     |
| S-04 | staff-code-lookup-and-prize   | obsługa loguje się hasłem, znajduje wynik po kodzie i oznacza „nagroda wydana”                          | S-03          | US-01, FR-011, FR-013                       | proposed |
| S-05 | hall-of-fame-screen           | obsługa wyświetla auto-odświeżany ranking top N z ostatnimi wynikami i ukrywa nicki (dyskwalifikacja)   | S-03          | US-01, FR-010, FR-012                       | proposed |
| S-06 | qr-token-gate                 | gracz może zacząć grę tylko po zeskanowaniu aktualnego, rotującego QR z ekranu rankingu                 | S-01, S-05    | US-01, FR-001, FR-017                       | proposed |

## Streams

Navigation aid — groups items that share a Prerequisites chain. Canonical ordering still lives in the dependency graph below; this table is the proposed reading order across parallel tracks.

| Stream | Theme                     | Chain                                  | Note                                                                                     |
| ------ | ------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------- |
| A      | Rozgrywka gracza          | `F-01` → `S-01` → `S-02` → `S-03`      | Najkrótsza ścieżka do pełnej sesji z kodem; ryzyko sandboxa zdejmowane na samym początku. |
| B      | Stoisko i ekran           | `S-04` / `S-05` → `S-06`               | Dołącza do Stream A w `S-03`; `S-04` i `S-05` mogą iść równolegle.                        |
| C      | Infrastruktura wydarzenia | `F-02`                                 | Niezależny od A i B; do zrobienia równolegle, gdy tylko rozstrzygnie się hosting (OQ 5). |

## Baseline

What's already in place in the codebase as of `2026-09-29` (auto-researched + user-confirmed).
Foundations below assume these are present and do NOT re-scaffold them.

- **Frontend:** absent — brak szablonów i plików statycznych; jest tylko standardowy Django admin.
- **Backend / API:** partial — szkielet Django 6.1 (`config/`), `config/urls.py` routuje tylko `admin/`, brak aplikacji.
- **Data:** partial — SQLite skonfigurowany (`config/settings.py:75`), brak własnych modeli i migracji.
- **Auth:** partial — `django.contrib.auth` i admin zainstalowane (logowanie obsługi hasłem dostępne), brak tokenu QR dla graczy.
- **Deploy / infra:** absent — brak konfiguracji kontenera, CI i reverse proxy; `tech-stack.md`: self-host na jednej VM, GitHub Actions, ręczna promocja wdrożeń.
- **Observability:** absent — brak konfiguracji logowania i śledzenia błędów.
- **Sandbox (dodatkowo):** absent — moduł cmdchallenge nie jest jeszcze skopiowany do repo.

## Foundations

### F-01: Obraz sandboxa i wycięcie niedziałających zadań

- **Outcome:** (foundation) obraz sandboxa z zestawem głównym zadań buduje się z repo; wzorcowe rozwiązania wszystkich zadań zostały uruchomione pod docelowym utwardzeniem, a zadania, które nie przechodzą, są wycięte z listy.
- **Change ID:** sandbox-image-and-task-cut
- **PRD refs:** NFR (izolacja komend, ≤ ok. 6 s), FR-004, Guardrail (fork bomba nie blokuje innych), Non-Goals (tylko zestaw główny; niedziałające zadania wycinamy), Open Question 4
- **Unlocks:** S-01; rozstrzyga Open Question 4 („Które z 42 zadań wyciąć?”); ścieżka weryfikacji „fork bomba / pętla / zajęcie pamięci nie wpływa na innych”.
- **Prerequisites:** —
- **Parallel with:** F-02
- **Blockers:** —
- **Unknowns:**
  - Architektura docelowej VM (amd64 czy arm64), pod którą budujemy obraz? — Owner: user. Block: no (przy przycięciu zakresu wystarczy jedna; można zacząć od lokalnej).
- **Risk:** idzie pierwsze, bo S-01 (north star) bez niego nie ruszy, a test pod utwardzeniem może wyciąć część zadań; gdyby wyszło to dopiero przy S-01, zmieniałoby zakres gry w ostatniej chwili.
- **Status:** done

### F-02: Wdrożenie na VM wydarzenia z kopią bazy

- **Outcome:** (foundation) aplikacja jest wdrożona na docelowej VM pod domeną z HTTPS, baza jest kopiowana poza VM co kilka minut, a odtworzenie VM ze snapshotu razem z bazą z kopii zostało raz przećwiczone.
- **Change ID:** event-vm-deploy
- **PRD refs:** NFR (awaria traci najwyżej ok. 5 min wyników), NFR (pełna gra w mobilnej przeglądarce na danych komórkowych), Guardrail (ranking i kody przetrwają awarię), Open Question 5
- **Unlocks:** ścieżka weryfikacji „pełna gra na telefonie przez dane komórkowe” dla S-01…S-06; ścieżka weryfikacji „wyniki i kody przetrwają odtworzenie” dla S-03 i S-04; S-06 (QR musi prowadzić pod publiczny adres).
- **Prerequisites:** —
- **Parallel with:** F-01, S-01, S-02, S-03, S-04, S-05
- **Blockers:** —
- **Unknowns:**
  - Hosting VM i domena (Open Question 5). — Owner: user. Block: yes.
- **Risk:** zrobione wcześnie, bo test na prawdziwych telefonach i próba odtworzenia wymagają publicznego adresu, a na ostatni dzień zostawić tego nie można; wdrażanie jest ręczne, więc merge w trakcie wydarzenia nie przerwie gier.
- **Status:** blocked

## Slices

### S-01: Pierwsza komenda wykonana w sandboxie

- **Outcome:** gracz czyta zasady, podaje nick, klika „Start” i rozwiązuje zadania po kolei, wpisując komendy wykonywane w sandboxie; widzi wyjście i informację „poprawne/niepoprawne”, a każda komenda zwiększa licznik podejść.
- **Change ID:** first-sandboxed-command
- **PRD refs:** US-01, FR-002, FR-003, FR-004, FR-005, NFR (izolacja komend)
- **Prerequisites:** F-01
- **Parallel with:** F-02
- **Blockers:** —
- **Unknowns:**
  - Czy wykonywanie komendy w osobnym kontenerze mieści się w ok. 1 s przy kilkunastu równoczesnych graczach? — Owner: team. Block: no (PRD akceptuje opóźnienie; do zmierzenia w tym kawałku).
- **Carry-overs z F-01 (przegląd implementacji, F9):**
  - (a) `reap_stale()` przy starcie ściga się z trwającymi uruchomieniami, jeśli startuje go wiele workerów lub procesów — wywoływać raz (jeden hook startowy lub blokada), nie w każdym workerze.
  - (b) Pula połączeń docker-py ma 10 połączeń; ponad ok. 10 równoczesnych `run_command` na wspólnym kliencie czeka w kolejce — dobrać pulę lub limit współbieżności do liczby workerów.
  - (c) `run_command` wywołuje `images.get` przy każdej komendzie; można to zbuforować po pierwszym sukcesie (obraz zmienia się tylko przy wdrożeniu).
  - (d) `catalog.get(slug)` zwraca też zadania wycięte — S-01 musi serwować zadania z `catalog.main_set()`.
- **Risk:** north star i największa niewiadoma; idzie tak wcześnie, jak pozwala F-01, żeby problemy z integracją lub wydajnością sandboxa wyszły w pierwszym dniu, a nie w ostatnim.
- **Status:** done

### S-02: Limit 5 minut pilnowany przez serwer

- **Outcome:** gracz widzi pozostały czas, po odświeżeniu strony wraca do tej samej sesji z tym samym czasem, a gra kończy się po 5 minutach od „Start” lub po rozwiązaniu wszystkich zadań; komendy wysłane po czasie się nie liczą.
- **Change ID:** server-side-time-limit
- **PRD refs:** US-01, FR-006, FR-007, Guardrail (nie da się wydłużyć ani zresetować limitu)
- **Prerequisites:** S-01
- **Parallel with:** F-02
- **Blockers:** —
- **Unknowns:** —
- **Risk:** bez tego wynik nie jest uczciwy (zegar w telefonie, odświeżenie); wydzielone z S-01, żeby north star był jak najmniejszy.
- **Status:** done

### S-03: Podsumowanie z miejscem i kodem nagrody

- **Outcome:** gracz po zakończeniu gry widzi liczbę rozwiązanych zadań, liczbę podejść, swoje miejsce w rankingu i unikalny 6-cyfrowy kod.
- **Change ID:** summary-with-prize-code
- **PRD refs:** US-01, FR-008, Business Logic (kolejność: zadania ↓, podejścia ↑, czas do ostatniego rozwiązania ↑)
- **Prerequisites:** S-02
- **Parallel with:** F-02
- **Blockers:** —
- **Unknowns:** —
- **Risk:** zamyka pętlę gracza i wprowadza regułę rankingu, z której korzystają S-04 i S-05; unikalność kodu musi być gwarantowana, bo tylko po nim obsługa identyfikuje gracza.
- **Status:** proposed

### S-04: Obsługa weryfikuje kod i wydaje nagrodę

- **Outcome:** obsługa loguje się hasłem, wyszukuje wynik po 6-cyfrowym kodzie (nick, zadania, podejścia, miejsce, czas) i oznacza „nagroda wydana”.
- **Change ID:** staff-code-lookup-and-prize
- **PRD refs:** US-01, FR-011, FR-013
- **Prerequisites:** S-03
- **Parallel with:** S-05, F-02
- **Blockers:** —
- **Unknowns:**
  - Jakie są nagrody i czy zależą od miejsca (Open Question 2)? — Owner: user. Block: no (oznaczenie „wydana” działa niezależnie od rodzaju nagrody).
- **Risk:** spełnia główne kryterium sukcesu („każdy wydany kod da się zweryfikować”); tanie dzięki panelowi admina, więc nie ma powodu odkładać go za ekran rankingu.
- **Status:** proposed

### S-05: Ekran Hall of fame z moderacją nicków

- **Outcome:** obsługa wyświetla na ekranie przy stoisku automatycznie odświeżany ranking top N (miejsce, nick, zadania, podejścia) i listę ostatnio zakończonych gier, a ukryty przez nią nick znika z rankingu bez kasowania wyniku.
- **Change ID:** hall-of-fame-screen
- **PRD refs:** US-01, FR-010, FR-012
- **Prerequisites:** S-03
- **Parallel with:** S-04, F-02
- **Blockers:** —
- **Carry-overs z S-03 (przegląd implementacji, F2):** `game/views.py` `done` rozpakowuje `services.rank_of(game)` bez obsługi `None`; gdy S-05 doda filtr ukrytych nicków do rankingu, ukryty gracz przeładowujący `/done` dostanie 500 — dodać obsługę `None` w widoku i szablonie.
- **Unknowns:**
  - Rozmiar top N, liczba ostatnich wyników i częstotliwość odświeżania (Open Question 3). — Owner: user. Block: no (rozsądne wartości domyślne, do zmiany w trakcie).
- **Risk:** drugorzędne kryterium sukcesu (ruch przy stoisku), ale też miejsce na QR z S-06, więc musi powstać przed nim.
- **Status:** proposed

### S-06: Start gry tylko z aktualnego kodu QR

- **Outcome:** gracz może rozpocząć grę tylko po zeskanowaniu aktualnego, rotującego kodu QR widocznego na ekranie rankingu; wygasły lub brakujący token kończy się komunikatem „zeskanuj kod przy stoisku”, a obsługa ustawia czas ważności tokenu (0 = bez wygasania).
- **Change ID:** qr-token-gate
- **PRD refs:** US-01, FR-001, FR-017
- **Prerequisites:** S-01, S-05
- **Parallel with:** S-04
- **Blockers:** —
- **Unknowns:**
  - Domyślny czas ważności tokenu i częstotliwość rotacji QR (Open Question 6). — Owner: user. Block: no (PRD przyjmuje ok. 15 minut).
- **Risk:** na końcu, bo potrzebuje ekranu z S-05 i przepływu startu z S-01, a do tego czasu gra da się testować bez bramki; ustawienie 0 jest fallbackiem, gdyby ekran przy stoisku padł.
- **Status:** proposed

## Backlog Handoff

| Roadmap ID | Change ID                   | Suggested issue title                                      | Ready for `/10x-plan` | Notes                                           |
| ---------- | --------------------------- | ---------------------------------------------------------- | --------------------- | ----------------------------------------------- |
| F-01       | sandbox-image-and-task-cut  | Zbudować obraz sandboxa i wyciąć niedziałające zadania     | yes                   | Run `/10x-plan sandbox-image-and-task-cut`      |
| F-02       | event-vm-deploy             | Wdrożyć na VM wydarzenia z HTTPS, kopią bazy i odtworzeniem | no                    | Czeka na hosting VM i domenę (OQ 5)             |
| S-01       | first-sandboxed-command     | Gracz rozwiązuje zadania komendami w sandboxie             | no                    | Po F-01                                         |
| S-02       | server-side-time-limit      | Limit 5 minut pilnowany po stronie serwera                 | no                    | Po S-01                                         |
| S-03       | summary-with-prize-code     | Podsumowanie gry z miejscem i 6-cyfrowym kodem             | no                    | Po S-02                                         |
| S-04       | staff-code-lookup-and-prize | Obsługa wyszukuje kod i oznacza wydanie nagrody            | no                    | Po S-03                                         |
| S-05       | hall-of-fame-screen         | Ekran Hall of fame z ukrywaniem nicków                     | no                    | Po S-03                                         |
| S-06       | qr-token-gate               | Start gry tylko z aktualnego, rotującego QR                | no                    | Po S-01 i S-05                                  |

## Open Roadmap Questions

1. **Jakie jest status quo i jego koszt?** Pierwsze takie wydarzenie, brak danych o tym, jak stoisko radzi sobie bez gry. — Owner: user. Block: — (nie wpływa na kolejność).
2. **Jakie są nagrody?** Czy zależą od miejsca lub wyniku, czy są za sam udział? Termin: przed 2026-10-03. — Owner: user. Block: — (S-04 działa niezależnie).
3. **Rozmiar top N i liczba „ostatnich wyników” na ekranie, częstotliwość odświeżania.** Termin: w trakcie implementacji. — Owner: user. Block: — (S-05 startuje z wartościami domyślnymi).
4. **Które z 42 zadań wyciąć?** Zależy od testu wzorcowych rozwiązań pod utwardzeniem. Termin: przed 2026-10-03. — Owner: user. Block: — (rozstrzyga je F-01).
5. **Hosting VM i domena.** Termin: przed 2026-10-03. Blokuje wdrożenie. — Owner: user. Block: F-02.
6. **Domyślny czas ważności tokenu QR i częstotliwość jego rotacji.** Przyjęto ok. 15 minut, z możliwością zmiany przez obsługę. — Owner: user. Block: — (S-06 startuje z ok. 15 min).
7. **Jaki jest spodziewany szczytowy ruch (`target_scale.qps`)?** Brak w notatkach. — Owner: user. Block: — (wpływa na pomiar w S-01).
8. **Jaka jest spodziewana skala danych (`target_scale.data_volume`)?** Brak w notatkach. — Owner: user. Block: —.
9. **Architektura VM (amd64 czy arm64) dla obrazu sandboxa.** Wynika z wyboru hostingu (OQ 5). — Owner: user. Block: — (dotyczy F-01 i F-02; wystarczy jedna architektura).

## Parked

- **Miękka blokada drugiej gry w tej samej przeglądarce (FR-016)** — Why parked: nice-to-have przy `main_goal: speed` i 4 dniach na całość; duplikaty w czołówce obsługa ukrywa (FR-012), a nagroda przysługuje raz (FR-013).
- **CTA rekrutacyjne w grze** — Why parked: PRD §Non-Goals; rozmowa rekrutacyjna odbywa się przy stoisku.
- **Anti-cheat i wykrywanie AI** — Why parked: PRD §Non-Goals; wyciąganie odpowiedzi z systemu jest dozwolone.
- **Celowo ukryte odpowiedzi w stronie** — Why parked: PRD §Non-Goals.
- **Podpowiedzi, rozwiązania i linki do odpowiedzi w UI** — Why parked: PRD §Non-Goals.
- **Zadania spoza zestawu głównego (`12days`, `oops`, własne)** — Why parked: PRD §Non-Goals; niedziałające zadania wycinamy w F-01, a nie naprawiamy.
- **Wiele wydarzeń, konta i historia graczy** — Why parked: PRD §Non-Goals.
- **Publiczny ranking** — Why parked: PRD §Non-Goals; Hall of fame widzi tylko obsługa.
- **Zbieranie e-maili i innych danych osobowych** — Why parked: PRD §Non-Goals.
- **Ręczna korekta lub unieważnianie wyniku w panelu** — Why parked: PRD §Non-Goals; dyskwalifikacja przez ukrycie nicku (S-05).
- **Punkty za trudność i pomijanie zadań** — Why parked: PRD §Non-Goals.
- **Gwarancja wydajności przy tłoku** — Why parked: PRD §Non-Goals; ok. 1 s na komendę akceptowane.
- **Twarda blokada powtórnej gry** — Why parked: PRD §Non-Goals.

## Done

- **F-01: (foundation) obraz sandboxa z zestawem głównym zadań buduje się z repo; wzorcowe rozwiązania wszystkich zadań zostały uruchomione pod docelowym utwardzeniem, a zadania, które nie przechodzą, są wycięte z listy.** — Archived 2026-09-29 → `context/archive/2026-09-29-sandbox-image-and-task-cut/`. Lesson: —.
- **S-01: gracz czyta zasady, podaje nick, klika „Start” i rozwiązuje zadania po kolei, wpisując komendy wykonywane w sandboxie; widzi wyjście i informację „poprawne/niepoprawne”, a każda komenda zwiększa licznik podejść.** — Archived 2026-09-29 → `context/archive/2026-09-29-first-sandboxed-command/`. Lesson: —.
- **S-02: gracz widzi pozostały czas, po odświeżeniu strony wraca do tej samej sesji z tym samym czasem, a gra kończy się po 5 minutach od „Start” lub po rozwiązaniu wszystkich zadań; komendy wysłane po czasie się nie liczą.** — Archived 2026-09-29 → `context/archive/2026-09-29-server-side-time-limit/`. Lesson: —.
- **S-03: gracz po zakończeniu gry widzi liczbę rozwiązanych zadań, liczbę podejść, swoje miejsce w rankingu i unikalny 6-cyfrowy kod.** — Archived 2026-09-29 → `context/archive/2026-09-29-summary-with-prize-code/`. Lesson: —.
