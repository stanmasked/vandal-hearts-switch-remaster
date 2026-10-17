# Vandal Hearts Remake — этап №214: передача NRO для физической проверки звука

**Статус: `HARDWARE NOT TESTED`.** Этот документ относится к подготовке запуска, а не к выполненному тестированию Nintendo Switch. Никакие приведённые ниже команды не запускают код на самой консоли.

## 1. Проверка происхождения сборки

1. На странице [GitHub Actions — Switch toolchain readiness](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/switch-toolchain.yml) откройте **успешный run** ветки `test/cdxa-extract-decode-pipeline`. Скопируйте полное значение `Head SHA` (40 шестнадцатеричных символов), номер/URL запуска, дату и настройки сборки. Не заменяйте фактический SHA названием ветки или версией приложения.
2. Из этого же запуска скачайте артефакт `vandal-hearts-switch-prototype` и извлеките основной `vandal-hearts-prototype.nro`. Исторические standalone аудиопробы и SDL2-пробы не являются этим файлом. При необходимости сохраните архив и его хеш отдельно.
3. На компьютере проверьте структурную корректность файла:

```sh
python3 tests/check_nro.py /path/to/vandal-hearts-prototype.nro
shasum -a 256 /path/to/vandal-hearts-prototype.nro
```

Проверка `NRO0` не подтверждает выполнение на Switch. SHA-256 архива GitHub Actions (если опубликован) **не равен** SHA-256 извлечённого NRO. Не считайте ссылку на CI в локальном манифесте криптографически подтверждённой: её вводит оператор; утилита работает офлайн и не сверяет ссылку с GitHub API.

## 2. Сухой прогон комплекта до испытания

В каталоге с исходной неизменённой копией NRO создайте манифест **без CSV**, чтобы зафиксировать исходный бинарник:

```text
switch-audio-preflight-214/
  nro/vandal-hearts-prototype.nro
```

```sh
python3 tools/verify_switch_audio_bundle.py create switch-audio-preflight-214 \
  --git-sha YOUR_ACTUAL_FULL_40_CHARACTER_COMMIT \
  --nro nro/vandal-hearts-prototype.nro

python3 tools/verify_switch_audio_bundle.py verify switch-audio-preflight-214
```

Ожидаемые поля: `integrity: VERIFIED`, `nro_structure: VALID_STRUCTURAL_HEADER_ONLY`, `build_provenance: SELF_REPORTED_UNVERIFIED`, `telemetry_readiness: INCOMPLETE` и `hardware_status: HARDWARE NOT TESTED`.

Если NRO слишком короткий, отсутствует `NRO0`, объявленный размер выходит за файл или сегменты `text/rodata/data` выходят за пределы NRO, операция возвращает ошибку **даже при правильном SHA-256**. Программа повторно проверяет структуру при `verify`, а не только при создании манифеста.

**Важно:** после успешного `create` старый манифест не редактируется. Для новых CSV создайте **отдельный** каталог с новой копией NRO, сохранив предварительный комплект для контроля.

## 3. Реальные испытания (ещё не проводились)

Используйте разрешённую среду homebrew и предпочтительно полноценный Application context. Для одного запуска заранее подготовьте карточку [SWITCH_AUDIO_STAGE212_SESSION_TEMPLATE.md](SWITCH_AUDIO_STAGE212_SESSION_TEMPLATE.md) и заполните наблюдения на **реальной** консоли:

- Запустите главный тактический NRO; убедитесь, что слышна музыка. Для диагностической панели нажмите **Minus**, для записи — **Y**.
- Соберите не менее двух **независимых** сеансов с минимум 1000 *наблюдаемыми* PCM-страницами каждый; выполните в рамках программы проверки **10 HOME → возврат**, **5 сон → пробуждение**, а также **30–60 минут** длительного прослушивания.
- Завершите каждый запуск **Plus**, затем после штатного завершения копируйте новый `sdmc:/switch/vandal-hearts-remake/audio-diagnostics-XXXX.csv`. Файл `audio-diagnostics.tmp` не является завершённым результатом.
- Отдельно оцените слышимые щелчки, пропуски нот, заикания и задержку восстановления; цифры `first_pcm_count/last_pcm_us/worst_pcm_us` измеряют подтверждение libnx и **не** момент звука в динамике.
- Проверьте старые CSV по SHA-256 до/после следующего запуска NRO. Если что-то не читается, отметьте `INCONCLUSIVE` или `FAIL` и сохраните неповреждённые доказательства.

