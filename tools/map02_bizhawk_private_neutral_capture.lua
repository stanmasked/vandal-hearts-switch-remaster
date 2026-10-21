-- OWNER LOCAL ONLY: capture candidate REVIEW frames, NOT verified MAP02.
-- Requires absolute VH_PRIVATE_CAPTURE_PLAN and VH_PRIVATE_PNG_DIR.
-- Original BK2, inputs and screenshots must NOT be uploaded to GitHub.
local HEADER = "VH_MAP02_CAPTURE_PLAN_V1"
local EXPECTED_LENGTH = 933949
local NAMES = {
  "Up", "Down", "Left", "Right", "Select", "Start", "Square",
  "Triangle", "Circle", "Cross", "L1", "R1", "L2", "R2", "L3", "R3", "MODE"
}
local function fail(code)
  print("VH_PRIVATE_NEUTRAL_CAPTURE_ERROR " .. code)
  return
end
local function absolute_private_path(value)
  if type(value) ~= "string" or #value < 4 or #value > 250
     or value:find("..", 1, true) or value:find("[\r\n]") then return false end
  return value:sub(1, 1) == "/" or value:match("^[A-Za-z]:[\\/]") ~= nil
end
local plan_file = os.getenv("VH_PRIVATE_CAPTURE_PLAN")
local root = os.getenv("VH_PRIVATE_PNG_DIR")
if not absolute_private_path(plan_file) or not absolute_private_path(root) then
  return fail("absolute_private_paths_required")
end
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
if movie.length() ~= EXPECTED_LENGTH or movie.getreadonly() ~= true then
  return fail("wrong_movie_length_or_readonly")
end
-- Fail closed on a late Lua attachment, manual seek, or a savestate loaded
-- after startup. This still cannot prove an authentic PS1 power-on.
local first_counter = emu.framecount()
if type(first_counter) ~= "number" or
    (first_counter ~= 0 and first_counter ~= 1) then
  return fail("lua_must_attach_at_movie_start")
end

local function start_state(data)
  if type(data) ~= "table" then return nil end
  local plain, prefixed = data["Start"], data["P1 Start"]
  if plain ~= nil and type(plain) ~= "boolean" then return nil end
  if prefixed ~= nil and type(prefixed) ~= "boolean" then return nil end
  if plain ~= nil and prefixed ~= nil and plain ~= prefixed then return nil end
  if plain == true or prefixed == true then return true end
  if plain == false or prefixed == false then return false end
  return nil
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
    print("VH_PRIVATE_NEUTRAL_START_PREFLIGHT counter=1662 candidate_input=1661 first_start_pressed=yes ps1_input_delivery=unverified")
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
    print(string.format(
      "VH_PRIVATE_NEUTRAL_CAPTURE window=%d role=%s counter=%d candidate_input=%d expected_buttons=%s png=written display_offset=unverified",
      wanted.group, wanted.role, counter, index, wanted.held))
    current = current + 1
    if current > #captures then
      print(string.format(
        "VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=%d movie_input_only=yes actual_map02=unverified", #captures))
      return
    end
  end
  emu.frameadvance()
end
