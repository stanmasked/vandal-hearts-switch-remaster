-- OWNER LOCAL ONLY: capture candidate REVIEW frames, NOT verified MAP02.
-- Requires absolute VH_PRIVATE_CAPTURE_PLAN and VH_PRIVATE_PNG_DIR.
-- Original BK2, inputs and screenshots must NOT be uploaded to GitHub.
local HEADER = "VH_MAP02_CAPTURE_PLAN_V1"
local EXPECTED_LENGTH = 933949
local NAMES = {
  "Up", "Down", "Left", "Right", "Select", "Start", "Square",
  "Triangle", "Circle", "Cross", "L1", "R1", "L2", "R2", "L3", "R3", "MODE"
}
local log_handle = nil
local function emit(line)
  print(line)
  if log_handle then
    log_handle:write(line, "\n")
    log_handle:flush()
  end
end
local function fail(code)
  emit("VH_PRIVATE_NEUTRAL_CAPTURE_ERROR " .. code)
  if log_handle then log_handle:close(); log_handle = nil end
  -- Do not leave a failed capture running through the remaining long movie.
  -- The launcher will record the nonzero process exit; if the API is missing,
  -- the existing preflight error remains fail-closed and needs owner cleanup.
  if type(client) == "table" and type(client.exitCode) == "function" then
    pcall(client.exitCode, 1)
  end
  return
end
local function absolute_private_path(value)
  if type(value) ~= "string" or #value < 4 or #value > 250
     or value:find("..", 1, true) or value:find("[\r\n]") then return false end
  return value:sub(1, 1) == "/" or value:match("^[A-Za-z]:[\\/]") ~= nil
end
local function canonical_movie_path(value)
  if not absolute_private_path(value) then return nil end
  local path = value:gsub("\\", "/"):gsub("/+", "/")
  -- macOS aliases /var to /private/var. Both may name the same file,
  -- depending on whether BizHawk returns the provided or resolved path.
  if path:sub(1, 13) == "/private/var/" then
    path = path:sub(9)
  end
  if path:match("^[A-Za-z]:/") then
    path = path:lower()
  end
  return path
end
local expected_movie = os.getenv("VH_PRIVATE_EXPECTED_MOVIE")
local plan_file = os.getenv("VH_PRIVATE_CAPTURE_PLAN")
local root = os.getenv("VH_PRIVATE_PNG_DIR")
local log_path = os.getenv("VH_PRIVATE_CAPTURE_LOG")
if not absolute_private_path(plan_file) or not absolute_private_path(root)
    or not absolute_private_path(log_path)
    or not canonical_movie_path(expected_movie) then
  return fail("absolute_private_paths_required")
end
-- Best-effort Git checkout guard for environments without LuaFileSystem.
-- Stop BEFORE writing any owner-private screenshot to a public checkout.
-- A later Python auditor independently resolves paths and repeats this check.
local function capture_root_in_git_checkout(path)
  local location = path:gsub("\\", "/"):gsub("/+$", "")
  if location:find("/.git/", 1, true) or location:match("/%.git$") then
    return true
  end
  while location and #location >= 2 do
    local marker = io.open(location .. "/.git/HEAD", "rb")
    if marker then marker:close(); return true end
    -- Worktrees use a .git *file* instead of a .git directory.
    local pointer = io.open(location .. "/.git", "rb")
    if pointer then pointer:close(); return true end
    location = location:match("^(.*)/[^/]+$")
  end
  return false
end
if capture_root_in_git_checkout(root) then
  return fail("private_png_dir_inside_git_checkout")
end
if capture_root_in_git_checkout(log_path) then
  return fail("private_log_inside_git_checkout")
end
local normalized_root = root:gsub("\\", "/"):gsub("/+$", "")
local normalized_log = log_path:gsub("\\", "/"):gsub("/+$", "")
if normalized_log ~= normalized_root .. "/vh_private_capture.log" then
  return fail("private_log_must_be_inside_capture_root")
end
-- The Python launcher creates this file with exclusive mode 0600 before
-- starting EmuHawk. Refuse to silently create a less-private log from Lua.
local log_probe = io.open(log_path, "rb")
if not log_probe then return fail("private_log_not_precreated") end
log_probe:close()
log_handle = io.open(log_path, "ab")
if not log_handle then return fail("private_log_unavailable") end
emit("VH_PRIVATE_CAPTURE_LOG_READY schema=1")
local fp = io.open(plan_file, "rb")
if not fp then return fail("private_plan_unavailable") end
local body = fp:read(8193)
fp:close()
if not body or #body > 8192 or body:find("\r", 1, true) then
  return fail("private_plan_oversize_or_malformed")
