# Vandal Hearts Remake — этап №240: предзапусковая проверка интегрированного NRO

Статус аппаратных испытаний: **`HARDWARE NOT TESTED`**.

Новый `tools/verify_switch_integrated_nro_preflight.py` выполняет **локальную офлайн-сверку байтов** NRO, файла `tactical-native.sha256` из того же GitHub Actions артефакта и **отдельно зафиксированного** ожидаемого SHA-256. Он повторно использует структурную проверку NRO из `verify_switch_audio_bundle.py`. Никаких игровых файлов или оригинальных коммерческих аудиоданных не требуется.

## Подготовка

Выберите **конкретный успешный** run workflow `Switch tactical prototype with integrated audio`, например исторический [run 39022002964](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39022002964), artifact `12097456224` с именем `vandal-hearts-tactical-with-native-music`, исходный Git SHA `94d978da9cf52038bf5b8da3f2dec67c77d06700`. Эти значения относятся **только к данному run** и не означают, что он по-прежнему HEAD.

Скачайте и распакуйте **один** CI-артефакт в отдельный каталог. Запишите ожидаемый SHA-256 из проверенной страницы выбранного run **вне распакованного ZIP**. Не используйте SHA-256 самого ZIP в качестве SHA-256 NRO. Укажите полные идентификаторы:

```sh
python3 tools/verify_switch_integrated_nro_preflight.py /path/to/unpacked-artifact \
  --git-sha 94d978da9cf52038bf5b8da3f2dec67c77d06700 \
  --run-id 39022002964 \
  --artifact-id 12097456224 \
  --artifact-name vandal-hearts-tactical-with-native-music \
  --expected-nro-sha256 ACTUAL_64_LOWERCASE_HEX_SHA256_FROM_RUN
```

Замените `ACTUAL_64_LOWERCASE_HEX_SHA256_FROM_RUN` на реально независимо прочитанное значение из job summary/надежно сохраненной квитанции (здесь оно **намеренно не выдумано**). На успехе скрипт возвращает `READY_FOR_SD_TRANSFER_REVIEW`; это **не автоматический допуск к запуску**, лишь допуск к следующей ручной сверке. При несоответствии возвращает код 2 и `STOP_INVALID_PREFLIGHT`.

Проверяется имя артефакта, идентификаторы запуска (формат), отсутствие символических ссылок, точное имя NRO, формат `tactical-native.sha256`, сравнение SHA-256 с локально вычисленным и независимым ожидаемым значением, базовая NRO0-структура. Скрипт **не обращается к GitHub API** и не доказывает, что введённые run ID, artifact ID, Git SHA действительно связаны между собой. Эту связь оператор обязан проверить по первичному CI run отдельно. Не подставляйте их из случайной заметки.

После успешного предзапускового контроля используйте протокол [№239](SWITCH_AUDIO_STAGE239_INTEGRATED_NRO_DEVICE_HANDOFF.md) и существующий офлайн/SD-обмен №216–218, затем протокол физического запуска №219. Для отдельного диагностического audout NRO этот инструмент **не подходит**.

## Регрессии

`python3 tests/test_verify_switch_integrated_nro_preflight.py`

Тесты добавлены в `make test` и `make test-audio-stream`. Они работают только с синтетическим NRO-заголовком. Успешное прохождение этих тестов не подтверждает работу звука, управления, HOME, сна и CSV на Switch.

**Граница доказательства:** `READY_FOR_SD_TRANSFER_REVIEW` не устанавливает аппаратный PASS и никогда не заменяет независимые наблюдения человека.