**Не извлекайте SD во время работы и не отключайте питание умышленно.** Успешный read-back/rename на FAT не гарантирует стойкость данных к внезапной потере питания.

## 4. Комплект из фактически полученных файлов

После испытаний создайте **новый** каталог с NRO и исходными CSV двух реальных сеансов, не перемещая файлы из предварительного комплекта:

```text
switch-audio-results-214/
  nro/vandal-hearts-prototype.nro
  session-01/audio-diagnostics-0000.csv
  session-02/audio-diagnostics-0001.csv
```

```sh
python3 tools/verify_switch_audio_bundle.py create switch-audio-results-214 \
  --git-sha YOUR_ACTUAL_FULL_40_CHARACTER_COMMIT \
  --nro nro/vandal-hearts-prototype.nro \
  --session session-01/audio-diagnostics-0000.csv \
  --session session-02/audio-diagnostics-0001.csv

python3 tools/verify_switch_audio_bundle.py verify switch-audio-results-214 \
  > switch-audio-results-214/verification.json
```

При необходимости приложите к протоколу подтверждённый вручную SHA-256 полученного NRO, вывод строгого [CSV-анализатора](../tools/analyze_switch_audio_log.py), фотографии интерфейса, сведения о режиме звука и заполненные карточки. Не публикуйте игры/ROM/SEQ/VH/VB, приватные материалы и не добавляйте реальные файлы в исходный Git-репозиторий.

## 5. Как читать результаты, не заявляя ложной приёмки

| Поле | Значение | **Чего не доказывает** |
| --- | --- | --- |
| `integrity: VERIFIED` | Зарегистрированные файлы сохранили байты согласно локальному неподписанному JSON-манифесту | Подлинность источника и сохранность SD после отключения питания |
| `nro_structure: VALID_STRUCTURAL_HEADER_ONLY` | Формат заголовка и диапазоны NRO прошли ограниченную проверку | Возможность исполнения кода, отсутствие падений на консоли |
| `build_provenance: SELF_REPORTED_UNVERIFIED` | SHA/CI URL введены оператором и сохранены для последующей ручной сверки | Подтверждение, что файл действительно собран этим коммитом |
| `telemetry_readiness: ENOUGH_DATA_FOR_MANUAL_REVIEW` | Есть не менее двух различающихся по байтам CSV, подходящих по базовым количественным критериям | Две независимые физические сессии или качественное звучание |
| `hardware_status: HARDWARE NOT TESTED` | Аппаратная приёмка остаётся за независимым ручным протоколом | Автоматический `PASS` даже при успехе CI |

**Итоговое решение принимает только оператор на основании реальных данных.** См. матрицу H01–H07 в [пакете №212/213](SWITCH_AUDIO_STAGE212_ACCEPTANCE_PACK.md). Если устройство не тестировалось, результат остаётся `HARDWARE NOT TESTED`; отсутствие файла/краткое окно означает недостаток наблюдений, а не доказательство сбоя музыки.

## 6. Этап №215 — автоматическая сортировка телеметрии (не аппаратная приёмка)

После успешного `create`/ `verify` этапов №213–214 доступен **дополнительный, полностью офлайн и read-only** инструмент [`report_switch_audio_hardware.py`](../tools/report_switch_audio_hardware.py). Он сначала снова проверяет NRO, SHA-256 и строгий формат **каждого** CSV; повреждённый или изменённый комплект не превращается в положительный отчёт.

Для структурированного отчёта:

```sh
python3 tools/report_switch_audio_hardware.py switch-audio-results-214 \
  --format json > audio-hardware-report.json
```

Для текстового протокола с таблицей по каждой сессии:

```sh
python3 tools/report_switch_audio_hardware.py switch-audio-results-214 \
  --format markdown > audio-hardware-report.md
```

**Выводите отчёты вне каталога с манифестом**: так легче отличить исходные доказательства от результатов анализа. Код завершения `0` означает **только**, что отчёт сформирован на основе проверенных файлов; при сбое верификации/парсинга возвращается `2` и **положительный отчёт не печатается**.

Разделы JSON не смешивают разные утверждения:

