# Vandal Hearts Remake — этап №238: нативный аудиотракт как основной путь сборки

**Статус физических испытаний: `HARDWARE NOT TESTED`.** Это устранение неоднозначностей GitHub Actions и улучшение воспроизводимости тестовых NRO, а не доказательство слышимой музыки на Nintendo Switch.

## Выявленная проблема

В логах workflow GitHub Actions от 17 октября 2026 года обнаружена одна и та же инфраструктурная ошибка:

- `Switch native music audio NRO`, run [39020749581](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39020749581): при установке `switch-sdl2` пакетный сервер devkitPro возвратил `HTTP 403`.
- `SDL2 Switch feasibility probe`, run [39020749522](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39020749522): то же самое `HTTP 403`.
- `OpenAL Switch feasibility probe`, run [39020749524](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39020749524): `dkp-libs.db` и `dkp-linux.db` не скачаны из `pkg.devkitpro.org` из-за `HTTP 403`.

Это **нельзя интерпретировать как ошибку исполняемого кода**, поскольку соответствующие workflow останавливаются **до компиляции**. Одновременно успешные [нативная сборка audout](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39020749646) и [интегрированный тактический NRO](https://github.com/stanmasked/vandal-hearts-switch-remaster/actions/runs/39020749515) подтверждают, что путь без загрузки пакетов SDL2/OpenAL способен пройти компиляцию и host-регрессии. Это не аппаратное свидетельство.

## Изменения

### Исправлены три необязательных workflow

[`switch-audio-nro.yml`](../.github/workflows/switch-audio-nro.yml), [`sdl2-probe.yml`](../.github/workflows/sdl2-probe.yml) и [`openal-probe.yml`](../.github/workflows/openal-probe.yml) теперь:

- При неудачной загрузке пакета сохраняют стандартный текст ошибки в журнал CI и вызывают [`classify_switch_portlib_install.py`](../tools/classify_switch_portlib_install.py).
- Сообщают `EXTERNAL_DEVKITPRO_MIRROR_HTTP_403`, если pacman или curl вернули соответствующий код, отдельно от `PACKAGE_NOT_FOUND`, сетевых и неизвестных ошибок.
- Не продолжают многократные бесполезные ожидания при уже обнаруженном HTTP 403.
- **Не превращают неисправный SDL2/OpenAL билд в зелёный**: классификатор всегда возвращает код завершения `2`, а шаг установки завершается ошибкой. Поддельная замена SDL2 двоичным файлом без SDL2 не допускается.
- Исправляют OpenAL-проверку: после установки `switch-openal-soft` проверяется наличие заголовка `AL/al.h`, а не ошибочная сторонняя предпосылка `sdl2-config`.

Если зеркало вновь станет доступным, полноценные сборки SDL2/OpenAL продолжатся в обычном режиме; классификация не отключает проверки их кода.

### Нативная музыка — предпочтительный рабочий путь

[`switch-audout-nro.yml`](../.github/workflows/switch-audout-nro.yml) собирает `build/audout-audio-switch-probe.nro`. Он использует libnx `audout`, синтетические музыкальные данные по умолчанию и допускает **только локальные пользовательские** аудиоресурсы. Никаких оригинальных коммерческих SEQ/VH/VB в GitHub нет.

[`switch-tactical-music-nro.yml`](../.github/workflows/switch-tactical-music-nro.yml) собирает `build/vandal-hearts-prototype.nro` с тактическим интерфейсом и нативным аудиотрактом. Обе сборки теперь:

- повторяют host-тесты аудиотракта;
- проверяют наличие итогового NRO;
- записывают `audout-native.sha256` либо `tactical-native.sha256` с SHA-256 **самого NRO**, а не ZIP-артефакта;
- выводят коммит GitHub и хеш в job summary, помечая `HARDWARE NOT TESTED`;
- публикуют NRO и файл с хешем вместе в соответствующем CI-артефакте.

Хеш внутри одного и того же ZIP — контроль случайного повреждения, **не криптографическая подпись** и не независимое подтверждение подлинности. Перед переносом на SD сверяйте коммит, номер запуска и контрольные SHA-256 со страницей соответствующей успешной сборки GitHub Actions. Отдельный `Switch toolchain readiness` также публикует NRO с привязкой к конкретной GitHub Actions-квитанции этапа №229.

## Практический следующий шаг

Для тестирования **тактического интерфейса вместе с музыкой** используйте интегрированный NRO из успешной сборки `Switch tactical prototype with integrated audio`. Для отдельной диагностики синтеза/ресемплирования можно использовать audout music probe.

Порядок действий на физической Nintendo Switch остаётся описан в [протоколе №219](SWITCH_AUDIO_STAGE219_FIRST_RUN_PROTOCOL.md). На карту надо переносить **точную** согласованную сборку, с соблюдением безопасности homebrew-среды, проверять слышимость, HOME, сон и последовательно собирать оригинальные CSV.

[9 новых host-тестов](../tests/test_classify_switch_portlib_install.py) воспроизводят типовые реальные строки ошибок `dkp-pacman`/`curl`, сетевые отказы, отсутствие пакета, обычную ошибку компилятора и проверяют, что классификатор никогда не возвращает успешный код вместо исправного билда.

**Открытый вопрос:** доступность внешнего зеркала devkitPro SDL2/OpenAL может измениться позднее. Даже когда оно восстановится, это не заменяет реальные испытания Switch. Приоритет запускаемой игры — `libnx/audout`, пока SDL2/OpenAL остаются необязательными экспериментами.
