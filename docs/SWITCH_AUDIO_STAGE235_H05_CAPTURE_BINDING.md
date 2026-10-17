# Vandal Hearts Remake — этап №235: связь проверки H05 с архивом исходных CSV

> **Аппаратный статус: `HARDWARE NOT TESTED`.** Совпадение контрольных хешей не доказывает, что действительно состоялись два независимых запуска Nintendo Switch, музыка была слышна или использовалась физическая SD-карта.

## Зачем нужна связка

[Этап №234](SWITCH_AUDIO_STAGE234_H05_CSV_PERSISTENCE.md) закрепляет исходный перечень CSV **до** второго заявленного запуска и проверяет появление нового CSV **после** него. [Этап №233](SWITCH_AUDIO_STAGE233_RAW_SD_CAPTURE.md) отдельно переносит выбранные исходные CSV и NRO в проверяемый архив. До №235 эти два результата можно было вручную перепутать: взять правильный H05-отчёт, но приложить к нему **не тот** сохранённый CSV или переставить сессии.

Новый [`tools/verify_switch_audio_h05_capture_binding.py`](../tools/verify_switch_audio_h05_capture_binding.py) независимо перечитывает и связывает:

1. Оригинальный `source-bundle` с точным NRO, Git SHA и URL CI-запуска.
2. Исходный `sd-transfer-plan.json`, SHA-256 которого закреплён в H05 baseline.
3. H05 baseline №234 — старый CSV, начальный перечень номерных журналов, NRO и отдельный SHA-256 всей карточки.
4. H05 review №234 — результат второго чтения, старые и новые хеши, дополнительные неатрибутированные CSV. Его **SHA-256 нужно сохранить независимо**, когда результат `recheck` записан в файл.
5. Итоговый evidence bundle №233 со всеми сохранёнными CSV, SHA-256-манифестом и NRO.

Итоговое ограничение: **старый CSV обязан находиться в архиве раньше нового**, иметь свой исходный SHA-256 и размер; новый CSV должен отсутствовать в предварительном перечне и совпадать с SHA-256 №234. Дополнительные выбранные CSV допустимы только если они были **старыми** или отдельно перечислены в H05 review как неатрибутированные новые.

## Подготовка H05 review с независимым SHA-256

После полноценного `record` / заявленного реального второго запуска / `recheck` этапа №234 сохраните стандартный JSON-вывод `recheck` в отдельный файл:

```sh
python3 tools/verify_switch_audio_h05_csv_persistence.py recheck \
  --source-bundle /safe/original-source-bundle \
  --sd-root /Volumes/ACTUAL_SWITCH_SD \
  --transfer-plan /safe/outside/sd-transfer-plan.json \
  --baseline /safe/outside/h05-before-second-run.json \
  --expected-baseline-sha256 ORIGINAL_PINNED_BASELINE_SHA256 \
  --new-csv audio-diagnostics-0001.csv \
  --operator-confirmed-second-run \
  > /safe/outside/h05-recheck-report.json
```

Выполните самостоятельно **после записи**, без редактирования файла:

```sh
shasum -a 256 /safe/outside/h05-recheck-report.json
```

Сохраните оба независимых хеша (старой карточки и review) вне архива и JSON. Нельзя считать SHA-256 из той же непроверенной папки доказательством происхождения.

## Проверка после копирования по №233

Импортируйте CSV в новый каталог так, чтобы старый файл был **раньше** нового в аргументах `--csv`. После этого проверьте сохранённые данные, **не требуя доступной SD-карты**:

```sh
python3 tools/verify_switch_audio_h05_capture_binding.py \
  --source-bundle /safe/original-source-bundle \
  --transfer-plan /safe/outside/sd-transfer-plan.json \
  --captured /safe/outside/real-switch-audio-evidence-233 \
  --h05-baseline /safe/outside/h05-before-second-run.json \
  --baseline-sha256 ORIGINAL_PINNED_BASELINE_SHA256 \
  --h05-review /safe/outside/h05-recheck-report.json \
  --review-sha256 INDEPENDENT_PINNED_RECHECK_SHA256 \
  > /safe/outside/h05-capture-binding-235.json
```

Используйте именно реальные имена CSV и их исходные файлы; названия в примере — иллюстрация, не настоящие измерения.

## Что подтверждается программно

- Байт-в-байт сохранены SHA-256 H05 baseline и review.
- Неподписанные source manifest и SD transfer plan неизменны относительно закреплённых SHA-256.
- Исходные NRO, размер бинарника, Git SHA и CI URL совпадают между источником и архивом.
- Каждый CSV из архива проходит полную проверку №213, имеет безопасный номерной путь `session-NN/` и завершается событием `EXIT`.
- Старый и новый CSV имеют правильные хеши и представлены **в правильном порядке**.
- Любые дополнительно выбранные новые CSV остаются неатрибутированными, а не записываются автоматически в «аппаратно подтверждённые» сессии.

| Ответ | Значение |
| --- | --- |
| `H05_CAPTURED_EVIDENCE_CONSISTENT_FOR_MANUAL_REVIEW` | Все обязательные байтовые привязки и порядок выбранных CSV согласованы |
| `INVALID_EVIDENCE` | Ошибка контрольного хеша, подмена источника, неправильный NRO, отсутствие или перестановка CSV, поддельный статус, неправильный формат или иная несогласованность |

Даже успешный результат содержит `second_run_attested: false`, `physical_sd_attested: false`, `audible_audio_attested: false` и `manual_signoff: REQUIRED_NOT_AUTOMATED`. Для настоящей приёмки используйте оригинальные карточки и процедуры [№219](SWITCH_AUDIO_STAGE219_FIRST_RUN_PROTOCOL.md), [№222](SWITCH_AUDIO_STAGE222_HARDWARE_HANDOFF.md) и [№232](SWITCH_AUDIO_STAGE232_DEVICE_EVIDENCE_BINDING.md).

## Ограничения и тестирование

При совместной подмене всех исходных файлов **и независимых контрольных записей** одна только система SHA-256 не обеспечивает подпись или достоверность оператора. Нельзя автоматически подтверждать независимость запусков по числу файлов.

[25 синтетических host-тестов](../tests/test_verify_switch_audio_h05_capture_binding.py) покрывают сохранённый порядок, пропущенные CSV, подмену H05 review и baseline, неверные NRO/CI URL, изменение исходного манифеста/плана, повреждение копий, повторное использование старых данных и дополнительные неатрибутированные CSV. Оба host-набора `make test` и `make test-audio-stream` выполняют эти тесты без SD и физической консоли.
