# OmnibusCloud Render Bridge — план внедрения (редизайн панели)

**Scope:** UI Blender-аддона (Python) + lifecycle бриджа (.NET). Чистый поток художника + свёрнутая диагностика, фазовая модель состояний, персистентность настроек, связь/вход, 2-осевая модель режимов, actionable-блокеры.

**Визуальный референс:** `omnibuscloud-render-bridge-design.html` (8 разделов: до/после, состояния, Image, Animation, идентичность, память настроек, связь и вход, принципы).

**Что это заменяет:** Phase 4 из `docs/bridge-addon-responsiveness-audit.md`

---

## Решения по ревью (2026-06-09)

Зафиксировано по итогам ревью дизайна/плана:

1. **Персистентность настроек — на бридже через `OutWit.Common.Settings` (JSON-провайдер), НЕ свой файл и НЕ `bpy AddonPreferences`.** Это канонический паттерн экосистемы (воркер `OutWit.Cloud.Client` и сервер уже на нём). `OutWit.Common.Settings.Json` — файловый провайдер с `.UseJson()`, DI, change-notify (`ISettingsValue : INotifyPropertyChanged`) и тестами на конкурентность. `SettingsPathResolver` уже целит в per-OS-user (`Environment.SpecialFolder.ApplicationData` → `%appdata%` / `~/.config`) — требование «локально, per-user, не синкается» закрывается из коробки. Persisted-корзина живёт на бридже; аддон тонкий — читает/пишет через REST (seed на открытии панели, sticky на submit); bpy-props — транзитный UI-binding. (См. Phase 5.)
2. **Старт бриджа — lazy-on-first-panel-visibility, без кнопки Refresh.** Refresh уходит не кнопкой, а механикой: хартбит опрашивает локальный бридж пока панель видима и делает `tag_redraw` при смене фазы. Бридж поднимается при первом показе N-панели (не на `register()`), idle-shutdown после долгой невидимости — убирает Refresh и не держит всегда-живой процесс, когда аддоном не пользуются. Ручной `Reconnect` — только контекстный в блокере. (См. Phase 3.) Подпись/нотаризация всех бинарей — обязательна к релизу (снимает AV/Gatekeeper-риск всегда-живого процесса).
3. **Добавить транзитную фазу `Cancelling`** между `Running` и `Cancelled`: отмена асинхронна (сервер гасит → текущая задача дорендеривается → `Cancelled`), кнопка Cancel должна давать мгновенный фидбэк (дизейбл + «finishing current task…»). (См. Phase 1.)
4. **Источник истины для фаз исполнения — серверный статус job** (из poll'а `JobMonitor`), не локальная догадка. `compute_status` реконсилит: connection/auth/blocker — локально, `Submitting/Running/Finalizing/Completed/Failed/Cancelled` — от бриджа. (См. Phase 1.)
5. **Phase 4 (вход) — плумбинг уже есть** (нативный OIDC loopback `127.0.0.1:<port>/callback` → `/auth/complete`, приложение на `auth.omnibuscloud.com`). Phase 4 — это UI-гейт над готовым флоу, не новая auth-механика.
6. **Foundation отзывчивости (responsiveness-audit Phases 1–3) уже в проде** (addon 0.2.0→0.4.1): off-thread `JobMonitor`/`AsyncCall` (`bridge_async.py`), оператор Cancel, `recommended_render_mode`, large-render-confirm. Части Phase 1/3/6 — консолидация существующего кода, не greenfield.
7. **Риск Blender Extensions:** bundled per-RID .NET-бридж конфликтует с публикацией в Extensions (per-platform сборки, правила на bundled-исполняемые). Для self-host `.zip` — ок; для Extensions — отдельная packaging-задача. (См. Риски / Phase 7.)

---

## Прогресс реализации (обновлять по ходу)

**Phase 1 — частично, в проде как addon `0.5.0` (commit 87fee19 / tag `addon-v0.5.0`):**
- ✅ `bridge_status.py` — `compute_status(scene, state) -> StatusView` + `Phase` (incl `Cancelling`) + типизированные `Blocker`; сконсолидированы все policy- и summary-хелперы. Headless-тесты `tests/test_bridge_status.py` (19, `python -m unittest`, без Blender).
- ✅ Основной поток подключён: Render-панель рисует статус/блокер/gate из `compute_status` (новый `_draw_status`); матрица `_draw_policy_box` **убрана из UI**; gate = `view.is_ready`. Cancel-оператор ставит `active_job_cancel_requested` → фаза `Cancelling` (сброс на new-job/Reset). Установлено и подтверждено пользователем («в целом работает»).
- ⏳ Остаток Phase 1 (войдёт в реструктур Phase 2): root-панель + диагностические панели ещё на старых хелперах (`_compact_status_label`/`_primary_finding`/`_validation_policy`/…); схлопывание god-object `bridge_state` (derived `preflight_*`/`validate_*`); удаление мёртвых `_can_start_render`/`_draw_policy_box`.

**Phase 2–7 — не начаты.** Следующий заход (новая сессия): **Phase 2 — панель 12→3+Advanced** (он же убирает остаток Phase 1). Стартовать с чтения текущего `bridge_panel.py` (12 Panel-классов) + этого плана.

---

## Порядок работ (рекомендация)

**Фундамент → структура → фичи.** Phase 1 (фазовая модель + единый модуль статуса) — это backbone, на котором сидят IA панели, блокеры и состояния связи. Делать косметику панели первой и прикручивать стейт-машину потом — значит строить панель против старых разрозненных булевых флагов и затем переделывать. Чисто-косметические правки можно вытащить раньше ради быстрого результата, но это даст переделку — **не рекомендую**.

Зависимости: `1 → 2 → {3,4} → 5 → 6 → 7`. Phase 3 (бридж, .NET-сторона) частично параллелится с Phase 2, но UI связи в 2/3 опирается на enum фаз из Phase 1.

---

## Phase 1 — Фундамент состояния (backbone; чинит дубли)

**Проблема:** состояние выводится из россыпи булевых флагов; презентационная логика продублирована в `bridge_panel.py` и `bridge_operators.py` и разъехалась — оператор сообщает одно, панель показывает другое.

**Новый файл `bridge_status.py`** — единственный источник правды для «в каком мы состоянии и что показать».
- `Phase` (enum): `Disconnected · Connecting · BridgeMissing · CloudUnreachable · SignedOut · Ready · Blocked · Preparing · Submitting · Running · Finalizing · Cancelling · Completed · Failed · Cancelled`.
  - **`Cancelling`** — транзитная фаза после клика Cancel: отмена асинхронна (сервер гасит → текущая задача дорендеривается → `Cancelled`). В этой фазе кнопка Cancel дизейблится, показывается «finishing current task…»; локально ставится оптимистично по клику, сверяется с серверным статусом.
- `compute_status(scene, runtime, prefs, job_phase) -> StatusView` — чистая функция, без UI. Возвращает: текущую фазу, **одну** строку статуса, **один** блокер с типизированным fix-action, и (свёрнутую) диагностическую детализацию.
  - **Источник истины фаз исполнения — серверный статус job** (`job_phase` из poll'а `JobMonitor`), не локальная догадка. `compute_status` реконсилит: connection/auth/blocker-фазы (`Disconnected/SignedOut/Blocked/Preparing`) считаются локально; `Submitting/Running/Finalizing/Cancelling/Completed/Failed/Cancelled` берутся от бриджа. Это структурно исключает drift «локально Running — на сервере Cancelled».
- Сюда переезжает вся логика, размазанная сейчас по двум файлам.

**`bridge_state.py`** (`OutWitBridgeRuntimeState`, ~85 полей) — схлопнуть god-object.
- Убрать `preflight_{still,frames,still_tiled,video}_{ready,issue_summary,warning_summary}` (17 полей) и `validate_*` (6) как хранимое состояние — они становятся производными от `compute_status`.
- Добавить одно поле `phase` (EnumProperty) + минимальные сырые входы, нужные модулю статуса.
- Транзиентные поля джоба пометить как reset-on-new-job (см. Phase 5).

**`bridge_operators.py`** (17 операторов) — удалить дубли:
- `_merge_unique_summaries` (определён здесь И в панели), `_validation_policy_message` / `_selected_mode_policy_message` / `_compose_policy_message`.
- Любой текст, который оператор репортит, берётся из `bridge_status.compute_status()` — оператор и панель всегда совпадают.

**Итог:** drift-баг становится структурно невозможным.

---

## Phase 2 — Реструктуризация панели (12 → 3 + Advanced)

**`bridge_panel.py`** (12 Panel-классов) — собрать в три видимые секции + Advanced.

- **Панель 1 — шапка/идентичность:** компактная марка (реальный логотип) + название + аккаунт; Login/Logout; связь — только при ошибке.
- **Панель 2 — Render (рабочий поток):** читает `StatusView`.
  - Target — только если опций > 1.
  - Ось `Output` (см. Phase 6).
  - **Одна** строка статуса + **одна** строка блокера. Удалить `_draw_policy_box` (матрица Engine/Scene/Mode над кнопкой).
  - Большая кнопка Render.
  - **Job и Results сворачиваются ВНУТРЬ этой панели по фазе:** прогресс + Cancel во время `Running`; результат + Download/Open после `Completed`. Художник не уходит из панели. Отдельные панели Job/Results удалить.
- **Панель 3 — Advanced / Diagnostics (свёрнута):** Connection, Account & scope, Scene & dependencies (слить Blend + Scene Diagnostics + dependency plan), Manual steps (Upload/Validate/Preflight + матрицы — живут тут), Last error.
- Убрать повторяющиеся факты: имя .blend — один раз, диапазон кадров — один раз.
- Убрать кнопку Check из основного потока (это тот же preflight, что Render и так гоняет; ручной Preflight остаётся в Advanced > Manual steps).

---

## Phase 3 — Связь и lifecycle бриджа (eager + watchdog + авто-reconnect)

**Файлы:** `bridge_launcher.py`, `bridge_client.py`, `bridge_async.py`, `__init__.py` (register/unregister), бридж `OutWit.Render.BlenderBridge` (.NET).

- **Старт (lazy-on-first-panel):** бридж поднимается при первом показе N-панели OmnibusCloud (первый `draw()`), а не на `register()`. `bridge_launcher` передаёт PID Blender (`--parent-pid <os.getpid()>`). Это убирает Refresh **и** не держит всегда-живой процесс, когда аддоном не пользуются. Первое открытие — честное короткое `Connecting…`. Опц. idle-shutdown бриджа после долгой невидимости панели. (Eager-on-register — допустимая альтернатива, если важнее «мгновенно готово»; с подписью AV-риск ниже. Для старт-триггера выбран lazy.)
- **Refresh уходит:** статус не тянется кнопкой — **хартбит делает `tag_redraw` региона панели при смене фазы**, панель сама обновляется. Кнопку Refresh из основного потока удалить (в «после»-мокапе её нет).
- **Гарантия гашения — в самом бридже (.NET):** watchdog по parent-PID — бридж следит за PID Blender и сам завершается, когда родитель исчез (нормальный выход, kill, краш). Кросс-платформенно и НЕ зависит от `unregister()`.
- **Доп. гарантия ОС:** Windows — Job Object `KILL_ON_JOB_CLOSE` (ставит лончер); Linux — `PR_SET_PDEATHSIG` (ставит бридж); macOS — хватает watchdog.
- **Graceful:** `unregister()` шлёт бриджу shutdown (отменить in-flight, освободить), таймаут → форс-килл. Watchdog — страховка.
- **Один инстанс на Blender** (lock/порт по PID); смерть бриджа в сессии → авто-релонч.
- **Хартбит:** расширить существующий `bpy.app.timers`-паттерн — лёгкий пинг локального бриджа раз в несколько секунд, пока панель видима, с откатом в простое. Обновляет `phase`. Аддон пингует ТОЛЬКО локальный бридж; статус облака берётся из ответа бриджа.
- **Reconnect:** на drop → авто-ретрай с backoff; после N неудач → `phase=Disconnected/BridgeMissing`, показать `[Reconnect]`. Различать причины:
  - бридж недоступен/флапает → reconnect;
  - бинарь не найден → `BridgeMissing` → `[Locate]` / `[Install]`, **без** бесконечного ретрая;
  - облако недоступно → `CloudUnreachable` → retry.
- **UI:** состояния связи рендерятся из `phase` (Connecting… / Bridge not responding → Reconnect / Bridge not found → Locate·Install). Ручной Reconnect — контекстно в блокере + всегда в Advanced > Connection.

**Риск №1 проекта** — orphan бриджа при краше. Watchdog обязателен и тестируется отдельно (`kill -9` Blender → бридж должен умереть).

---

## Phase 4 — Гейт входа (login/logout)

**Файлы:** `bridge_client.py` (auth), `bridge_panel.py`, `bridge_context.py`, бридж (WitIdentity/SSO).

> **Scope:** auth-плумбинг уже есть — нативный OIDC loopback (`127.0.0.1:<port>/callback` → `/auth/complete`) и приложение на `auth.omnibuscloud.com` (починено 2026-06). Phase 4 — это **UI-гейт** (`SignedOut → Login CTA`, Logout в строке идентичности) поверх готового флоу, не новая auth-механика.

- Гейт перед Ready: `connected → SignedOut → [Login] → SignedIn → Ready`.
- **Login** — главный CTA в `SignedOut` (брендовый локап: реальный логотип + вордмарка). Запускает WitIdentity/SSO через бридж (браузер/OAuth). Активен только при `connected`.
- **Logout** — явная небольшая кнопка в строке идентичности (бывш. «Sign Out»); дубль в Advanced > Account.
- Сессия/токен — на стороне бриджа; logout чистит.

---

## Phase 5 — Память настроек (%appdata%, per OS user, sticky)

**Файлы:** бридж `OutWit.Render.BlenderBridge` (.NET, владелец persisted-настроек через `OutWit.Common.Settings`), `bridge_client.py` (REST get/set settings), `bridge_state.py` (seed из бриджа / reset транзиента), `_finish_launch` (sticky-запись на submit).

- **Хранилище — на бридже через `OutWit.Common.Settings` + `.UseJson()`** (НЕ свой файл, НЕ `bpy AddonPreferences`). Канонический паттерн экосистемы (воркер уже на нём); файловый JSON-провайдер, concurrency-safe (несколько Blender, делящих файл — покрыто тестами), DI + change-notify. `SettingsPathResolver` уже целит в per-OS-user (`Environment.SpecialFolder.ApplicationData` → `%appdata%` / `~/.config`), **для пользователя ОС**, без серверного синка. Persisted-корзина = группа настроек на бридже; аддон тонкий — bpy-props это транзитный UI-binding, не хранилище.
- **Мастер-тоггл** «Remember last render settings» (default on).
- **Корзина 1 (сохранять):** tiled on/off, `tiles_x/y/overlap`, target (+ фолбэк, если группы нет), result sequence/video, video container/codec.
- **Корзина 2 (выводить, не хранить):** кадр/диапазон, разрешение, формат изображения, fps → из `scene` / Output Properties.
- **Корзина 3 (сбрасывать каждый джоб/сессию):** `phase`, прогресс, результат, download state, `validate_*`/`preflight_*` вердикты, scene-dirty/upload status, last error.
- Seed активного runtime из настроек бриджа (REST get) при открытии панели; sticky-запись использованных значений → бридж (REST set → `OutWit.Common.Settings`) на успешном submit (под мастер-тогглом).
- **Чинит баг:** `_scene_requires_upload` сейчас проверяет только путь — добавить проверку формата (смена формата должна форсить re-upload).

---

## Phase 6 — Модель вывода (2 оси) + actionable-блокеры

**Файлы:** `bridge_state.py`, `bridge_panel.py`, `bridge_operators.py`, `bridge_engine_routing.py`, `bridge_scene_packaging.py`.

- Заменить 4 плоских режима на 2 оси:
  - **Output: Image | Animation.**
  - Image → тоггл **«Split frame across machines»** (раскрывает `tiles_x/y/overlap`; дефолт — авто-грид от числа целевых машин, ручной оверрайд).
  - Animation → диапазон `Frames` + **Result: Sequence | Video**; Video раскрывает container/codec/fps.
- **Маппинг на существующие пути (ничего не теряем):** `Still = Image·single`, `Tiled Still = Image·split`, `Frames = Animation·sequence`, `Video = Animation·video`. `engine_routing` и `scene_packaging` продолжают обрабатывать те же четыре внутренних пути.
- Авто-вывод Output из сцены (диапазон > 1 → Animation), конфликт ловит блокер.
- **Actionable-блокеры** (open item C): каждый блокер несёт типизированный fix-action + кнопку, реализованную оператором, и поднимается через `compute_status`:
  - не сохранено → `[Save scene]`;
  - still + много кадров → `[Switch to Animation]`;
  - EXR на tiled → `[Switch format]`;
  - бридж не найден → `[Locate / Install]`.

---

## Phase 7 — Полировка и QA

- Тёмные токены темы — готовы; проверить рендер в Blender.
- Заменить плейсхолдер-логотип на детализированную «большую» иконку в signed-out (по готовности ассета).
- **Тест-матрица:**
  - холодный старт (eager launch + connect);
  - **краш Blender** → бридж обязан умереть (orphan-чек);
  - kill бриджа посреди рендера → авто-релонч;
  - login / logout;
  - каждый блокер → fix;
  - submit tiled / sequence / video;
  - sticky-настройки между рестартами И между пользователями ОС;
  - смена сцены/формата форсит re-upload.

---

## Сводка рисков

- **Orphan бриджа при краше** — watchdog обязателен, тест явный.
- **Дубликаты бриджа** — single-instance lock по PID.
- **Stale-персистентность** — никогда не хранить вердикты; всегда пересчёт.
- **Авто-reconnect** — кап ретраев + различение причин (нет бесконечного цикла на отсутствующем бинаре).
- **Blender Extensions + bundled .NET-бридж** — публикация в Extensions требует per-platform сборок и имеет правила на bundled-исполняемые; bundled per-RID бридж туда «как есть» не уедет. Self-host `.zip` — ок. Для Extensions — отдельная packaging-задача (+ обязательная подпись/нотаризация всех бинарей).

---

## Чеклист по файлам

| Файл | Phase | Суть правки |
|------|-------|-------------|
| `bridge_status.py` (новый) | 1 | Enum `Phase` + `compute_status()` — единый источник статуса/блокера |
| `bridge_state.py` | 1,5,6 | Схлопнуть god-object; `phase`; reset-on-job; sticky-seed; оси вместо плоских режимов |
| `bridge_operators.py` | 1,6 | Удалить дубли презентации; блокеры-операторы с fix-action |
| `bridge_panel.py` | 2,3,4,6 | 12→3+Advanced; lifecycle внутри Render; убрать `_draw_policy_box`/Check; оси; состояния связи и входа |
| `bridge_launcher.py` | 3 | **Lazy-старт на первый показ панели**, передача PID, Job Object (Win), single-instance, idle-shutdown |
| `bridge_client.py` | 3,4,5 | Хартбит/reconnect; auth-вызовы; **REST get/set настроек** бриджа |
| `bridge_async.py` | 3 | Хартбит-таймер рядом с `JobMonitor`; `tag_redraw` панели при смене фазы (убирает Refresh) |
| `bridge_context.py` | 4 | Контекст сессии/входа |
| `bridge_panel.py` (settings UI) | 5 | Мастер-тоггл «Remember last render settings»; bpy-props — транзитный UI-binding (хранилище на бридже) |
| `bridge_engine_routing.py` | 6 | Те же 4 пути под новой 2-осевой подачей |
| `bridge_scene_packaging.py` | 5,6 | Re-upload по смене формата; упаковка под оси |
| `__init__.py` | 3 | register → launch, unregister → graceful shutdown |
| `OutWit.Render.BlenderBridge` (.NET) | 3,4,5 | **Watchdog по parent-PID** (+PR_SET_PDEATHSIG); WitIdentity/SSO (готово); cloud-status в ответах; **persisted-настройки через `OutWit.Common.Settings.UseJson()` + REST get/set** |
