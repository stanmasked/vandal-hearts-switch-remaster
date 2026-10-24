# MAP02 — приватная предварительная проверка образа и BK2

Эта команда локально проверяет, что CUE ссылается на один BIN-трек
MODE2/2352, ISO9660 PVD валиден, известный профиль ресурса
`DATA/M_MAP02.PRS` совпадает с ранее проверенным образом
`Vandal_Hearts_(RU)_v1.6`, а заголовок BK2 указывает на
`Vandal Hearts (USA) / PSX / Octoshock` с настройкой одного контроллера
и без карт памяти. Кроме заголовка теперь полностью читается и
валидируется журнал ввода BK2: LogKey, формат каждой записи,
закрывающий маркер и ожидаемые **933 949 кадров**.
Команда не запускает эмулятор.

## Запуск на компьютере владельца

    python3 -m tools.map02_private_disc_movie_preflight \
      "/absolute/path/Vandal_Hearts_(RU)_v1.6.cue" \
      "/absolute/path/vandalhearts.bk2"

Оба исходника и BIN, на который ссылается CUE, должны быть обычными
локальными файлами вне Git checkout/worktree. CUE должен ссылаться на BIN
по имени файла в той же папке. Программа также проверяет точный размер
ранее исследованного RU v1.6 BIN — 664 849 248 байт (282 674 raw-сектора).
Для PVD и 12 секторов MAP02 проверяются синхрослово, режим 2,
адрес MSF (BCD MM:SS:FF, логический LBA + 150 кадров pregap),
совпадение обеих копий четырёхбайтового CD-XA subheader и отсутствие
признака Form 2 (у этих ресурсов ожидается Mode 2 Form 1).
Это исключает простую подмену нужного сектора полезными данными
с другим адресом, но не удостоверяет весь диск.
Программа читает только PVD на LBA 16 и 12 raw-секторов,
содержащих ресурс MAP02 с LBA 7116 и длиной 22 783 байта;
весь BIN в память не загружается. Сравнение выполняется с хешем ресурса
из прежнего локального аудита, но сам хеш и пути не выводятся.

Только совпадение первых необходимых секторов без полного ожидаемого
размера образа больше не принимается как готовый профиль. Однако даже
правильный размер и совпадение ресурса не являются полной проверкой
хеша BIN или подлинности релиза: остальные секторы не хешируются.

## Проверка запуска BK2 от включения консоли

Для рассматриваемых двух холодных воспроизведений не подходят
видео-записи, начатые из savestate или SaveRAM. Помимо проверки всей
вводимой последовательности локальный анализатор теперь отказывает
файлу BK2, если его `Header.txt` содержит поле, начинающееся на
`StartsFromSave` (без учёта регистра), **даже при значении `False`**.
В BK2 наличие `StartsFromSavestate` может означать якорь сохранения
независимо от текстового значения. Архивы с `CoreState` / `SaveRAM`
также запрещены: фактическое состояние внутри ZIP имеет приоритет
над недостаточным описанием в заголовке.

Отчёт включает `movie_has_no_declared_save_anchor=true/false`.
Значение `false` блокирует
`media_preflight_ready_for_owner_replay` до запуска эмулятора.
`true` говорит лишь об отсутствии известных признаков сохранения
**в архиве**, а не доказывает фактический PS1 power-on или верную
версию Octoshock. Уже работающий BizHawk отдельно проверяется через
Lua-функции `movie.startsfromsavestate()` и
`movie.startsfromsaveram()`.

## Необязательная полная проверка BIN

Чтобы дополнительно сверить **все байты** ранее исследованной личной копии
RU v1.6, создайте **вне Git** файл, содержащий только её уже сохранённый
64-символьный SHA-256. Не записывайте контрольную сумму в командную строку
или публичную документацию.

На Linux/macOS выдайте этому файлу права `0600`:

    chmod 600 /private/vh-full-bin.sha256

Выполните:

    python3 -m tools.map02_private_disc_movie_preflight \
      "/private/Vandal_Hearts_(RU)_v1.6.cue" \
      /private/vandalhearts.bk2 \
      --private-full-bin-sha256-file /private/vh-full-bin.sha256

Анализатор последовательно прочитает BIN блоками не более 1 МиБ, не
создавая вторую копию файла и не выводя контрольную сумму. Появятся
`full_bin_sha256_requested=true` и `full_bin_sha256_verified=true/false`.
Если полная проверка не запрошена, второе поле остаётся `null`;
это **не** означает успешную проверку полного файла.

При несовпадении полного SHA-256
`media_preflight_ready_for_owner_replay=false`, даже если размер,
PVD и 12 секторов MAP02 совпадают. Нельзя обходить это требование
для заявленного эталонного образа. Совпадение подтверждает
**идентичность локальной ранее сохранённой копии**, но не легальность,
подлинность официального релиза или совместимость с таймингом BK2.

