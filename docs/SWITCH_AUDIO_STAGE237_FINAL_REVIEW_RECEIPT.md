# Vandal Hearts Remake — этап №237: воспроизводимая итоговая квитанция H05

**Аппаратный статус — `HARDWARE NOT TESTED`.** Итоговая квитанция содержит результаты автоматического аудита **исходных файлов и неподписанных наблюдений**. Она не подтверждает физическую Switch, звук, два независимых запуска или подлинность заявлений оператора. **Даже идеальная квитанция не является разрешением на аппаратный PASS.**

## Задача

На этапе [№236](SWITCH_AUDIO_STAGE236_H05_OPERATOR_CARDS.md) проверено, что старый и новый CSV из H05 правильно соответствуют операторским карточкам. Однако для независимого аудитора полезно один раз зафиксировать **все** первичные SHA-256 и решения H01–H07, а позже доказуемо повторить проверку, не доверяя самому ранее выданному JSON-отчёту.

Новый инструмент [`tools/seal_switch_audio_h05_review.py`](../tools/seal_switch_audio_h05_review.py) предлагает две команды: `seal` и `replay`.

Команда `seal` не копирует NRO, CSV или карточки. Она сначала заново выполняет полный аудит №236, а затем полный аудит №222, проверяя согласованность обоих результатов. В JSON-квитанции сохраняются:

- SHA-256 исходного манифеста, SD transfer plan, H05 baseline/review, захваченного манифеста и операторских наблюдений.
- Исходный Git SHA, NRO SHA-256 и **полная инвентаризация всех файлов** №222, в том числе промежуточных CSV и операторских карточек, не относящихся непосредственно к паре H05.
- Привязка старого и нового CSV H05 к операторам, все статусные результаты H01–H07, запрошенные опциональные тесты, повторные тесты, отсутствующие карточки и противоречия.
- `hardware_status: HARDWARE NOT TESTED`, `manual_signoff: REQUIRED_NOT_AUTOMATED`, `physical_switch_execution: NOT_ATTESTED`.

Квитанция формируется детерминированно (сортированный canonical JSON, UTF-8, финальный перевод строки), без локальных абсолютных путей и без новых временных меток. Её **SHA-256 необходимо сохранить независимо от самой квитанции**. Отчёт не подписан цифровой подписью.

## 1. Создать и закрепить квитанцию

Когда готовы оригинальные материалы №234–236, выполните:

```sh
python3 tools/seal_switch_audio_h05_review.py seal \
  --source-bundle /safe/source-bundle \
  --transfer-plan /safe/outside/sd-transfer-plan.json \
  --captured /safe/outside/real-switch-audio-evidence-233 \
  --h05-baseline /safe/outside/h05-before-second-run.json \
  --baseline-sha256 INDEPENDENT_PINNED_BASELINE_SHA256 \
  --h05-review /safe/outside/h05-recheck-report.json \
  --review-sha256 INDEPENDENT_PINNED_REVIEW_SHA256 \
  --observations /safe/outside/operator-v2.json \
  --cards-dir /safe/outside/session-cards \
  --output /safe/outside/final-h05-review-237.json
```

Сохраните выданный `receipt_sha256` в отдельном доверенном месте. Если конечный JSON уже существует, программа **не заменяет его**. Выходной файл обязан лежать **вне source bundle, захваченного архива и каталога операторских карточек**.

Результат `H05_FINAL_REVIEW_RECEIPT_SEALED` сообщает только, что отчёт записан по итогам аудита, а поле `review_state` явно сообщает его качество:

- `READY_FOR_INDEPENDENT_MANUAL_REVIEW`: все программно проверяемые привязки согласованы.
- `INCONCLUSIVE`: обязательных карточек или измерений недостаточно.
- `INVESTIGATE`: есть противоречивые заявления или ошибочные аудиопоказатели.

Квитанция **сохраняет** `INCONCLUSIVE` и `INVESTIGATE`, а не скрывает отрицательные результаты.

## 2. Независимо повторить аудит

Предоставьте проверяющему исходные файлы, квитанцию **и отдельно закреплённый SHA-256**:

```sh
python3 tools/seal_switch_audio_h05_review.py replay \
  --source-bundle /safe/source-bundle \
  --transfer-plan /safe/outside/sd-transfer-plan.json \
  --captured /safe/outside/real-switch-audio-evidence-233 \
  --h05-baseline /safe/outside/h05-before-second-run.json \
  --baseline-sha256 INDEPENDENT_PINNED_BASELINE_SHA256 \
  --h05-review /safe/outside/h05-recheck-report.json \
  --review-sha256 INDEPENDENT_PINNED_REVIEW_SHA256 \
  --observations /safe/outside/operator-v2.json \
  --cards-dir /safe/outside/session-cards \
  --receipt /safe/outside/final-h05-review-237.json \
  --expected-receipt-sha256 INDEPENDENT_PINNED_FINAL_RECEIPT_SHA256
```

`replay` проверяет закреплённый SHA-256 квитанции, строгий формат JSON и повторно выполняет аудит **по первичным файлам**. Снова созданная каноническая квитанция должна **побайтно совпасть** с первоначальной. Изменение даже промежуточной карточки (не относящейся к паре H05), исходного CSV, аудионаблюдения или набора опциональных тестов приводит к отказу, а не к тихому повторному принятию.

Успех называется `PINNED_H05_FINAL_REVIEW_REPLAYED`. Ошибка — `INVALID_EVIDENCE` и код завершения `2`; успех кода `0` никогда не означает аппаратный PASS.

## Невозможность автоматической аппаратной приёмки

Проверка SHA-256 имеет смысл, только если независимые хеши были записаны до предполагаемой подмены; одновременная подмена файлов и всех отдельно хранимых хешей может не обнаружиться. Карточки содержат самозаявленные времена и слышимый звук. Настоящие доказательства запуска и качества звука могут быть получены лишь на физической консоли с соблюдением [протокола №219](SWITCH_AUDIO_STAGE219_FIRST_RUN_PROTOCOL.md).

[16 новых синтетических тестов](../tests/test_seal_switch_audio_h05_review.py) охватывают полный перечень исходников, воспроизводимый формат, плохие закреплённые SHA, подмены карточек и CSV, фиктивный hardware PASS, `INCONCLUSIVE/INVESTIGATE`, необязательный H06, запрет перезаписи исходников и CLI. Они включены в `make test` и `make test-audio-stream`. Реальная Switch в тестах не использовалась.
