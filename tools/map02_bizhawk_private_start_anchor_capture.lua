-- OWNER-LOCAL ONLY. Capture a 3-frame Start anchor, not a MAP02 scene.
-- Run from power-on with the owner's Vandal Hearts USA/Octoshock BK2.
-- Set VH_PRIVATE_PNG_DIR to an existing absolute directory OUTSIDE GitHub.
-- No files are sent anywhere; only client.screenshot writes local PNGs.
local FIRST_INDEX = 1660
local START_INDEX = 1661
local LAST_INDEX = 1662
local EXPECTED_MOVIE_FRAMES = 933949
local PNG_SIGNATURE = "\137PNG\r\n\26\n"

local function fail(code)
  print("VH_PRIVATE_START_CAPTURE_ERROR " .. code)
  return
end

local root = os.getenv("VH_PRIVATE_PNG_DIR")
if type(root) ~= "string" or #root < 4 or #root > 240
    or root:find("%.%.") or root:find("[\r\n]") then
  return fail("private_absolute_capture_dir_required")
end
local is_unix_absolute = root:sub(1, 1) == "/"
local is_windows_absolute = root:match("^[A-Za-z]:[\\/]") ~= nil
if not is_unix_absolute and not is_windows_absolute then
  return fail("private_absolute_capture_dir_required")
end
if movie.length() ~= EXPECTED_MOVIE_FRAMES then
  return fail("wrong_private_movie_length")
end
if movie.getreadonly() ~= true then
  return fail("movie_must_be_read_only")
end

local function start_button(data)
  if type(data) ~= "table" then return nil end
  local a, b = data["Start"], data["P1 Start"]
  if a ~= nil and b ~= nil and a ~= b then return nil end
  if a ~= nil then return a == true end
  if b ~= nil then return b == true end
  return false
end

local previous_counter = nil
local captured = 0
while true do
  if movie.mode() ~= "PLAY" then
    return fail("movie_left_playback")
  end
  if movie.getreadonly() ~= true then
    return fail("movie_changed_readonly")
  end
  local counter = emu.framecount()
  if type(counter) ~= "number" or counter < 1 or counter % 1 ~= 0 then
    return fail("bad_emulator_counter")
  end
  if previous_counter ~= nil and counter ~= previous_counter + 1 then
    return fail("nonsequential_emulator_counter")
  end
  previous_counter = counter
  local index = counter - 1
  if index > FIRST_INDEX and captured == 0 then
    return fail("missed_anchor_begin")
  end
  if index >= FIRST_INDEX and index <= LAST_INDEX then
    if index ~= FIRST_INDEX + captured then
      return fail("unexpected_anchor_index")
    end
    local pressed = start_button(movie.getinput(index, 1))
    if pressed == nil then
      return fail("missing_or_ambiguous_start_input")
    end
    if index == FIRST_INDEX and pressed then
      return fail("expected_start_released_before_anchor")
    end
    if index == START_INDEX and not pressed then
      return fail("start_press_missing_at_frame_1661")
    end
    local filename = string.format("%s/vh_start_anchor_counter_%07d.png", root, counter)
    local exists = io.open(filename, "rb")
    if exists ~= nil then
      exists:close()
      return fail("capture_filename_already_exists")
    end
    -- Client display captures may include scaling, filters or OSD.
    -- Counter is logged at call time; displayed frame timing is NOT verified.
    client.screenshot(filename)
    local saved = io.open(filename, "rb")
    if saved == nil then
      return fail("screenshot_file_not_written")
    end
    local signature = saved:read(8)
    saved:close()
    if signature ~= PNG_SIGNATURE then
      return fail("screenshot_not_png")
    end
    print(string.format(
      "VH_PRIVATE_START_CAPTURE counter=%d candidate_input=%d start_pressed=%s mode=PLAY png=written",
      counter, index, pressed and "yes" or "no"))
    captured = captured + 1
    if captured == 3 then
      print("VH_PRIVATE_START_CAPTURE_COMPLETE snapshots=3 movie_input_anchor_1661=yes displayed_frame_offset=unverified")
      return
    end
  end
  emu.frameadvance()
end