## Создание приватного SHA-256 без публикации (этап №494)

Если у вас есть локальная копия BIN/CUE, но ещё нет отдельного
приватного файла эталонной контрольной суммы, появилась команда,
которая **не выводит сам хеш** и не требует загрузки 665 МБ в GitHub:

    mkdir -p /private/vh-owner-digests
    chmod 700 /private/vh-owner-digests

    python3 -m tools.map02_private_bin_digest_init \
      "/private/Vandal_Hearts_(RU)_v1.6.cue" \
      /private/vh-owner-digests/vh-full-bin.sha256

Команда принимает CUE, находит **соседний** BIN, проверяет ровно один
трек MODE2/2352, правильный размер диска, ISO9660 PVD, volume ID и
контрольный профиль MAP02. Только после этого она последовательно
прочитает **все байты** BIN блоками не более 1 МиБ, сверит неизменность
его дескриптора и контрольных секторов и создаст новый файл эталона
через эксклюзивное открытие (без перезаписи существующего).
Каталог должен принадлежать владельцу и быть закрыт для других
пользователей; файл создаётся с POSIX-правами 0600. Ошибки не печатают
ни пути, ни исходные данные, ни значение SHA-256. После записи файл
проверяется повторным чтением. При поздней ошибке новая запись удаляется.

**Это самосозданный эталон, а не независимое доказательство
аутентичности оригинала.** Он пригоден для обнаружения последующих
изменений локальной копии, если исходная копия в момент создания
соответствовала уже известному MAP02-профилю. Для независимого
подтверждения происхождения требуется заранее доверенный хеш из
отдельного источника. Сам эталон нельзя отправлять в публичный репозиторий.

Для последующих приватных проверок используйте полученный файл:

    python3 -m tools.map02_private_disc_movie_preflight \
      "/private/Vandal_Hearts_(RU)_v1.6.cue" \
      /private/vandalhearts.bk2 \
      --private-full-bin-sha256-file \
      /private/vh-owner-digests/vh-full-bin.sha256

Подключённый Google Drive подтверждает наличие двух файлов русской
версии и их размер, но текущий способ загрузки имеет ограничение
256 МиБ на файл. **В рамках этого этапа исходный BIN не был
прочитан целиком, а его реальный SHA-256 не вычислялся.**
Операции выше выполняются локально у владельца; публичный CI
проверяет только вымышленные короткие BIN и имитации профиля.

## Приватная проверка PSX BIOS по заголовку BK2 (этап №499)

В официальном BizHawk заголовок новой BK2-записи может содержать
метаданные обслуженной прошивки в полях вида
`PSX_Firmware_<идентификатор>`: их имя формируется через
`FirmwareID.MovieHeaderKey`, а значение сохраняется из
`FirmwareManager.RecentlyServed` (SHA-1). Эти поля отличаются от
общего `FirmwareSHA1`, который не обязательно идентифицирует PSX BIOS.

Добавлен отдельный **локальный** инструмент:

    python3 -m tools.map02_private_psx_firmware_probe \
      /private/vandalhearts.bk2 \
      /private/psx-bios-candidate.bin

Оба файла должны быть регулярными абсолютными путями за пределами
любого Git checkout. Содержимое BK2 читается только из ограниченного
проверенного ZIP, BIOS-хешируется потоково SHA-1 без вывода результата.
Из BK2 выделяются **только** строго валидные поля
`PSX_Firmware_*`. При отсутствии таких полей или при конфликте
разных PSX-хешей инструмент честно сообщает, что сопоставление
не удалось, даже если имеется общий `FirmwareSHA1`. Результат
содержит только агрегированные булевы поля и число записей — ни
имён прошивок, ни значений хешей, ни приватных путей.

- Код завершения `0`: байты предложенного BIOS совпали с
  однозначным PSX firmware SHA-1 из BK2.
- Код `2`: нет подходящих метаданных, они неоднозначны или кандидат
  не совпал; нельзя считать BIOS подтверждённым.
- Код ошибки: некорректный BK2, запрещённые пути, изменившийся файл
  или другая ошибка. Диагностика не раскрывает содержимое приватных
  файлов.

**Это проверка метаданных записи, а не работающего эмулятора.**
Даже при коде `0` мы не доказали, что EmuHawk использовал именно этот
BIOS, запустил Octoshock или дошёл до MAP02. Значение SHA-1 применяется
только ради совместимости с историческим форматом BK2: оно не должно
использоваться как самостоятельное современное доказательство
подлинности firmware. На Stage524 фактический пользовательский BK2
проверен локально: содержит единственное поле `PSX_Firmware_U`, и BIOS
SCPH-7003 v3.0 совпадает с ним. Альтернативный SCPH-7001/9001 v4.1 не
совпадает. CI по-прежнему использует только вымышленные BK2 и BIOS;
приватные файлы не загружаются.