end
local lines = {}
for line in body:gmatch("[^\n]+") do table.insert(lines, line) end
if lines[1] ~= HEADER or lines[2] ~= "movie_frames=" .. EXPECTED_LENGTH then
  return fail("private_plan_header_invalid")
end
local n = tonumber((lines[3] or ""):match("^capture_count=(%d+)$"))
if not n or n < 3 or n > 30 or n % 3 ~= 0 or #lines ~= n + 3 then
  return fail("private_plan_count_invalid")
end
local captures, groups, last_frame = {}, {}, -1
for i = 4, #lines do
  local g, role, ix, held = lines[i]:match("^(%d+),([a-z]+),(%d+),([a-z]+)$")
  g, ix = tonumber(g), tonumber(ix)
  if not g or not ix or g < 1 or g > n / 3
      or ix < 1663 or ix >= EXPECTED_LENGTH or ix <= last_frame
      or (role ~= "before" and role ~= "middle" and role ~= "after")
      or held ~= ((role == "middle") and "neutral" or "held") then
    return fail("private_plan_row_invalid")
  end
  last_frame = ix
  groups[g] = groups[g] or {}
  if groups[g][role] then return fail("duplicate_group_role") end
  groups[g][role] = ix
  table.insert(captures, {index=ix, group=g, role=role, held=held})
end
for g = 1, n / 3 do
  local p = groups[g]
  if not p or not p.before or not p.middle or not p.after
      or not (p.before < p.middle and p.middle < p.after) then
    return fail("incomplete_group_order")
  end
end
-- Distinguish an actual PlayStation system from unrelated movies whose
-- frame counts happen to match. This does not attest which PSX *core* is
-- running; the owner must still verify Octoshock in EmuHawk.
if type(emu.getsystemid) ~= "function" or emu.getsystemid() ~= "PSX" then
  return fail("wrong_or_unknown_emulated_system")
end
if movie.length() ~= EXPECTED_LENGTH or movie.getreadonly() ~= true then
  return fail("wrong_movie_length_or_readonly")
end
-- Movie metadata alone can be correct while EmuHawk has selected a
-- pre-existing GUI instance and opened a *different* BK2. Reject it.
if type(movie.filename) ~= "function"
    or canonical_movie_path(movie.filename()) ~= canonical_movie_path(expected_movie) then
  return fail("loaded_movie_path_does_not_match_private_source")
end
-- True replay from PS1 power-on must not silently start at a savestate or
-- SaveRAM image; such a run cannot support the cold-start claim.
if type(movie.startsfromsavestate) ~= "function"
    or type(movie.startsfromsaveram) ~= "function"
    or movie.startsfromsavestate() ~= false
    or movie.startsfromsaveram() ~= false then
  return fail("movie_not_poweron_anchored")
end
emit("VH_PRIVATE_NEUTRAL_MOVIE_SOURCE_PREFLIGHT source=poweron filename=matched core_identity=unverified")
-- The owner-local launcher needs EmuHawk to exit as soon as the bounded
-- captures finish, rather than playing the rest of this long BK2 movie.
if type(client) ~= "table" or type(client.exitCode) ~= "function" then
  return fail("emuhawk_exit_code_api_unavailable")
end
-- Fail closed on a late Lua attachment, manual seek, or a savestate loaded
-- after startup. This still cannot prove an authentic PS1 power-on.
local first_counter = emu.framecount()
if type(first_counter) ~= "number" or
    (first_counter ~= 0 and first_counter ~= 1) then
  return fail("lua_must_attach_at_movie_start")
end

-- The original movie must not be replaced by a savestate at any point
-- after this capture script attaches. Counter continuity is insufficient:
-- loading a state could restore a matching counter while changing the core.
if type(event) ~= "table" or type(event.onloadstate) ~= "function" then
  return fail("savestate_event_api_unavailable")
end
local state_loaded = false
local state_listener = event.onloadstate(function()
  state_loaded = true
end, "vh_map02_block_runtime_state_load")
if type(state_listener) ~= "string" or state_listener == "" then
  return fail("savestate_event_registration_failed")
end
-- Input-poll callbacks offer supplementary evidence that the running core
-- requested controller data. They do NOT show which inputs were delivered.
-- Some BizHawk builds/cores do not expose this callback, so unavailability
-- is recorded honestly rather than promoted to proof or an automatic error.
local input_polled = false
if type(event.oninputpoll) == "function" then
  local poll_listener = event.oninputpoll(function()
    input_polled = true
  end, "vh_map02_observe_input_poll")
  if type(poll_listener) ~= "string" or poll_listener == "" then
    return fail("input_poll_event_registration_failed")
  end
