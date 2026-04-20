# ida-procon

> **ida** + **pro**cessed **con**tour — autonomous reverse engineering at scale.

*[Русская версия ниже](#ru)*

---

IDA Pro decompiles binaries. But what it gives you is thousands of `sub_XXXXX` functions with variables named `v1, v2, a3` — no structure, no context, no understanding of how they relate. Manually tracing call graphs, renaming variables, and piecing together what a binary actually does takes weeks for anything non-trivial.

ida-procon closes that gap. You dump the binary once, close IDA, and never open it again. From that point, autonomous LLM agents work through the decompiled code in parallel — tracing calls, renaming variables, writing descriptions, and assembling the results into **contours**: named, annotated subgraphs that represent logical units of the binary.

```
20 agents in parallel = 690 contours, 2399 functions documented across 13 modules
Mixed fleet: Claude Opus + Sonnet + GPT via Codex CLI
```

## Benchmarks

Public benchmarks against Mandiant's Flare-On CTF. Both runs were fully autonomous — no human hints about content, solutions, or cultural references. Flags verified against official write-ups.

| Challenge | Year | Arch | Functions | Coverage | Time | Cost | Result |
|---|---|---|---|---|---|---|---|
| `checksum` (#2) | 2024 | Go / x86-64 | ~50 | 100% | 207s | ~$3 | Full crypto pipeline reconstructed |
| `Nur geträumt` (#10) | 2022 | Motorola 68K | 693 | 100% | ~80 min | ~$15 | Full coverage + autonomous flag recovery |

### Challenge 2 — `checksum` (Flare-On 11, 2024)

Golang binary. One Opus agent, 207 seconds, 49,738 tokens, 28 tool calls.

Recovered the complete runtime pipeline: math quiz gate → hex key input → XChaCha20-Poly1305 decrypt → SHA-256 self-consistency check → XOR+Base64 validation → JPG write to `%LocalAppData%`.

Notable: public CTF write-ups omit the XChaCha20-Poly1305 stage because it isn't required to extract the flag. The agent captured it anyway — procon reconstructs binary semantics, not just puzzle solutions.

### Challenge 10 — `Nur geträumt` (Flare-On 9, 2022)

Motorola 68K binary inside a classic Mac OS disk image. Per public write-ups, this challenge took finishers 2–3 weeks of manual work, including setting up Mini vMac with a custom ROM and using Super ResEdit to inspect resources visually.

**Phase 1 — coverage** (~44 min wall-clock, ~436k tokens):

- 4× Opus parallel batch — 1 completed (269k tokens), 3 rate-limited at ~15k each
- 3× Sonnet cleanup pass — added remaining 46 functions
- Result: 693 functions, 375 contours, 100% coverage

**Phase 2 — flag extraction** (~40 min, 1× Opus):

Agent worked entirely over the contour graph from Phase 1. Chain of reasoning:

1. Located `FL\x81G` resource id=128, 48 bytes, named `"99 Luftballons"`
2. Identified XOR cipher via `EOR.W` instruction in M68K disassembly
3. Inferred cultural context: resource name = Nena song; volume name `"Nur geträumt"` = another Nena song (cross-check)
4. Hypothesized passphrase = song lyrics, tested first line of "99 Luftballons": `Hast du etwas Zeit für mich?`
5. XOR produced readable plaintext = second line of the same song: `Dann singe ich ein Lied für dich@flare-on.com`
6. Found in-binary hint `"Remove the umlaut before submitting"` in DATA resource
7. Produced final flag: **`Dann_singe_ich_ein_Lied_fur_dich@flare-on.com`**

Verified against [Hasherezade's write-up](https://hshrzd.wordpress.com/2022/10/10/flare-on-9-task-10/) — exact match.

The agent performed no dynamic analysis and did not use an emulator. Reference solutions required Mini vMac setup, ROM sourcing, disk mounting, and visual resource inspection. Procon reached the same flag via static analysis of the disk image through IDA + contour graph alone.

### Why M68K matters

Hex-Rays pseudocode for legacy architectures (M68K, PowerPC, older MIPS) is thin in LLM training data. Empirically, agents reason more reliably on raw disassembly for these ISAs than on decompiler pseudocode — general assembly knowledge transfers across architectures, unfamiliar pseudocode dialects invite hallucination. The coverage phase used disassembly-first input for this reason.

**Production** — 948 functions documented across a 7,000-function industrial binary in **15 minutes with 6 parallel agents for $6**. Equivalent manual work: 4 engineers × 6 months.

## Why this is different

**You dump once and close IDA.** `ida_dump.py` connects to IDA's [MCP server](https://github.com/mrexodia/ida-pro-mcp), batch-decompiles every function with callees, xrefs, and metadata, and writes structured `.c` files. After that, all work happens through the coordinator API. IDA is not needed again.

**Agents understand what they're looking at.** You don't tell them "this is a numerical library." An agent reads `sub_664212F0`, sees matrix operations and factorization patterns in the callees, and writes: "Sparse Cholesky decomposition (LL^T) with skyline storage." It identifies algorithms, protocols, and design patterns on its own.

**Cross-module linking happens automatically.** When an agent analyzing one DLL sees a call into another, it switches `module=` in the API and reads the code from the other module. No need to reopen IDA with a different binary. The coordinator knows all loaded modules and serves them through the same API. Agents follow dependencies across DLLs as naturally as they follow local calls.

**A contour is not just a graph — it's ready-to-read source code.** The coordinator assembles full annotated source for any contour on demand via `/contour-code`: entry function first, then helpers in call order, each with role and description headers. You can read it as a single file, pass it to another agent, or use it as reference documentation.

**Scaling is trivial.** 1 agent or 20 — the coordinator handles conflicts through atomic claims with TTL. If an agent crashes, its locks auto-release. If two agents reach the same function, one gets a "borrowed" read-only copy. Tested with 20 simultaneous agents (Claude + GPT mixed fleet), zero conflicts.

## How it works

```
IDA Pro + ida-pro-mcp        ida_dump.py           Coordinator (:40000)
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
│ Decompiles binary │───▶│ Batch exports    │───▶│ Loads dump, tracks   │
│ via MCP server    │    │ all functions    │    │ coverage, serves API │
└──────────────────┘    │ with metadata    │    └──────────┬───────────┘
                        └──────────────────┘               │
                                                 ┌─────────┼─────────┐
                                                 ▼         ▼         ▼
                                              Agent     Agent     Agent
                                               │         │         │
                                            claim →   claim →   claim →
                                            trace →   trace →   trace →
                                            improve → improve → improve →
                                            submit    submit    submit
                                               │         │         │
                                               ▼         ▼         ▼
                                            contour   contour   contour
```

**Step 1 — Dump.** Open your binary in IDA Pro with [ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp). Run `ida_dump.py` — it pulls every function through the MCP server and writes structured `.c` files with callee/xref metadata headers. Close IDA.

**Step 2 — Coordinate.** Start the coordinator daemon. It loads the dump, creates a coverage graph (which functions are analyzed, which aren't), and serves a REST API on port 40000.

**Step 3 — Analyze.** Launch Claude Code agents. Each one autonomously: asks for the richest uncovered entry point → claims it → traces callees → improves the code → submits a contour. The sergeant skill (`/sergeant`) recommends how many agents to launch and generates ready-to-paste commands.

## What's a contour?

The name **procon** comes from **pro**cessed **con**tour — the core output unit.

A contour is a named subgraph of related functions that represent a single logical unit of the binary. Instead of a flat list of 7000 improved functions, you get structured groups like "sparse Cholesky decomposition", "COM IDispatch bridge", or "TLS slot manager".

```json
{
  "name": "sparse_cholesky@sub_664212F0",
  "summary": "Sparse Cholesky decomposition (LL^T/LDL^T) with skyline storage",
  "nodes": {
    "sub_664212F0": { "role": "entry",    "description": "Main factorization dispatcher" },
    "sub_6641FE90": { "role": "helper",   "description": "Rank-1 Givens rotation update" },
    "sub_66420E90": { "role": "borrowed", "description": "Skyline Cholesky (claimed by another agent)" }
  },
  "edges": [["sub_664212F0", "sub_6641FE90"], ["sub_664212F0", "sub_66420E90"]],
  "external_deps": [{ "name": "EnterCriticalSection", "module": "KERNEL32" }]
}
```

Roles: **entry** (root function), **helper** (called by entry), **leaf** (terminal), **micro** (≤10 lines, shared across contours), **borrowed** (claimed by another agent — read-only reference).

## Results

Tested on a real-world closed-source application (13 DLLs, 11600+ functions, no source code available):

| Module | Functions | Documented | Contours | Coverage |
|--------|-----------|------------|----------|----------|
| A.dll | 708 | 376 | 153 | 61.6% |
| B.dll | 147 | 31 | 16 | 60.8% |
| C.dll | 802 | 255 | 80 | 44.3% |
| D.dll | 1078 | 316 | 97 | 42.4% |
| E.exe | 971 | 284 | 69 | 34.0% |
| F.dll | 1265 | 248 | 80 | 30.3% |
| G.dll | 5307 | 696 | 115 | 13.3% |
| + 6 more modules | 1332 | 193 | 80 | — |
| **Total** | **11610** | **2399** | **690** | **25.4%** |

**What agents discovered** — with zero prior knowledge of the binary:
- G.dll is a statically linked numerical library — agents identified FFT, SVD, Cholesky factorization, curve fitting algorithms
- A.dll handles the main data processing pipeline: XML parsing, signal correction, data analysis
- E.exe orchestrates via Qt custom events across plugin DLLs
- D.dll communicates with hardware over TCP
- B.dll implements a license verification handshake
- Cross-module call paths were traced across 4 DLLs — through Qt event dispatch, COM/IDispatch, and DLL imports

## After analysis

Once contours are built, the coordinator becomes a **source server** for the entire binary:

**Assembled source code.** `GET /contour-code?module=X&name=Y` returns the full annotated source of a contour — entry function first, then helpers in call order, each preceded by a comment block with its role and description. This is not a JSON graph — it's readable `.c` code you can hand to a human or another agent.

**Cross-module navigation.** Every contour lists its `external_deps` — calls into other modules. Any agent (or script) can resolve them: `GET /func-code?module=algorithm&name=sub_664212F0` returns the code regardless of which DLL it came from. The coordinator already has all modules loaded. No need to switch IDA databases — just change the `module=` parameter.

**Feed it forward.** The contour-code endpoint turns ida-procon into a backend for downstream tools. Point another Claude Code agent at `API_READ.md`, give it the coordinator URL, and it can browse the entire reverse-engineered codebase through HTTP — reading contours, following cross-module calls, building higher-level understanding on top of what the soldiers already produced.

## Quickstart

### Prerequisites

- **IDA Pro 9.x** with [ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp) — exposes IDA's decompiler as an MCP server
- **Python 3.10+**
- **[Claude Code](https://claude.ai/code)** — the CLI that runs the agents

### 1. Dump from IDA

Open your binary in IDA, make sure ida-pro-mcp is running (default port 13337):

```bash
pip install requests
python ida_dump.py --port 13337 --module mylib --output dump
```

This decompiles all functions and writes them to `dump/mylib/raw_funcs/` with a `manifest.json` index. Close IDA after the dump completes.

### 2. Start the coordinator

```bash
cd coordinator
pip install -r requirements.txt
python main.py --port 40000 --dump-dir ../dump
```

The coordinator loads all modules from the dump directory and starts serving on port 40000.

### 3. Launch agents

Open Claude Code in the repo root:

```
/sergeant status          # coverage across all modules
/sergeant mylib           # get agent launch recommendations
```

The sergeant analyzes what's left to cover and gives you ready-to-paste commands for launching soldiers. Run as many in parallel as you want.

### 4. Read results

```bash
# list all contours with summaries
curl http://127.0.0.1:40000/contours?module=mylib

# get assembled source code for a contour
curl "http://127.0.0.1:40000/contour-code?module=mylib&name=sparse_cholesky@sub_664212F0"

# overall coverage stats
curl http://127.0.0.1:40000/status
```

## Agent hierarchy

```
You (Commander)
 └── /sergeant — analyzes coverage, recommends what to launch
      ├── Opus soldiers (Claude) — complex functions (200+ lines), ≥10 contours per session
      ├── Sonnet soldiers (Claude) — regular functions (11-200 lines), ≥5 contours per session
      └── GPT soldiers (Codex CLI) — regular functions, 1-2 contours per session, many in parallel
```

Claude soldiers are launched via the Agent tool and use Read/Edit for file access. GPT soldiers run non-interactively via `codex exec` and work entirely through the coordinator API. The Commander (you) only needs to launch them and monitor coverage.

## API

Full reference: **[API.md](API.md)** | Read-only reference: **[API_READ.md](API_READ.md)**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/status` | Coverage stats per module |
| `GET` | `/next-entry?module=X` | Richest uncovered function to analyze next |
| `GET` | `/contours?module=X` | All contours with summaries |
| `GET` | `/contour-code?module=X&name=Y` | Assembled annotated source for a contour |
| `GET` | `/func-code?module=X&name=Y` | Source code of a single function |
| `POST` | `/claim` | Atomically lock a function for editing |
| `POST` | `/submit-contour` | Submit a completed contour |

## Repo structure

```
ida-procon/
├── ida_dump.py                # Batch decompiler (IDA → structured .c files)
├── coordinator/               # FastAPI coordination daemon
│   ├── main.py                # Entry point (port 40000 by default)
│   ├── api/                   # REST endpoints (query + mutation)
│   ├── models/                # Pydantic schemas
│   ├── services/              # Claims, resolution, contour assembly
│   └── storage/               # File I/O layer
├── agents/                    # Agent instructions
│   ├── AGENTS.md              # Rules for all subagents
│   ├── sergeant/              # Orchestrator orders
│   └── soldiers/
│       ├── opus/              # Claude Opus — complex functions
│       ├── sonnet/            # Claude Sonnet — regular functions
│       └── gpt/               # GPT via Codex CLI — regular functions
├── .claude/skills/sergeant/   # Orchestration skill for Claude Code
├── CLAUDE.md                  # Commander instructions
├── API.md                     # Full API reference
├── API_READ.md                # Read-only API reference
└── LICENSE                    # MIT
```

## License

MIT

---

<a name="ru"></a>

# ida-procon (RU)

> **ida** + **pro**cessed **con**tour — автономный реверс-инжиниринг в масштабе.

---

IDA Pro декомпилирует бинарники. Но на выходе — тысячи функций `sub_XXXXX` с переменными `v1, v2, a3`. Никакой структуры, никакого контекста, никакого понимания связей. Ручная трассировка графов вызовов, переименование переменных и восстановление логики бинарника — это недели работы для чего-то нетривиального.

ida-procon закрывает этот разрыв. Вы дампите бинарник один раз, закрываете IDA и больше её не открываете. Дальше автономные LLM-агенты параллельно работают с декомпилированным кодом — трассируют вызовы, переименовывают переменные, пишут описания и собирают результаты в **контуры**: именованные, аннотированные подграфы, представляющие логические единицы бинарника.

```
20 агентов параллельно = 690 контуров, 2399 функций задокументировано в 13 модулях
Смешанный флот: Claude Opus + Sonnet + GPT через Codex CLI
```

## Бенчмарки

Публичные бенчмарки на задачах Mandiant Flare-On CTF. Оба прогона полностью автономны — без подсказок о содержании, решениях или культурных отсылках. Флаги верифицированы по официальным write-up'ам.

| Задача | Год | Архитектура | Функций | Покрытие | Время | Стоимость | Результат |
|---|---|---|---|---|---|---|---|
| `checksum` (#2) | 2024 | Go / x86-64 | ~50 | 100% | 207с | ~$3 | Полный крипто-пайплайн восстановлен |
| `Nur geträumt` (#10) | 2022 | Motorola 68K | 693 | 100% | ~80 мин | ~$15 | Полное покрытие + автономное извлечение флага |

### Задача 2 — `checksum` (Flare-On 11, 2024)

Golang-бинарник. Один агент Opus, 207 секунд, 49 738 токенов, 28 вызовов инструментов.

Восстановлен полный runtime-пайплайн: математическая проверка → ввод hex-ключа → XChaCha20-Poly1305 дешифровка → SHA-256 self-consistency check → XOR+Base64 валидация → запись JPG в `%LocalAppData%`.

Примечание: публичные write-up'ы пропускают стадию XChaCha20-Poly1305 — она не нужна для извлечения флага. Агент зафиксировал её самостоятельно — procon восстанавливает семантику бинарника, а не только ответы на задачи.

### Задача 10 — `Nur geträumt` (Flare-On 9, 2022)

Бинарник для Motorola 68K внутри образа диска классической Mac OS. Согласно публичным write-up'ам, финишёры тратили 2–3 недели ручной работы, включая настройку Mini vMac с кастомным ROM и визуальный осмотр ресурсов через Super ResEdit.

**Фаза 1 — покрытие** (~44 мин wall-clock, ~436k токенов):

- 4× Opus параллельно — 1 завершил (269k токенов), 3 срубило рейт-лимитом (~15k каждый)
- 3× Sonnet добивка — закрыли оставшиеся 46 функций
- Итог: 693 функции, 375 контуров, 100% покрытие

**Фаза 2 — извлечение флага** (~40 мин, 1× Opus):

Агент работал исключительно по графу контуров из фазы 1. Цепочка рассуждений:

1. Нашёл ресурс `FL\x81G` id=128, 48 байт, имя `"99 Luftballons"`
2. Определил XOR-шифр по инструкции `EOR.W` в дизассемблере M68K
3. Вывел культурный контекст: название ресурса = песня Nena; имя тома `"Nur geträumt"` = другая песня Nena (перекрёстная проверка)
4. Предположил пароль = текст песни, проверил первую строку "99 Luftballons": `Hast du etwas Zeit für mich?`
5. XOR дал читаемый plaintext = вторая строка той же песни: `Dann singe ich ein Lied für dich@flare-on.com`
6. Нашёл в DATA-ресурсе подсказку `"Remove the umlaut before submitting"`
7. Итоговый флаг: **`Dann_singe_ich_ein_Lied_fur_dich@flare-on.com`**

Верифицировано по [write-up Hasherezade](https://hshrzd.wordpress.com/2022/10/10/flare-on-9-task-10/) — точное совпадение.

Агент не проводил динамический анализ и не использовал эмулятор. В референсных решениях требовались: настройка Mini vMac, поиск ROM, монтирование диска, визуальный осмотр ресурсов. Procon достиг того же флага через статический анализ образа диска в IDA + граф контуров.

### Почему M68K важен

Псевдокод Hex-Rays для устаревших архитектур (M68K, PowerPC, старый MIPS) практически отсутствует в обучающих данных LLM. Эмпирически агенты рассуждают надёжнее по сырому дизассемблеру для таких ISA, чем по псевдокоду — знание ассемблера переносится между архитектурами, незнакомые диалекты псевдокода провоцируют галлюцинации. Именно поэтому фаза покрытия использовала дизассемблер как основной источник.

**Production** — 948 функций задокументировано в 7000-функциональном промышленном бинарнике за **15 минут, 6 параллельных агентов, $6**. Эквивалент ручной работы: 4 инженера × 6 месяцев.

## Почему это другое

**Дампишь один раз и закрываешь IDA.** `ida_dump.py` подключается к [MCP-серверу](https://github.com/mrexodia/ida-pro-mcp) IDA, пакетно декомпилирует все функции с callees, xrefs и метаданными, и записывает структурированные `.c` файлы. После этого вся работа идёт через API координатора. IDA больше не нужна.

**Агенты сами понимают что перед ними.** Вы не говорите им "это численная библиотека". Агент читает `sub_664212F0`, видит матричные операции и паттерны факторизации в callees, и пишет: "Sparse Cholesky decomposition (LL^T) with skyline storage". Он сам распознаёт алгоритмы, протоколы и паттерны проектирования.

**Кросс-модульная связка происходит автоматически.** Когда агент, анализирующий одну DLL, видит вызов в другую, он переключает `module=` в API и читает код из другого модуля. Не нужно переоткрывать IDA с другим бинарником. Координатор знает все загруженные модули и отдаёт их через единый API. Агенты следуют зависимостям между DLL так же естественно, как и по локальным вызовам.

**Контур — это не просто граф, а готовый к чтению исходный код.** Координатор собирает полный аннотированный исходник любого контура по запросу `/contour-code`: entry-функция сверху, затем helpers в порядке вызовов, каждая с заголовком роли и описания. Можно читать как единый файл, передать другому агенту или использовать как справочную документацию.

**Масштабирование тривиально.** 1 агент или 20 — координатор разруливает конфликты через атомарные захваты с TTL. Если агент упал — блокировка снимается автоматически. Если два агента дошли до одной функции — один получает "borrowed" копию (только чтение). Протестировано с 20 одновременными агентами (смешанный флот Claude + GPT), ноль конфликтов.

## Как это работает

```
IDA Pro + ida-pro-mcp         ida_dump.py           Координатор (:40000)
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────────┐
│ Декомпилирует     │───▶│ Пакетный экспорт │───▶│ Загружает дамп,      │
│ через MCP-сервер  │    │ всех функций     │    │ треки покрытия, API  │
└──────────────────┘    │ с метаданными    │    └──────────┬───────────┘
                        └──────────────────┘               │
                                                 ┌─────────┼─────────┐
                                                 ▼         ▼         ▼
                                              Агент     Агент     Агент
                                               │         │         │
                                            claim →   claim →   claim →
                                            trace →   trace →   trace →
                                            improve → improve → improve →
                                            submit    submit    submit
                                               │         │         │
                                               ▼         ▼         ▼
                                            контур    контур    контур
```

**Шаг 1 — Дамп.** Откройте бинарник в IDA Pro с [ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp). Запустите `ida_dump.py` — он вытянет каждую функцию через MCP-сервер и запишет структурированные `.c` файлы с метаданными callees/xrefs. Закройте IDA.

**Шаг 2 — Координация.** Запустите демон-координатор. Он загружает дамп, создаёт граф покрытия (какие функции проанализированы, какие нет) и запускает REST API на порту 40000.

**Шаг 3 — Анализ.** Запустите агентов Claude Code. Каждый автономно: запрашивает самую богатую непокрытую точку входа → захватывает → трассирует callees → улучшает код → сдаёт контур. Скилл сержанта (`/sergeant`) подскажет сколько агентов запускать и сгенерирует готовые команды.

## Что такое контур?

Название **procon** — от **pro**cessed **con**tour, обработанный контур — основная единица вывода.

Контур — это именованный подграф связанных функций, представляющий одну логическую единицу бинарника. Вместо плоского списка из 7000 улучшенных функций вы получаете структурированные группы: "разреженное разложение Холецкого", "мост COM IDispatch", "менеджер TLS-слотов".

```json
{
  "name": "sparse_cholesky@sub_664212F0",
  "summary": "Sparse Cholesky decomposition (LL^T/LDL^T) with skyline storage",
  "nodes": {
    "sub_664212F0": { "role": "entry",    "description": "Main factorization dispatcher" },
    "sub_6641FE90": { "role": "helper",   "description": "Rank-1 Givens rotation update" },
    "sub_66420E90": { "role": "borrowed", "description": "Skyline Cholesky (claimed by another agent)" }
  },
  "edges": [["sub_664212F0", "sub_6641FE90"], ["sub_664212F0", "sub_66420E90"]],
  "external_deps": [{ "name": "EnterCriticalSection", "module": "KERNEL32" }]
}
```

Роли: **entry** (корневая функция), **helper** (вызывается из entry), **leaf** (терминальная), **micro** (≤10 строк, общая для нескольких контуров), **borrowed** (захвачена другим агентом — только чтение).

## Результаты

Протестировано на реальном закрытом приложении (13 DLL, 11600+ функций, исходников нет):

| Модуль | Функций | Задокументировано | Контуров | Покрытие |
|--------|---------|-------------------|----------|----------|
| A.dll | 708 | 376 | 153 | 61.6% |
| B.dll | 147 | 31 | 16 | 60.8% |
| C.dll | 802 | 255 | 80 | 44.3% |
| D.dll | 1078 | 316 | 97 | 42.4% |
| E.exe | 971 | 284 | 69 | 34.0% |
| F.dll | 1265 | 248 | 80 | 30.3% |
| G.dll | 5307 | 696 | 115 | 13.3% |
| + ещё 6 модулей | 1332 | 193 | 80 | — |
| **Итого** | **11610** | **2399** | **690** | **25.4%** |

**Что обнаружили агенты** — без какого-либо предварительного знания о бинарнике:
- G.dll — статически слинкованная численная библиотека: агенты опознали FFT, SVD, разложение Холецкого, алгоритмы фитинга кривых
- A.dll — пайплайн обработки данных: парсинг XML, коррекция сигнала, анализ данных
- E.exe оркестрирует через кастомные Qt events между плагинами
- D.dll общается с оборудованием по TCP
- B.dll реализует лицензионную верификацию
- Кросс-модульные пути прослежены через 4 DLL — через Qt event dispatch, COM/IDispatch и DLL импорты

## После анализа

Когда контуры построены, координатор становится **сервером исходного кода** всего бинарника:

**Собранный исходный код.** `GET /contour-code?module=X&name=Y` возвращает полный аннотированный исходник контура — entry-функция первой, затем helpers в порядке вызовов, каждая с комментарием роли и описания. Это не JSON-граф — это читаемый `.c` код, который можно отдать человеку или другому агенту.

**Кросс-модульная навигация.** Каждый контур содержит `external_deps` — вызовы в другие модули. Любой агент (или скрипт) может их разрешить: `GET /func-code?module=algorithm&name=sub_664212F0` вернёт код независимо от того, из какой DLL он пришёл. Координатор уже загрузил все модули. Не нужно переключать базы IDA — просто измените параметр `module=`.

**Передай дальше.** Эндпоинт contour-code превращает ida-procon в бэкенд для последующих инструментов. Направьте другого агента Claude Code на `API_READ.md`, дайте ему URL координатора — и он сможет просматривать всю реверснутую кодовую базу по HTTP: читать контуры, следовать кросс-модульным вызовам, строить более высокоуровневое понимание поверх того, что солдаты уже наработали.

## Быстрый старт

### Требования

- **IDA Pro 9.x** с [ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp) — открывает декомпилятор IDA как MCP-сервер
- **Python 3.10+**
- **[Claude Code](https://claude.ai/code)** — CLI, который запускает агентов

### 1. Дамп из IDA

Откройте бинарник в IDA, убедитесь что ida-pro-mcp запущен (порт по умолчанию 13337):

```bash
pip install requests
python ida_dump.py --port 13337 --module mylib --output dump
```

Декомпилирует все функции и запишет в `dump/mylib/raw_funcs/` с индексом `manifest.json`. После завершения закройте IDA.

### 2. Запуск координатора

```bash
cd coordinator
pip install -r requirements.txt
python main.py --port 40000 --dump-dir ../dump
```

Координатор загрузит все модули из директории дампа и запустится на порту 40000.

### 3. Запуск агентов

Откройте Claude Code в корне репо:

```
/sergeant status          # покрытие по всем модулям
/sergeant mylib           # рекомендации по запуску агентов
```

Сержант анализирует оставшуюся работу и выдаёт готовые команды для запуска солдат. Запускайте сколько хотите параллельно.

### 4. Чтение результатов

```bash
# список контуров с описаниями
curl http://127.0.0.1:40000/contours?module=mylib

# собранный исходный код контура
curl "http://127.0.0.1:40000/contour-code?module=mylib&name=sparse_cholesky@sub_664212F0"

# общая статистика покрытия
curl http://127.0.0.1:40000/status
```

## Лицензия

MIT
