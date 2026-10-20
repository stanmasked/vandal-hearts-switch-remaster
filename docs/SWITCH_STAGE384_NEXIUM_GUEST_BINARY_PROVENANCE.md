# Stage384 — идентификатор исполняемого NeXium для каждого нового CI-прогона

## Зачем это нужно

Stage371 последовательно собирает один и тот же проверенный NRO и запускает две гостевые аудиосессии (выдержки 6 и 12 секунд). Но сам NeXium загружается из публичного релиза по **изменяемому тегу `nightly`**. Одинаковый SHA-256 NRO **не подтверждает**, что все прошлые прогоны использовали побайтово одинаковую версию NeXium.

Stage384 устраняет этот пробел **для новых запусков**. Непосредственно после скачивания эмулятора workflow сохраняет компактную квитанцию с:

- ID релиза и ID конкретного GitHub asset, названием и заявленным размером;
- SHA-256 действительно скачанного `nexium-linux-x86_64.tar.gz`;
- SHA-256 и длиной действительно исполняемого `nexium-gui` или `nexium`;
- исходным SHA коммита и ID текущего запуска Stage371;
- отметкой, предоставил ли GitHub API дополнительный SHA-256 asset и совпал ли он.

При наличии объявленного GitHub SHA-256 несовпадение — ошибка. Если поле `digest` отсутствует, скрипт **не объявляет архив подписанным**: он фиксирует наблюдаемый SHA-256, который впоследствии можно сравнивать между прогонами.

После второй гостевой сессии Stage371 повторно читает архив и исполняемый файл и отклоняет сборку, если байты, длина, режим запуска или идентификатор исходного CI-процесса отличаются от квитанции. Прежний анализ исходных CSV, NRO и оптических PNG остаётся обязательным.

## Проверки

```sh
python3 -m unittest discover -s tests -p test_audit_stage384_nexium_binary_provenance.py -v
python3 -m py_compile tools/audit_stage384_nexium_binary_provenance.py
```

Гостевой workflow вызывает две команды:

```sh
python3 tools/audit_stage384_nexium_binary_provenance.py create \
  --release runtime-evidence/nexium-release-metadata.json \
  --archive /tmp/vh-stage371-nexium.tar.gz --binary "$NEXIUM_BIN" \
  --receipt runtime-evidence/nexium-runtime-binary-provenance.json \
  --run-id "$GITHUB_RUN_ID" --head "$GITHUB_SHA"

python3 tools/audit_stage384_nexium_binary_provenance.py verify \
  --archive /tmp/vh-stage371-nexium.tar.gz --binary "$NEXIUM_BIN" \
  --receipt runtime-evidence/nexium-runtime-binary-provenance.json \
  --run-id "$GITHUB_RUN_ID" --head "$GITHUB_SHA"
```

CI публикует **только JSON-квитанцию**, не публикует исходный исполняемый NeXium, его `.tar.gz`, ROM, музыку или PCM. Отдельный статус аудиосессии по-прежнему определяется её оригинальными гостевыми квитанциями.

**Ограничения:** SHA-256 фиксирует идентичность байтов, но не гарантирует безопасность или подлинность неподписанного бинарного файла, и сам по себе не доказывает, что NeXium правильно эмулирует консоль. Для старых запусков до Stage384 двоичные хеши NeXium не сохранились; ретроспективно объявлять их одинаковыми нельзя. Виртуальный PCM/оптические квитанции не подтверждают звучание на динамиках физической Nintendo Switch. HOME/сон/SD на железе по-прежнему **HARDWARE NOT TESTED**. Аудиокод, владение PCM-буферами и ожидание 12 мс не изменяются.
