# ida-procon

**Massively parallel reverse engineering with LLM agents.**

*[Русская версия ниже](#ru)*

Feed it a binary. Get back structured, annotated, cross-referenced source code — organized into logical contours, not a flat dump.

Built and battle-tested on a real-world industrial control system (3 DLLs, 7000+ functions). 6 agents running in parallel, zero conflicts, 180 contours produced in a single session.

## What it does

Most RE tools give you a pile of decompiled functions. ida-procon gives you **understanding** — by deploying autonomous LLM agents that:

- **Trace call graphs** from entry points through internal callees
- **Rename variables** from `v1, v2` to meaningful names based on context
- **Build contours** — named subgraphs that represent logical units ("sparse Cholesky decomposition", "COM IDispatch bridge", "TLS slot manager")
- **Work in parallel** with atomic claims — no two agents touch the same function
- **Cross-link modules** — agents naturally follow cross-DLL calls through the API, no manual stitching

```
6 agents × 15 min = 180 contours, 948 functions resolved
Cost: ~800K tokens (~$6) for what would take a human weeks
```

## Architecture

```
IDA Pro (zeromcp)  →  ida_dump.py  →  dump/{module}/raw_funcs/
                                              ↓
                                    Coordinator API (:40000)
                                     ↙    ↓    ↘
                                Agent  Agent  Agent  ...
                                  ↓      ↓      ↓
                              contour contour contour
                                  └──────┼──────┘
                                   coverage.json
```

**ida_dump.py** — Batch decompiler. Connects to IDA's MCP server, pulls all functions with callees/xrefs, writes structured `.c` files with metadata headers.

**Coordinator** — FastAPI daemon that serializes writes and manages claims. Agents talk to it via HTTP, never touch raw files directly. Supports any number of parallel agents with zero conflicts.

**Agents** — Claude Code subagents (opus for complex 200+ line functions, sonnet for regular ones). Each agent autonomously: claims → traces → improves → submits. Minimum 10 contours per opus session, 5 per sonnet.

**Contours** — The output. Each contour is a named call subgraph:

```json
{
  "name": "sparse_cholesky@sub_664212F0",
  "entry": "sub_664212F0",
  "summary": "Sparse Cholesky decomposition (LL^T/LDL^T) with skyline storage",
  "nodes": {
    "sub_664212F0": {"role": "entry", "description": "Main factorization dispatcher"},
    "sub_6641FE90": {"role": "helper", "description": "Rank-1 Givens rotation update"},
    "sub_66420E90": {"role": "borrowed", "description": "Skyline Cholesky (claimed by another agent)"}
  },
  "edges": [["sub_664212F0", "sub_6641FE90"], ["sub_664212F0", "sub_66420E90"]],
  "external_deps": [{"name": "EnterCriticalSection", "module": "KERNEL32"}]
}
```

## Results on real target

Tested on a real-world industrial control system (3 DLLs, no source code):

| Module | Functions | Resolved | Contours | Coverage |
|--------|-----------|----------|----------|----------|
| algorithm.dll | 5307 | 696 | 115 | 13.3% |
| protocol.dll | 708 | 244 | 65 | 40.0% |
| main.exe | 971 | 8 | 1 | 1.0% |

**What agents found:**
- algorithm.dll is a statically linked numerical library — agents identified FFT, SVD, Cholesky, spline fitting, neural networks, optimization solvers
- protocol.dll is a Qt/COM bridge — QAxBase, IDispatch marshalling, QVariant conversion, XML serialization
- Cross-module linking happened naturally: agents reading protocol code followed calls into algorithm functions through the API

**Emergent behavior:** We designed a separate "knot" layer for cross-module connections. Turned out it wasn't needed — agents discover cross-module dependencies organically by following external_deps through the API. The coordinator already *is* the linker.

## Quickstart

### Prerequisites
- IDA Pro 9.x with [zeromcp](https://github.com/nickcano/zeromcp)
- Python 3.10+
- [Claude Code](https://claude.ai/code)

### 1. Dump from IDA

```bash
pip install requests
python ida_dump.py --port 13337 --module mylib --output dump
```

### 2. Start coordinator

```bash
cd coordinator
pip install -r requirements.txt
python main.py --port 40000 --dump-dir ../dump
```

### 3. Deploy agents

From the repo root in Claude Code:
```
/sergeant status
/sergeant mylib
```

The sergeant analyzes coverage and gives you ready-to-paste commands for launching parallel soldiers.

## API

Full reference: [API.md](API.md) | Read-only reference: [API_READ.md](API_READ.md)

Key endpoints:
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/status` | Coverage stats per module |
| GET | `/next-entry?module=X` | Best uncovered function to work on |
| GET | `/contour-code?module=X&name=Y` | Assembled source of entire contour |
| GET | `/contours?module=X` | List all contours with summaries |
| POST | `/claim` | Atomically claim a function |
| POST | `/submit-contour` | Submit completed contour |

## How agents avoid conflicts

The claim system makes parallel execution safe:

1. Agent calls `POST /claim {module, name}` — atomic lock with 600s TTL
2. If another agent already claimed it → function becomes "borrowed" (read-only, still included in contour graph for context)
3. Claims auto-release if agent crashes
4. All coverage writes go through a serialized queue — no race conditions

Tested with 6 simultaneous agents, zero conflicts.

## Repo structure

```
ida-procon/
├── ida_dump.py              # IDA batch decompiler
├── coordinator/             # FastAPI coordination daemon
│   ├── main.py              # Entry point
│   ├── api/                 # REST endpoints
│   ├── models/              # Pydantic schemas
│   ├── services/            # Business logic (claims, resolution, contours)
│   └── storage/             # File I/O
├── agents/                  # Agent orders
│   ├── soldiers/opus/       # Opus handles 200+ line functions
│   └── soldiers/sonnet/     # Sonnet handles 11-200 line functions
├── .claude/skills/sergeant/ # Orchestration skill
├── CLAUDE.md                # Commander instructions
├── API.md                   # Full API reference
└── API_READ.md              # Read-only API reference
```

---

<a name="ru"></a>

# ida-procon (RU)

**Массово-параллельный реверс-инжиниринг с LLM-агентами.**

Скорми бинарник — получи структурированный, аннотированный, перекрёстно связанный исходный код. Не плоский дамп, а логические контуры.

Создано и протестировано на реальной промышленной системе управления (3 DLL, 7000+ функций). 6 агентов параллельно, ноль конфликтов, 180 контуров за одну сессию.

## Что это делает

Большинство RE-инструментов выдают кучу декомпилированных функций. ida-procon даёт **понимание** — разворачивая автономных LLM-агентов, которые:

- **Трассируют граф вызовов** от точки входа через внутренние callees
- **Переименовывают переменные** из `v1, v2` в осмысленные имена по контексту
- **Строят контуры** — именованные подграфы, представляющие логические единицы ("разложение Холецкого", "мост COM IDispatch", "менеджер TLS-слотов")
- **Работают параллельно** с атомарными claim'ами — два агента никогда не трогают одну функцию
- **Связывают модули** — агенты естественно следуют кросс-DLL вызовам через API, без ручной сшивки

```
6 агентов × 15 мин = 180 контуров, 948 функций разобрано
Стоимость: ~800K токенов (~$6) за работу, которая заняла бы у человека недели
```

## Архитектура

```
IDA Pro (zeromcp)  →  ida_dump.py  →  dump/{module}/raw_funcs/
                                              ↓
                                    Координатор API (:40000)
                                     ↙    ↓    ↘
                                Агент  Агент  Агент  ...
                                  ↓      ↓      ↓
                              контур  контур  контур
                                  └──────┼──────┘
                                   coverage.json
```

**ida_dump.py** — Пакетный декомпилятор. Подключается к MCP-серверу IDA, вытягивает все функции с callees/xrefs, пишет структурированные `.c` файлы с заголовками метаданных.

**Координатор** — FastAPI-демон, сериализующий запись и управляющий claim'ами. Агенты общаются с ним по HTTP, не трогая файлы напрямую. Поддерживает любое число параллельных агентов без конфликтов.

**Агенты** — субагенты Claude Code (opus для сложных функций 200+ строк, sonnet для обычных). Каждый агент автономно: claim → трассировка → улучшение → submit. Минимум 10 контуров за сессию opus, 5 за sonnet.

**Контуры** — результат работы. Каждый контур — именованный подграф вызовов с ролями (entry, helper, leaf, borrowed) и описаниями.

## Результаты на реальном таргете

Протестировано на реальной промышленной системе управления (3 DLL, исходников нет):

| Модуль | Функций | Разобрано | Контуров | Покрытие |
|--------|---------|-----------|----------|----------|
| algorithm.dll | 5307 | 696 | 115 | 13.3% |
| protocol.dll | 708 | 244 | 65 | 40.0% |
| main.exe | 971 | 8 | 1 | 1.0% |

**Что нашли агенты:**
- algorithm.dll — статически слинкованная численная библиотека. Агенты опознали FFT, SVD, Холецкий, сплайн-фиттинг, нейросети, оптимизационные солверы
- protocol.dll — Qt/COM мост. QAxBase, маршаллинг IDispatch, конвертация QVariant, XML-сериализация
- Кросс-модульная связка произошла естественно: агенты, читая код protocol, следовали за вызовами в algorithm через API

**Эмерджентное поведение:** Мы проектировали отдельный слой "knot" для кросс-модульных связей. Оказалось, он не нужен — агенты обнаруживают зависимости между модулями органически, следуя по external_deps через API. Координатор уже *является* линковщиком.

## Быстрый старт

### Требования
- IDA Pro 9.x с [zeromcp](https://github.com/nickcano/zeromcp)
- Python 3.10+
- [Claude Code](https://claude.ai/code)

### 1. Дамп из IDA

```bash
pip install requests
python ida_dump.py --port 13337 --module mylib --output dump
```

### 2. Запуск координатора

```bash
cd coordinator
pip install -r requirements.txt
python main.py --port 40000 --dump-dir ../dump
```

### 3. Деплой агентов

Из корня репо в Claude Code:
```
/sergeant status
/sergeant mylib
```

Сержант анализирует покрытие и выдаёт готовые команды для запуска параллельных солдат.

## Как агенты избегают конфликтов

Система claim'ов делает параллельное выполнение безопасным:

1. Агент вызывает `POST /claim {module, name}` — атомарная блокировка с TTL 600 секунд
2. Если другой агент уже занял функцию → она становится "borrowed" (только чтение, но всё равно включается в граф контура для контекста)
3. Claim'ы автоматически освобождаются если агент упал
4. Все записи в coverage идут через сериализованную очередь — никаких гонок

Протестировано с 6 одновременными агентами, ноль конфликтов.

