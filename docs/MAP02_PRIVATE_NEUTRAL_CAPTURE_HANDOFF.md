# MAP02 — owner-private screenshot capture from BK2 neutral input windows

This is a capture *handoff* for the intervals proposed by Draft PR #418.
It is **not** an automated scene recognizer. BK2 input indices, emulator
frame counters, and screenshot presentation timings are separate facts.

## Owner-local procedure

The owner retains the original Vandal Hearts (USA) BK2, PS1 disc/BIOS and
any screenshots in private directories **outside the public checkout**.
Do not add any of these files to GitHub Actions or commit them to Git.

1. In a private shell, create a restricted directory:

       umask 077
       mkdir -p /private/vh-map02-review-png

2. Generate a strictly bounded **private capture plan** by reading the
   original BK2 end to end. This validates the known aggregate input
   fingerprint first. Example: up to 4 eligible quiet intervals,
   3 frames each:

       python3 -m tools.map02_private_bk2_capture_plan \
         /private/vandalhearts.bk2 \
         --private-plan-output /private/vh-map02-review-plan.txt \
         --max-windows 4

   The plan is created once with owner-only file permission 0600 and
   may contain private input-frame positions. The CLI refuses output
   overwrite, relative paths and directories inside a Git checkout.
   Default intervals are 180..1800 digital-button-neutral BK2 frames,
   bounded by frames with actual button activity. If none qualify, it
   creates no plan: do not manufacture scene candidates.

   Format is a small versioned ASCII file:

       VH_MAP02_CAPTURE_PLAN_V1
       movie_frames=933949
       capture_count=3
       1,before,3000,held
       1,middle,3250,neutral
       1,after,3500,held

   The numbers above are **invented examples**, not actual MAP02
   positions. The real locally generated capture indices must not
   enter public GitHub or CI.

3. Configure BizHawk with the owner-private original movie and matching
   PSX Octoshock game/firmware. Disable movie recording and enable
   read-only playback. Start playback from power-on before the earliest
   candidate frame, not a mid-movie savestate.

4. Start BizHawk with two environment variables defined in the process:

       export VH_PRIVATE_CAPTURE_PLAN=/private/vh-map02-review-plan.txt
       export VH_PRIVATE_PNG_DIR=/private/vh-map02-review-png

   Run tools/map02_bizhawk_private_neutral_capture.lua in the Lua
   console while the BK2 is in PLAY mode and before the first candidate
   is reached. The script validates the plan, expected movie frame
   count 933949, read-only state and consecutive emulator counters,
   and reads movie.getinput(candidate_input, 1) at each planned frame.

5. For each candidate, the Lua script requests client.screenshot(path)
   and checks that a PNG was written before recording its event. It
   refuses existing filenames, conflicting controller-key names,
   unexpected button-neutral states and incomplete playback. No
   picture or console log is uploaded; store them privately.

## Interpretation

The script checks the **stored movie controller state**, not whether
the actual PS1 code consumed that input. It compares the marker's
candidate BK2 input index against emu.framecount()-1, but this remains
a provisional timing convention. The frontend may render a prior or
subsequent frame and may include overlays, filters or buffering.

The labels "before", "middle" and "after" refer to controller-button
quiet intervals, **not** to an authenticated scene transition. Their
presence, stability and duration cannot establish MAP02. Only inspect
the resulting images locally to nominate a possible MAP02 range, then
seek genuinely observed source/native PlayStation state and GPU/VRAM.

GitHub CI executes the actual Lua script only with invented movie,
emulator, screenshot and file APIs, plus invented candidate input lists.
It never loads the private BK2, game disc/BIOS, screenshots or input
logs and **cannot** claim actual BizHawk replay or scene capture.
Keep every PR Draft until real owner-local observations are verified.

## Обязательная контрольная точка начала фильма

Перед запуском Lua-зонда поставьте фильм в начало (счётчик `emu.framecount()`
равен 0 или 1) и включите режим `PLAY` с `read-only`. В новой версии
скрипт **отказывает при позднем подключении**, а также требует
непрерывного последовательного продвижения кадров до первого Start:

- Кадр ввода BK2 1660: Start отпущена.
- Кадр ввода BK2 1661: Start нажата, причём Lua считывает
  `movie.getinput(1661, 1)` в текущем воспроизведении.

После этого выводится отдельная приватная строка
`VH_PRIVATE_NEUTRAL_START_PREFLIGHT` с `counter=1662`,
`candidate_input=1661` и отметкой, что PS1 input delivery ещё
не подтверждена. Если её нет или она следует после снимков,
дальнейший аудитор отклонит весь захват. Это предотвращает
случайное принятие захвата, начатого из середины BK2, за непрерывное
воспроизведение. Однако счётчик и строку Lua можно искусственно
подделать: **это не доказательство реального старта PlayStation**.