## Интерпретация

- `media_preflight_ready_for_owner_replay=true` — структура диска, известный
  MAP02-ресурс, метаданные и полный журнал ввода BK2 соответствуют
  ожидаемому профилю. Можно переходить к следующему шагу локального запуска.
- `movie_has_no_declared_save_anchor=false` — в BK2 указан запуск
  из savestate или SaveRAM; нельзя принимать этот файл как прохождение
  от включения консоли.
- `movie_input_log_matches_expected_frame_count=false` — журнал ввода
  синтаксически корректен, но содержит не 933 949 кадров; воспроизведение
  исходного прохождения нельзя считать подготовленным. Неверный LogKey,
  повреждённые строки или отсутствующий конец журнала отклоняются как ошибки.
- `disc_size_matches_audited_profile=false` — файл неполный или имеет
  другую длину, даже если проверенные PVD и MAP02 совпали; такой образ
  не допускается к автоматическому запуску.
- `false` — не интерпретируйте последующие кадры как подтверждение MAP02;
  проверьте выбранные файлы и версию ресурса.
- `exact_disc_movie_compatibility_verified=false` остаётся false намеренно:
  совпадение ID/ресурса и заголовка фильма не доказывает, что все изменения
  русской локализации совместимы с таймингом USA-прохождения.
- Отдельный BIOS probe сопоставляет кандидата с метаданными BK2, но сам по
  себе не доказывает, что эмулятор загрузил этот файл. Автоматическое
  runtime-свидетельство V4 теперь проверяет `FirmwareManager.RecentlyServed`
  для `PSX/U` и записывает только булев маркер совпадения с заголовком BK2.
  Это остаётся локальным самоотчётом, а не криптографической аттестацией.
  Ручное свидетельство без ожидаемого хеша записывает bios=unverified;
  его можно использовать для ограниченной диагностики, но не для
  автоматического paired-acceptance.
- Реальное ядро Octoshock, доставку ввода, синхронизацию кадра с вводом,
  идентичность игровой сцены и GPU/VRAM preflight не подтверждает. После
  preflight всё равно нужны два отдельных холодных воспроизведения и
  независимая проверка изображений.

## Приватность

Результат содержит только агрегированные булевы признаки; исходные пути,
хеши, игровые байты и PNG не печатаются и не сохраняются. Нельзя отправлять
BIN/CUE/BIOS/BK2, планы кадров, реальные снимки или журналы в GitHub Actions.
CI использует только синтетические секторные данные и вымышленный BK2.


## Stage524 — safely stage a large private BIN for transfer

The current owner-local Drive image is 664,849,248 bytes, larger than the
connector's 268,435,456-byte single-file download limit. Do not add the BIN,
the BK2, a part, or the generated private manifest to Git.

The helper tools/map02_private_disc_parts.py splits an unchanged local BIN
into parts of 220 MiB by default (well below the transfer limit), and writes a
private JSON manifest with the part order, sizes, and SHA-256 digests. It
refuses to overwrite existing outputs. The optional --expected-sha256 flag
compares the streamed source against a digest already pinned in the owner's
private local inventory; a mismatch removes every part and writes no manifest.
This is a continuity check against that previously observed copy, not proof of
release authenticity. Do not commit or publish the private digest. The inverse
command verifies each part and the whole reconstructed image before reporting
success; a mismatch deletes the partial output rather than leaving a misleading
reconstructed file.

Run from a clean checkout of the current working branch. Set
VH_EXPECTED_BIN_SHA256 locally from the private pinned inventory before using
the optional digest check; do not put it into a repository file:

    python3 -m tools.map02_private_disc_parts split \
      "/absolute/path/Vandal_Hearts_(RU)_v1.6.bin" \
      "/absolute/path/vh-map02-private-parts" \
      --expected-sha256 "$VH_EXPECTED_BIN_SHA256"

Upload the three .partNN files and the .parts.json manifest to the
owner-private Vandal Hearts Drive folder. Keep the manifest private because it
contains hashes of the original media. The CUE remains a separate small file.
After the parts are available, download them individually, reassemble into a
private workspace, and compare the resulting full-image digest with the
manifest before running any emulator. This helper and its CI tests use only
invented bytes; they do not include or inspect the retail image.

To reassemble after all files are present in one local directory:

    python3 -m tools.map02_private_disc_parts join \
      "/absolute/path/vh-map02-private-parts/Vandal_Hearts_(RU)_v1.6.bin.parts.json" \
      "/absolute/path/vh-map02-private-parts" \
      "/absolute/path/private-workspace/Vandal_Hearts_(RU)_v1.6.bin"