- `file_integrity`: нынешнее совпадение SHA-256 с неподписанным манифестом и структурная проверка NRO. Поля `prior_sd_file_preservation: NOT_OBSERVABLE` и `power_loss_durability: NOT_TESTED` указывают на пределы проверки.
- `pcm` для **каждого CSV**: наблюдаемые подтверждения PCM, `pcm_fail`, `lease_fail`, перезапуски, восстановления, потенциальные остановки вывода, выборочный p95 подтверждения буфера и входы в `ERROR`.
- `resume`: наблюдаемые приращения HOME, `home_fail`, попытки повторного открытия и восстановления. `sleep_cycles: NOT_SEPARATELY_OBSERVABLE` означает, что лог **не позволяет отдельно подсчитать реальные циклы сна**.
- `recording`: пропущенная история `GAP`, откаты счётчиков, неопределённые ошибки из вытесненной истории и предупреждения, включая ограничение 128 записей.
- `report_triage`: `INVESTIGATE` при наблюдаемых ошибках/подозрительной остановке, `INCONCLUSIVE` при недостатке сравнимых данных, `REVIEW` при дополнительных предупреждениях либо `MANUAL_REVIEW_REQUIRED`. **Ни один из них не является аппаратным PASS.**

Во всех случаях `hardware_status` сохраняется `HARDWARE NOT TESTED`. Синтетические host-тесты не могут подтвердить качество звучания, настоящие 10 возвратов HOME, 5 циклов сна, 30–60 минут работы, сохранность старого CSV на SD после новой сессии или независимость двух физических запусков. Эти поля заполняются только в отдельной [ручной карточке сессии](SWITCH_AUDIO_STAGE212_SESSION_TEMPLATE.md).

Для проверки логики предусмотрен [`tests/test_report_switch_audio_hardware.py`](../tests/test_report_switch_audio_hardware.py) — чистые/повреждённые журналы, раздельные PCM и HOME-сбои, недостаточные записи, копии одинаковых CSV, подмена файлов, вывод Markdown/JSON и отказ без ложного статуса успеха. Тест запускается через `make test` и `make test-audio-stream`.


## 7. Этап №216 — офлайн-сверка NRO с конкретным GitHub Actions artifact

[Проверяющий инструмент](../tools/verify_switch_audio_build_provenance.py) требует **четыре независимых локальных входа**: существующий комплект с `audio-evidence-manifest.json`, оригинальный ZIP из GitHub Actions, снимок JSON выбранного workflow run и снимок JSON метаданных artifact. Комплект должен быть создан с обязательным `--ci-run-url`, соответствующим тому же реальному запуску. Для этой проверки используется **только** workflow `Switch toolchain readiness`, ветка `test/cdxa-extract-decode-pipeline` и архив `vandal-hearts-switch-prototype`.

1. Сохраните **неизменённый ZIP** с вкладки Artifacts конкретного успешного [запуска GitHub Actions](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/workflows/switch-toolchain.yml). Обязательно запишите номер run и артефакта. SHA-256 ZIP и его содержимого проверяются по метаданным GitHub.
2. Получите **официальные JSON-ответы GitHub REST API**, желательно непосредственно по HTTPS в момент проверки. При доступном `gh` CLI и подключённой учётной записи:

```sh
gh api repos/stanmasked/vandal-hearts-switch-remaster/actions/runs/RUN_ID \
  > run.json
gh api repos/stanmasked/vandal-hearts-switch-remaster/actions/artifacts/ARTIFACT_ID \
  > artifact.json
```

3. Используйте пакет этапа №213/214, созданный с **действительным** URL того же run (`--ci-run-url https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/RUN_ID`). Поместите `run.json`, `artifact.json` и ZIP **вне** папки с NRO/CSV, чтобы не смешивать неизменяемое свидетельство и рабочие отчёты.
4. Запустите:

```sh
python3 tools/verify_switch_audio_build_provenance.py \
  switch-audio-results-214 \
  --artifact-zip /path/to/original-artifact.zip \
  --run-json /path/to/run.json \
  --artifact-json /path/to/artifact.json \
  > /path/to/provenance-report.json
```

**Что именно проверяется:** полное совпадение Git SHA с `head_sha` запуска и артефакта, репозиторий, ветка, путь и имя workflow, состояние `completed/success`, `run_id`, `artifact_id`, имя артефакта, флаг `expired`, объявленный размер и SHA-256 ZIP, единственный ожидаемый NRO в архиве и **его точные байты** против NRO из проверенного манифеста. Архив не распаковывается на диск; предусмотрены ограничители размеров и количества элементов и отказ при опасных/повторяющихся ZIP-путях.

