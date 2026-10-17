# MAP02 — приватная передача локального захвата

Цель этапа: сохранить SHA-256 пользовательского игрового файла и
инструментированного PC-бинарника **до** запуска, а после получения
свидетельств ещё раз проверить неизменность этих файлов и связать их
с ранее опубликованной источниково-привязанной GTE/DrawOTag/VRAM-цепочкой.

Протокол **не запускает игру**, не копирует игровые байты, не создаёт
ложные кадры MAP02 и не загружает игровые ресурсы в GitHub.

## Перед локальным запуском

Образ игры должен принадлежать текущему пользователю и быть закрыт
от других пользователей (например, права 0600). Бинарник должен
быть обычным файлом текущего пользователя. Ссылки отклоняются.

Создать **отдельную** приватную папку с правами 0700, а затем выполнить:

~~~sh
mkdir -m 700 /private/map02/handoff
python3 -m tools.map02_local_capture_handoff prepare \
  /private/map02/handoff \
  --pc-binary /private/map02/pc-port-instrumented \
  --upstream-checkout /private/map02/VandalHearts-PcPort \
  --owned-game-image /private/map02/owned-game-image.bin \
  --frame 123
~~~

Число 123 — **пример**, а не установленный номер MAP02; нужно
использовать фактический номер выбранного вызова DrawOTag.

Теперь проверяются **реальные байты пяти источников** из локального
checkout, а не только название branch или строка commit: исходный
`libgpu.c`, `pc_raster.c`, игровые `graphics.c` и
`game_setup.c`, а также `platform/pc/Makefile`. Их Git blob
SHA-1 обязаны совпасть с зафиксированным PC-портом. Результат
дополнительно привязан к плану через SHA-256 всего набора.
Проверка повторяется перед публикацией и при каждом последующем
аудите. Любая подмена исходника или символьная ссылка вместо файла
приводит к отказу.

Подготовка эксклюзивно сохраняет файл
\`gpu-local-capture-plan.json\` с правами 0600, SHA-256 локального
PC-бинарника и принадлежащего пользователю игрового образа,
целевой номер кадра и заявленные опции инструментирования.
Также указывается pinned commit оригинального PC-порта:
\`14552fffa0e0b47e02b57592e274fc6e7a649923\`.

Важно: этот commit и флаги на этапе подготовки являются
**объявлением конфигурации**, а не доказательством, что запущенный
исполняемый файл действительно содержит именно данный исходник.

## После успешного захвата

Сначала требуется отдельно пройти уже существующий локальный конвейер:
исходная MAP02/GTE → окна оригинального GPU →
PutPixel/BlendG1 → VRAM-edges. Он должен завершиться приватным
\`gpu-native-window-scoped-source-witness.json\`.
Подробности: \`docs/MAP02_PRIVATE_FOUR_STREAM_WITNESS.md\`.

После этого:

~~~sh
python3 -m tools.map02_local_capture_handoff seal \
  /private/map02/handoff \
  --pc-binary /private/map02/pc-port-instrumented \
  --upstream-checkout /private/map02/VandalHearts-PcPort \
  --owned-game-image /private/map02/owned-game-image.bin \
  --source-bundle /private/map02/source-bundle \
  --native-windows /private/map02/native-windows \
  --scoped-capture /private/map02/scoped

python3 -m tools.map02_local_capture_handoff verify \
  /private/map02/handoff \
  --pc-binary /private/map02/pc-port-instrumented \
  --upstream-checkout /private/map02/VandalHearts-PcPort \
  --owned-game-image /private/map02/owned-game-image.bin \
  --source-bundle /private/map02/source-bundle \
  --native-windows /private/map02/native-windows \
  --scoped-capture /private/map02/scoped
~~~

Seal повторно вызывает полную проверку опубликованного источникового
GTE-свидетельства и окон GPU с идентификатором одного процесса.
Далее обе локальные контрольные суммы вычисляются повторно,
манифесты перечитываются, и в отдельной папке эксклюзивно создаётся
\`gpu-local-capture-handoff.json\` с правами 0600. Повторная
публикация с заменой файла запрещена.

Verify заново проверяет файл переданного свидетельства и его
SHA-256-привязки. Повреждение игрового файла, бинарника,
GPU/GTE-манифеста, номера кадра или приватного плана приводит
к отказу.

## Ограничение доказательства

Этот протокол проверяет целостность **предъявленных локальных
файлов**, не достоверность происхождения пользовательского образа
и не фактическое исполнение конкретного бинарника. В отчёте всегда
остаются ложными статусы
\`owned_game_binary_executed_proven\`,
\`original_gameplay_authenticated\` и
\`physical_ps1_equivalence_proven\`.

Никакого подлинного игрового кадра MAP02 или аппаратного сравнения
PlayStation этот этап сам по себе не подтверждает.

**HD-подмена остаётся выключенной** до независимого подтверждения.