end

local function start_state(data)
  if type(data) ~= "table" then return nil end
  local plain, prefixed = data["Start"], data["P1 Start"]
  if plain ~= nil and type(plain) ~= "boolean" then return nil end
  if prefixed ~= nil and type(prefixed) ~= "boolean" then return nil end
  if plain ~= nil and prefixed ~= nil and plain ~= prefixed then return nil end
  if plain == true or prefixed == true then return true end
  if plain == false or prefixed == false then return false end
  -- BizHawk may return a sparse table containing pressed buttons only.
  -- Missing Start therefore means "not pressed" (not an error). The
  -- following frame still MUST contain an explicit Start=true.
  return false
end

local function any_held(data)
  if type(data) ~= "table" then return nil end
  local held = false
  for _, name in ipairs(NAMES) do
    local plain, prefixed = data[name], data["P1 " .. name]
    if plain ~= nil and type(plain) ~= "boolean" then return nil end
    if prefixed ~= nil and type(prefixed) ~= "boolean" then return nil end
    if plain ~= nil and prefixed ~= nil and plain ~= prefixed then return nil end
    if plain == true or prefixed == true then held = true end
  end
  return held
end

local current, previous_counter = 1, nil
local first_start_off_seen, first_start_on_seen = false, false
while true do
  if state_loaded then return fail("savestate_loaded_during_replay") end
  if type(emu.getsystemid) ~= "function" or emu.getsystemid() ~= "PSX" then
    return fail("emulated_system_changed")
  end
  if movie.mode() ~= "PLAY" or movie.getreadonly() ~= true then
    return fail("movie_playback_left_readonly")
  end
  local counter = emu.framecount()
  if type(counter) ~= "number" or counter % 1 ~= 0 or counter < 0 then
    return fail("bad_emulator_counter")
  end
  if previous_counter ~= nil and counter ~= previous_counter + 1 then
    return fail("emulator_counter_jump")
  end
  previous_counter = counter
  local index = counter - 1 -- still only a provisional input-to-display convention
  -- The previously inspected owner's BK2 has its first Start press at zero-
  -- based movie input 1661. Observe that known edge during THIS uninterrupted
  -- replay before accepting any later plan candidate. movie.getinput is still
  -- recorded movie data, not independently observed PS1 controller delivery.
  if index == 1660 then
    local pressed = start_state(movie.getinput(index, 1))
    if pressed == nil or pressed then
      return fail("start_anchor_before_missing_or_pressed")
    end
    first_start_off_seen = true
  elseif index == 1661 then
    if not first_start_off_seen or start_state(movie.getinput(index, 1)) ~= true then
      return fail("start_anchor_press_missing_or_ambiguous")
    end
    first_start_on_seen = true
    emit("VH_PRIVATE_NEUTRAL_START_PREFLIGHT counter=1662 candidate_input=1661 first_start_pressed=yes ps1_input_delivery=unverified")
  elseif index > 1661 and not first_start_on_seen then
    return fail("start_anchor_was_not_observed_live")
  end
  local wanted = captures[current]
  if index > wanted.index then return fail("scheduled_frame_missed") end
  if index == wanted.index then
    local state = any_held(movie.getinput(index, 1))
    if state == nil or state ~= (wanted.held == "held") then
      return fail("movie_getinput_neutral_state_mismatch")
    end
    local name = string.format(
      "vh_review_w%02d_%s_counter_%07d.png", wanted.group, wanted.role, counter)
    local path = root .. "/" .. name
    local exists = io.open(path, "rb")
    if exists then exists:close(); return fail("refuse_overwrite_screenshot") end
    client.screenshot(path)
    local saved = io.open(path, "rb")
    if not saved then return fail("screenshot_not_written") end
    local sig = saved:read(8)
    saved:close()
    if sig ~= "\137PNG\r\n\26\n" then return fail("screenshot_not_png") end
    emit(string.format(
      "VH_PRIVATE_NEUTRAL_CAPTURE window=%d role=%s counter=%d candidate_input=%d expected_buttons=%s png=written display_offset=unverified",
      wanted.group, wanted.role, counter, index, wanted.held))
    current = current + 1
    if current > #captures then
      emit(string.format(
        "VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=%d movie_input_only=yes core_input_poll_observed=%s actual_map02=unverified",
        #captures, input_polled and "yes" or "no"))
      if log_handle then log_handle:close(); log_handle = nil end
      -- Close the emulator with an explicit successful process status.
      -- Python then appends the process-exit marker required by the auditor.
      client.exitCode(0)
      return
    end
  end
  emu.frameadvance()
end