**Результат:** `comparison: CONSISTENT_WITH_PROVIDED_GITHUB_METADATA` и `build_provenance: LOCAL_METADATA_CROSSCHECK_NOT_SIGNED`. Код `0` — только успешная **локальная сверка**. Код `2` и `comparison: FAILED` — несоответствие, повреждение или некорректные метаданные. Невозможно автоматически утверждать, что оператор получил JSON непосредственно с GitHub, что они не редактировались или что NRO имеет криптографическую аттестацию происхождения. Результат никогда не равен `HARDWARE PASS`, неизменный статус — `HARDWARE NOT TESTED`.

Для новых комплектов фиксируйте SHA-256 и идентификаторы сборки сразу при получении артефакта. Порог аппаратной приёмки по-прежнему требует настоящих CSV со Switch, независимых прогонов, проверки слухом и ручной [карточки сессии](SWITCH_AUDIO_STAGE212_SESSION_TEMPLATE.md).

Host-only регрессии: [`tests/test_verify_switch_audio_build_provenance.py`](../tests/test_verify_switch_audio_build_provenance.py), подключены к `make test` и `make test-audio-stream`. Тесты используют только синтетические ZIP и NRO-заголовки, **не** реальную консоль и не игровые ресурсы.


## 8. Этап №217 — онлайн-проверка актуального HEAD перед передачей NRO

Для **передачи последней сборки на физическую Switch** дополнительно используйте [`tools/verify_switch_audio_live_preflight.py`](../tools/verify_switch_audio_live_preflight.py). В отличие от архивной офлайн-сверки этапа №216, новый режим **сам** читает GitHub REST по HTTPS с проверкой TLS, не принимает подготовленные оператором JSON как источник истины и сверяет NRO с **текущим HEAD** ветки непосредственно перед передачей устройства на тест. Никакие персональные токены или игровые ресурсы не нужны для публичного репозитория в пределах GitHub API rate limit.

Сначала создайте комплект №213/214 **с реальными параметрами конкретной сборки**:

```sh
python3 tools/verify_switch_audio_bundle.py create switch-audio-preflight-217 \
  --git-sha FULL_40_DIGIT_SHA_OF_THE_NRO_BUILD \
  --ci-run-url https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/RUN_ID \
  --nro nro/vandal-hearts-prototype.nro
```

Из **того же** завершённого успешного workflow `Switch toolchain readiness` скачайте архив артефакта `vandal-hearts-switch-prototype`, сохраните ZIP без изменений и запишите числовые `RUN_ID` и `ARTIFACT_ID` со страницы GitHub:

```sh
python3 tools/verify_switch_audio_live_preflight.py switch-audio-preflight-217 \
  --artifact-zip /path/to/original-artifact.zip \
  --run-id RUN_ID \
  --artifact-id ARTIFACT_ID \
  > /path/to/live-preflight-217.json
```

Номер `ARTIFACT_ID` можно получить через `gh api repos/stanmasked/vandal-hearts-switch-remaster/actions/runs/RUN_ID/artifacts`. Не используйте номер другого архива или номер run вместо artifact ID.

Инструмент проверяет:

- HTTPS-ответы GitHub для run, artifact и `refs/heads/test/cdxa-extract-decode-pipeline`, только по жёстко фиксированным путям API;
- точное совпадение полного Git SHA из манифеста, `head_sha` успешного run, `head_sha` артефакта и **текущего HEAD ветки**;
- имя/путь workflow, репозиторий, ветку, номер и URL запуска, имя артефакта и срок его доступности;
- ограничение возраста запуска: по умолчанию **30 дней**; иной явный лимит — `--max-run-age-days N` (1–365);
- SHA-256 оригинального ZIP из GitHub и побайтный SHA-256 NRO внутри архива по сравнению с файлом, заранее зафиксированным в манифесте.

При успехе возвращаются `result: MATCHED_CURRENT_HEAD_AT_CHECK_TIME`, `build_provenance: GITHUB_HTTPS_METADATA_AND_BYTE_MATCH_NOT_SIGNED`, `checked_at_utc` и `head_sha_at_check_time`, код завершения `0`. При старом коммите (ветка ушла вперёд), слишком давнем запуске, подменённом файле/архиве, несоответствии ID или недоступности GitHub API — `result: FAILED`, код `2` и **никакого разрешения на передачу новой сборки как текущей**. Старую намеренно зафиксированную сборку можно исследовать отдельно по историческому протоколу №216, но нельзя выдавать её за нынешний HEAD.

