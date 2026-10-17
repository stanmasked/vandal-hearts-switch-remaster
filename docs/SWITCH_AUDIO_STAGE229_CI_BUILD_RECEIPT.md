# Vandal Hearts Remake — этап №229: CI-квитанция точного NRO

**Статус оборудования — `HARDWARE NOT TESTED`.** Это проверка идентичности программной сборки, а не свидетельство запуска Nintendo Switch или прослушивания музыки.

## Зачем это нужно

Ранее [сверка с GitHub Actions №216–217](SWITCH_AUDIO_STAGE214_DEVICE_HANDOFF.md) требовала вручную указать Git SHA, номер CI-запуска и SHA-256 извлечённого NRO. Проверки проводились корректно, но **сам CI-артефакт не содержал отдельной квитанции с идентичностью собранного бинарника**.

Начиная с этапа №229, workflow [Switch toolchain readiness](../.github/workflows/switch-toolchain.yml) после `make verify-nro` вызывает [`switch_audio_ci_build_receipt.py`](../tools/switch_audio_ci_build_receipt.py) и публикует **два файла вместе** в артефакте `vandal-hearts-switch-prototype`:

```text
vandal-hearts-prototype.nro
vandal-hearts-prototype.build.json
```

Путь может иметь общий префикс `build/` в архиве; оба файла должны находиться **рядом**, без независимой замены одного из них.

## Что содержит JSON-квитанция

Схема `vh-switch-audio-ci-build-receipt/v1` сохраняет:

- `git_sha`: полный Git-коммит, из которого workflow собрал NRO;
- `head_branch`, `repository`, `workflow_name`, `workflow_path`;
- `run_id` и `run_attempt`: номер и попытка запуска GitHub Actions;
- `nro.name`, `nro.size`, `nro.sha256`: конкретные байты скомпилированного `vandal-hearts-prototype.nro`;
- `hardware_status: HARDWARE NOT TESTED`, `provenance: CI_METADATA_SELF_REPORTED_NOT_SIGNED`.

Квитанция создаётся **только после проверки NRO**; затем workflow повторно читает её и проверяет SHA-256 исходного бинарника, Git SHA, ID запуска и название ветки. Уже существующая квитанция не перезаписывается — для новой сборки должен быть чистый каталог `build`.

## Как вручную проверить после скачивания

Скачайте ZIP-артефакт из успешного **конкретного запуска** GitHub Actions и распакуйте оба файла без редактирования. Убедитесь, что JSON и NRO принадлежат **одной и той же** скачанной сборке.

```sh
python3 tools/switch_audio_ci_build_receipt.py verify \
  /path/to/extracted/vandal-hearts-prototype.nro \
  --receipt /path/to/extracted/vandal-hearts-prototype.build.json \
  --expected-git-sha ACTUAL_40_HEX_GITHUB_COMMIT \
  --expected-run-id ACTUAL_GITHUB_ACTIONS_RUN_ID \
  --expected-branch test/cdxa-extract-decode-pipeline
```

При успехе выдаётся `CI_RECEIPT_AND_NRO_BYTES_MATCH`. Это **не** гарантия, что JSON действительно создан GitHub, если проверять только скачанные файлы: злоумышленник может подменить и NRO, и **неподписанную** квитанцию.

Поэтому дополнительно выполните существующую строгую проверку [этапа №217](../tools/verify_switch_audio_live_preflight.py). Она получает **актуальные** данные `run`, `artifact` и HEAD ветки по HTTPS из GitHub REST API, сверяет SHA-256 всего ZIP с дайджестом опубликованного артефакта, SHA-256 и размер самого NRO с локальным манифестом, а теперь также сверяет приложенную CI-квитанцию с **действительным** Git SHA, ID запуска, его попыткой и веткой.

```sh
python3 tools/verify_switch_audio_live_preflight.py \
  /path/to/verified-evidence-bundle \
  --artifact-zip /path/to/downloaded-vandal-hearts-switch-prototype.zip \
  --run-id ACTUAL_GITHUB_ACTIONS_RUN_ID \
  --artifact-id ACTUAL_GITHUB_ARTIFACT_ID
```

Важные ограничения:

1. Старые артефакты с **одним только NRO** не удалены из процесса проверки: для них в отчёте `verified_archive.ci_receipt_state` будет `ABSENT_LEGACY_ARTIFACT`. Это не поддельная квитанция и не основание объявлять аппаратный `PASS`.
2. Новые ZIP с квитанцией получают `ci_receipt_state: VERIFIED_UNTRUSTED` **только после** проверки её структуры, расположения рядом с NRO, SHA-256/размера, отсутствия лишних файлов и отдельной привязки к действительным полям GitHub run. Значение `VERIFIED_UNTRUSTED` сознательно не называется цифровой аттестацией.
3. Неверные/повторные JSON, разные попытки GitHub Actions, неверная ветка/коммит, несоответствие NRO и посторонние файлы внутри официального ZIP вызывают отказ.
4. GitHub Actions может перепубликовать результаты при rerun; поле `run_attempt` отличает попытки одного запуска. Не переносите квитанцию от другой попытки.
5. Дайджест ZIP, возвращённый GitHub, **не равен** SHA-256 NRO. В JSON указывается именно NRO, который затем копируется на SD.
6. Не добавляйте ROM, оригинальные игровые ресурсы или личные диагностические журналы в публичный GitHub.

Непосредственный перенос NRO на SD продолжает проверяться [этапом №218](../tools/verify_switch_audio_sd_transfer.py). Даже если источник GitHub, локальная квитанция и SD-копия совпали побайтно, это **не доказывает** реальный старт на консоли, работоспособность звуковых драйверов, длительность прослушивания или наличие двух независимых физических запусков.

## Автоматические проверки

[20 синтетических регрессионных тестов](../tests/test_switch_audio_ci_build_receipt.py) охватывают генерацию, детерминированность, строгость SHA/имён, запрет перезаписи, неправильную ветку и попытку CI, двойную квитанцию, посторонние ZIP-члены, повреждённый JSON, подменённый NRO, legacy-совместимость, CLI и расширенную live-preflight-проверку. Они входят в `make test` и `make test-audio-stream`, без использования реальной Nintendo Switch.

**Следующий практический этап** — скачать артефакт успешного запуска, подтвердить `NRO + build.json`, вручную перенести NRO на SD, выполнить H01–H05 на физической Switch и сохранить сырые журналы. До реальных испытаний статус остаётся `HARDWARE NOT TESTED`.
## Этап №230 — объединённый контроль GitHub → NRO → SD

Новый [инструмент проверки №230](SWITCH_AUDIO_STAGE230_PRELAUNCH_GATE.md), `tools/verify_switch_audio_launch_gate.py`, объединяет актуальный HTTPS preflight GitHub №217, CI-квитанцию NRO №229 и повторную проверку самостоятельно скопированного на SD NRO по плану №218. Он требует совпадение точного Git-коммита, CI run/attempt, SHA-256 скачанного ZIP и SHA-256 NRO в локальном каталоге SD. Старые артефакты без CI-квитанции не принимаются в этом предзапусковом режиме. Успешный ответ `READY_FOR_MANUAL_DEVICE_LAUNCH` означает только согласованность файлов перед **реальным** запуском на физической Nintendo Switch; `HARDWARE NOT TESTED` сохраняется.