**Ограничение:** даже настоящий HTTPS-ответ GitHub не является подписанной аттестацией воспроизводимой сборки. Текущий HEAD может измениться *после* запроса: повторите preflight непосредственно перед копированием NRO на SD, сохраните дату и JSON результата. Никаких физических HOME/сна, прослушивания и стойкости SD онлайн-сверка не подтверждает: `hardware_status` остаётся `HARDWARE NOT TESTED`.

Регрессии [`tests/test_verify_switch_audio_live_preflight.py`](../tests/test_verify_switch_audio_live_preflight.py) выполняются **без сети**, на имитированных ответах GitHub: актуальный HEAD, уход ветки вперёд, старый/истёкший артефакт, подмена ZIP/NRO, будущие метки времени, небезопасные URL и некорректные идентификаторы. Подключены в `make test` / `make test-audio-stream`.


## 9. Этап №218 — контроль SHA-256 до и после ручного копирования NRO на SD

Добавлена [`tools/verify_switch_audio_sd_transfer.py`](../tools/verify_switch_audio_sd_transfer.py) — двухэтапная **строго read-only по отношению к SD** процедура. Она не копирует, не заменяет, не удаляет и не переименовывает файлы на SD и **не подтверждает**, что выбранный каталог является реальной физической картой. В качестве источника используется **предварительно проверенный комплект** №213–217 с NRO `vandal-hearts-prototype.nro`.

**Перед началом:** убедитесь, что выбранный NRO действительно соответствует нужному GitHub Actions run: выполните live-проверку этапа №217 как можно ближе к переносу файлов. Подключите SD обычным способом, определите *её фактический путь монтирования* на своём компьютере. В командах ниже `/mount/SDCARD` — только **пример**, а не автоматически обнаруженное устройство. Указанный пользовательский каталог может быть обычным диском, поэтому инструмент **не способен подтвердить носитель**.

### Шаг А — зафиксировать исходник и существующий файл до переноса

```sh
python3 tools/verify_switch_audio_sd_transfer.py plan switch-audio-preflight-217 \
  --sd-root /mount/SDCARD \
  --output /path/outside-sd/transfer-plan-218.json
```

План `transfer-plan-218.json` создаётся однократно **вне** исходного комплекта и SD. В нём записываются полный Git SHA, исходный NRO (относительный путь, длина и SHA-256), SHA-256 манифеста и состояние существующего файла назначения (если он уже был). Если файл существует, его содержимое только считывается: **не перезаписывается**. Папку назначения можно создать до копирования, но утилита сама ничего на карте не создаёт.

По умолчанию проверяется путь `switch/vandal-hearts-remake/vandal-hearts-prototype.nro` **от корня SD**. Для другого заранее согласованного пути допускается параметр `--destination switch/your-folder/vandal-hearts-prototype.nro`, но имя NRO остаётся фиксированным. Любая ссылка-символический переход в пути, `..`, абсолютный путь или попытка использовать сам источник как «SD» отвергаются.

### Шаг Б — обычное копирование пользователем

Скопируйте **именно** `switch-audio-preflight-217/nro/vandal-hearts-prototype.nro` в каталог `/mount/SDCARD/switch/vandal-hearts-remake/` привычным файловым менеджером или командой ОС. Не подменяйте исходник, не меняйте его содержимое, а при обновлении уже существующей версии сначала сохраните старую отдельно. Дождитесь штатного завершения операции и безопасного завершения записи носителя в вашей ОС.

**Никогда не отключайте/не извлекайте SD во время активной записи.** Инструмент не выполняет `fsync` для операции копирования и не доказывает, что FAT записан устойчиво к внезапному отключению питания.

### Шаг В — независимая проверка файлов после переноса

```sh
python3 tools/verify_switch_audio_sd_transfer.py verify switch-audio-preflight-217 \
  --sd-root /mount/SDCARD \
  --plan /path/outside-sd/transfer-plan-218.json \
  > /path/outside-sd/sd-transfer-check-218.json
```

При успешном чтении возвращается код `0` и `result: DESTINATION_BYTES_MATCH_PLANNED_NRO`; тогда повторно вычисленные длина и SHA-256 **отдельного файла назначения** совпадают с зафиксированным NRO, структура `NRO0` проходит проверку, исходный манифест не изменён. Если файл отсутствует, усечён, изменён, передан по недопустимому пути или источник менялся после планирования — `result: FAILED`, код `2`.

Особо важные поля результата:

- `destination_previously_existed` — существовал ли NRO по тому же пути **до** переноса;
- `destination_was_already_identical_before_plan` — файл с такими же байтами был там заранее, поэтому даже успешная сверка **не доказывает новый акт копирования**;
- `copy_operation: NOT_OBSERVED_BY_VERIFIER` — программа только читает, **не следит за процессом копирования**;
- `destination_medium: NOT_VERIFIED_AS_PHYSICAL_SD` и `sd_durability: NOT_TESTED` — нельзя делать вывод о настоящем SD-носителе или долговечности записи;
- `hardware_status: HARDWARE NOT TESTED` — программная проверка никогда не превращается в аппаратный `PASS`.

Перед реальным запуском на консоли отсоедините SD **штатно**, при необходимости ещё раз проверьте хеш при повторном подключении и отметьте наблюдения в [ручной карточке](SWITCH_AUDIO_STAGE212_SESSION_TEMPLATE.md). Наличие NRO с совпадающим хешем не означает, что homebrew-среда загрузит программу или что музыка будет воспроизводиться корректно.

Добавлены [`tests/test_verify_switch_audio_sd_transfer.py`](../tests/test_verify_switch_audio_sd_transfer.py): 17 регрессионных тестов на хосте с *симулированным* смонтированным каталогом, включая пустую SD, существующий файл, частично скопированный файл, совпадающие и искажённые байты, изменение исходного манифеста, поддельный PASS, символьные ссылки и вредоносные относительные пути. Подключены к `make test` и `make test-audio-stream`. Никакой настоящей SD или Switch в этих тестах нет.


## 10. Этап №219 — первый физический аудиозапуск и ручные наблюдения

После проверки происхождения NRO (№216–217) и SHA-256 SD-копии (№218) переходите к [отдельному пошаговому протоколу первого запуска №219](SWITCH_AUDIO_STAGE219_FIRST_RUN_PROTOCOL.md). Там точно описаны управление (`Minus` — диагностика, `Y` — журнал, `Plus` — штатный выход), раздельные тесты HOME и сна, длительное прослушивание, сохранение старого CSV после следующего запуска и безопасное создание evidence bundle.

В дополнение к карточке [№212](SWITCH_AUDIO_STAGE212_SESSION_TEMPLATE.md) создан [незаполненный JSON-шаблон наблюдений](SWITCH_AUDIO_STAGE219_OPERATOR_TEMPLATE.json) и read-only сверяющий инструмент [`assess_switch_audio_first_run.py`](../tools/assess_switch_audio_first_run.py). Он проверяет соответствие вручную записанных SHA/номеров сессий и реальных CSV, выявляет недостаточную телеметрию и видимые PCM/HOME-сбои, **не** подменяя слуховые и аппаратные наблюдения.

Даже `READY_FOR_INDEPENDENT_MANUAL_REVIEW` — **не аппаратный PASS**: человек обязан подтвердить независимость запусков, истинность возвратов HOME/сна, слышимое качество, дату и результат. На текущем этапе по-прежнему `HARDWARE NOT TESTED` независимо от успехов Actions.

## Этап №229 — отдельная CI-квитанция исходной NRO-сборки

Workflow [Switch toolchain readiness](../.github/workflows/switch-toolchain.yml) теперь публикует рядом с `vandal-hearts-prototype.nro` автоматически проверенную `vandal-hearts-prototype.build.json`: полный Git SHA, ветку, CI run/attempt и SHA-256 **самого NRO**. См. [руководство №229](SWITCH_AUDIO_STAGE229_CI_BUILD_RECEIPT.md) и [инструмент локальной проверки](../tools/switch_audio_ci_build_receipt.py). Существующие проверки архива №216 и HTTPS-подтверждение GitHub №217 дополнительно сверяют квитанцию со структурой ZIP, фактическим бинарником и независимыми данными запуска. Старые NRO-only артефакты продолжают читаться с явной меткой `ABSENT_LEGACY_ARTIFACT`. Это не цифровая подпись и не аппаратное испытание: `HARDWARE NOT TESTED` остаётся без настоящих логов Switch.
