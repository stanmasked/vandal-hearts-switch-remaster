-- Executable Lua capture test with entirely invented BizHawk APIs and PNG bytes.
-- Does NOT run Octoshock, use the owner's BK2 or publish original gameplay.
local SCRIPT = "tools/map02_bizhawk_private_neutral_capture.lua"
local old_print, old_getenv, old_open = print, os.getenv, io.open
local ROOT = "/private/fake-local-images"
local PLAN = "/private/fake-capture-plan.txt"
local LOG = ROOT .. "/vh_private_capture.log"
local SIGNATURE = "\137PNG\r\n\26\n"
local BASE = "VH_MAP02_CAPTURE_PLAN_V1\nmovie_frames=933949\ncapture_count=3\n" ..
             "1,before,1664,held\n1,middle,1666,neutral\n1,after,1669,held\n"
local scenarios = 0

local function run(option)
  scenarios = scenarios + 1
  local counter = option == "late-attach" and 80 or (option == "zero-counter" and 0 or 1)
  local lines, screenshots, saved, log_lines, exit_codes = {}, {}, {}, {}, {}
  local callbacks = {}
  local content = BASE
  if option == "boundary" then content = content:gsub("1,before,1664,held", "1,before,1663,held") end
  if option == "bad-header" then content = content:gsub("VH_MAP02_CAPTURE_PLAN_V1", "OTHER") end
  if option == "bad-count" then content = content:gsub("capture_count=3", "capture_count=4") end
  if option == "duplicate-index" then content = content:gsub("1,middle,1666", "1,middle,1664") end
  if option == "invalid-role" then content = content:gsub("1,middle,1666", "1,before,1666") end
  os.getenv = function(name)
    if name == "VH_PRIVATE_EXPECTED_MOVIE" then
      if option == "relative-movie" then return "not-absolute.bk2" end
      if option == "mac-alias" then return "/var/private-movie.bk2" end
      return "/private/private-movie.bk2"
    end
    if name == "VH_PRIVATE_CAPTURE_PLAN" then
      return option == "relative-plan" and "fake-plan.txt" or PLAN
    end
    if name == "VH_PRIVATE_PNG_DIR" then
      return option == "relative-root" and "fake-images" or ROOT
    end
    if name == "VH_PRIVATE_CAPTURE_LOG" then
      if option == "relative-log" then return "capture.log" end
      if option == "outside-log" then return "/private/outside.log" end
      return LOG
    end
    error("unexpected environment variable")
  end
  io.open = function(path, mode)
    if path == LOG and mode == "ab" then
      return {
        write = function(_, line, newline)
          assert(newline == "\n", "private log records must be newline-delimited")
          table.insert(log_lines, tostring(line))
          return true
        end,
        flush = function() end,
        close = function() end,
      }
    end
    assert(mode == "rb", "only the private capture log may be opened for append")
    if path == LOG then
      if option == "missing-log" then return nil end
      return { close = function() end }
    end
    -- Simulate three public Git roots: inside the output root, an ancestor,
    -- and a worktree-style .git pointer file.
    local mark =
      (option == "git-root" and path == ROOT .. "/.git/HEAD") or
      (option == "git-parent" and path == "/private/.git/HEAD") or
      (option == "git-worktree" and path == "/private/.git")
    if mark then
      return { close = function() end }
    end
    if path == PLAN then
      return {
        read = function(_, size) assert(size == 8193); return content end,
        close = function() end,
      }
    end
    local bytes = saved[path]
    if option == "saved-exists" and path:find("before", 1, true) then
      bytes = SIGNATURE
    end
    if bytes == nil then return nil end
    return {
      read = function(_, size) assert(size == 8); return bytes:sub(1, size) end,
      close = function() end,
    }
  end
  movie = {
    filename = function()
      if option == "wrong-movie" then return "/private/some-other.bk2" end
      if option == "mac-alias" then return "/private/var/private-movie.bk2" end
      return "/private/private-movie.bk2"
    end,
    startsfromsavestate = function() return option == "savestate-movie" end,
    startsfromsaveram = function() return option == "saveram-movie" end,
    length = function()
      return option == "wrong-length" and 500 or 933949
    end,
    getreadonly = function()
      return option ~= "not-readonly"
    end,
    mode = function()
      if option == "mode-leaves" and counter >= 1666 then return "RECORD" end
      return "PLAY"
    end,
    getinput = function(idx, port)
      assert(port == 1)
      assert(idx == 1660 or idx == 1661 or idx == 1663 or
             idx == 1664 or idx == 1666 or idx == 1669)
      if idx == 1660 or idx == 1661 then
        if option == "sparse-start" and idx == 1660 then return {} end
        if option == "nil-start-table" and idx == 1660 then return nil end
        local pressed = idx == 1661
        if option == "early-start" and idx == 1660 then pressed = true end
        if option == "missing-start" and idx == 1661 then pressed = false end
        if option == "ambiguous-start" and idx == 1661 then
          return {Start = true, ["P1 Start"] = false}
        end
        if option == "unknown-start" and idx == 1661 then
          return {["P2 Start"] = true}
        end
        local start_key = option == "prefixed" and "P1 Start" or "Start"
        return {[start_key] = pressed}
      end
      local pressed = (idx ~= 1666)
      if option == "neutral-mismatch" then pressed = not pressed end
      local key = option == "prefixed" and "P1 Up" or "Up"
      return {[key] = pressed}
    end,
  }
  if option == "missing-filename-api" then movie.filename = nil end
  if option == "missing-savestate-api" then movie.startsfromsavestate = nil end
  if option == "missing-saveram-api" then movie.startsfromsaveram = nil end
  event = {
    onloadstate = function(callback, name)
      assert(name == "vh_map02_block_runtime_state_load")
      callbacks.state = callback
      return option == "state-hook-refused" and "" or "fictional-state-hook"
    end,
    oninputpoll = function(callback, name)
      assert(name == "vh_map02_observe_input_poll")
      callbacks.poll = callback
      return option == "poll-hook-refused" and "" or "fictional-poll-hook"
    end,
  }
  if option == "missing-state-event" then event.onloadstate = nil end
  if option == "missing-input-event" then event.oninputpoll = nil end
  if option == "missing-event-table" then event = nil end
  emu = {
    getsystemid = function()
      if option == "wrong-system" then return "NES" end
      if option == "system-changed" and counter >= 1664 then return "N64" end
      return "PSX"
    end,
    framecount = function() return counter end,
    getdisplaytype = function()
      if option == "unknown-display" then return "UNKNOWN" end
      if option == "display-changes" and counter >= 1665 then return "PAL" end
      if option == "pal-display" then return "PAL" end
      return "NTSC"
    end,
    frameadvance = function()
      assert(counter < 1700, "capture observer should terminate")
      if callbacks.poll and option ~= "no-input-polls" then callbacks.poll() end
      if callbacks.state and
          ((option == "state-loaded-before-first" and counter == 1663) or
           (option == "state-loaded-after-first" and counter == 1665)) then
        callbacks.state("fictional-savestate")
      end
      if option == "skip-counter" and counter == 1663 then
        counter = counter + 2
      else
        counter = counter + 1
      end
    end,
  }
  if option == "missing-system-api" then emu.getsystemid = nil end
  client = {
    getversion = function()
      if option == "bad-version" then return "2.11\nPRIVATE_PATH" end
      return "2.11"
    end,
    screenshot = function(path)
      assert(path:sub(1, #ROOT) == ROOT and path:match("%.png$"),
             "screenshot not confined to intended fake root")
      table.insert(screenshots, path)
      if option ~= "missing-write" then
        saved[path] = option == "malformed-png" and "badbytes" or SIGNATURE
      end
    end,
    exitCode = function(code) table.insert(exit_codes, code) end,
  }
  if option == "missing-exit-api" then client.exitCode = nil end
  if option == "missing-version-api" then client.getversion = nil end
  if option == "missing-display-api" then emu.getdisplaytype = nil end
  print = function(line) table.insert(lines, tostring(line)) end
  local ok, err = pcall(dofile, SCRIPT)
  print, os.getenv, io.open = old_print, old_getenv, old_open
  assert(ok, tostring(err))
  return lines, screenshots, log_lines, exit_codes
end

for _, option in ipairs({"plain", "prefixed", "boundary", "zero-counter", "sparse-start", "mac-alias", "pal-display"}) do
  local lines, shots, log_lines, exit_codes = run(option)
  assert(#shots == 3, option .. ": expected three screenshot calls")
  assert(#lines == 8, option .. ": log ready, source, runtime, Start anchor, three captures and summary")
  assert(#log_lines == #lines, option .. ": private file log must mirror console markers")
  for i = 1, #lines do
    assert(log_lines[i] == lines[i], option .. ": private log differs from console marker")
  end
  assert(lines[1] == "VH_PRIVATE_CAPTURE_LOG_READY schema=1", option .. ": missing log-ready marker")
  assert(lines[2] == "VH_PRIVATE_NEUTRAL_MOVIE_SOURCE_PREFLIGHT source=poweron filename=matched core_identity=unverified", option .. ": wrong power-on source")
  local display = option == "pal-display" and "PAL" or "NTSC"
  assert(lines[3] == "VH_PRIVATE_NEUTRAL_RUNTIME_PREFLIGHT bizhawk_version=2.11 display=" .. display .. " active_core=unverified", option .. ": wrong runtime")
  assert(lines[4] == "VH_PRIVATE_NEUTRAL_START_PREFLIGHT counter=1662 candidate_input=1661 first_start_pressed=yes ps1_input_delivery=unverified", option .. ": wrong live anchor")
  local frames = {option == "boundary" and 1663 or 1664, 1666, 1669}
  local roles = {"before", "middle", "after"}
  for i = 1, 3 do
    local group, role, counter, candidate, held = lines[i + 4]:match(
      "^VH_PRIVATE_NEUTRAL_CAPTURE window=(%d+) role=([a-z]+) counter=(%d+) candidate_input=(%d+) expected_buttons=([a-z]+) png=written display_offset=unverified$")
    assert(tonumber(group) == 1 and role == roles[i], option .. ": bad role/group")
    assert(tonumber(counter) == frames[i] + 1, option .. ": bad core counter")
    assert(tonumber(candidate) == frames[i], option .. ": off-by-one movie frame")
    assert(held == (i == 2 and "neutral" or "held"), option .. ": expected button state")
  end
  assert(lines[8] == "VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=3 movie_input_only=yes core_input_poll_observed=yes actual_map02=unverified")
  assert(#exit_codes == 1 and exit_codes[1] == 0,
         option .. ": successful bounded capture must close EmuHawk with exit code 0")
end

for _, option in ipairs({
  "relative-plan", "relative-root", "relative-log", "outside-log", "missing-log", "wrong-length", "not-readonly",
  "bad-header", "bad-count", "duplicate-index", "neutral-mismatch",
  "mode-leaves", "skip-counter", "saved-exists", "missing-write",
  "malformed-png", "invalid-role", "late-attach",
  "early-start", "missing-start", "ambiguous-start", "unknown-start",
  "nil-start-table", "git-root", "git-parent", "git-worktree",
  "wrong-system", "system-changed", "missing-system-api", "missing-exit-api",
  "wrong-movie", "relative-movie", "savestate-movie", "saveram-movie",
  "missing-filename-api", "missing-savestate-api", "missing-saveram-api",
  "missing-event-table", "missing-state-event", "state-hook-refused",
  "poll-hook-refused", "state-loaded-before-first", "state-loaded-after-first",
  "bad-version", "missing-version-api", "missing-display-api",
  "unknown-display", "display-changes"
}) do
  local lines, shots, _, exit_codes = run(option)
  local rejected = false
  for _, line in ipairs(lines) do
    if line:match("^VH_PRIVATE_NEUTRAL_CAPTURE_ERROR ") then rejected = true end
    assert(not line:match("^VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE"),
           option .. ": unsafe false-success")
  end
  assert(rejected, option .. ": fail-closed diagnostic missing")
  assert(#shots < 3, option .. ": should reject before three successful PNGs")
  if option == "missing-exit-api" then
    assert(#exit_codes == 0, option .. ": unavailable exit API must not be called")
  else
    assert(#exit_codes == 1 and exit_codes[1] == 1,
           option .. ": failed capture must terminate EmuHawk with exit code 1")
  end
end
do
  local lines, shots, _, exit_codes = run("no-input-polls")
  assert(#shots == 3 and #exit_codes == 1 and exit_codes[1] == 0)
  assert(lines[8] == "VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=3 movie_input_only=yes core_input_poll_observed=no actual_map02=unverified")
end
do
  local lines, shots, _, exit_codes = run("missing-input-event")
  assert(#shots == 3 and #exit_codes == 1 and exit_codes[1] == 0)
  assert(lines[8] == "VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=3 movie_input_only=yes core_input_poll_observed=no actual_map02=unverified")
end
old_print("VH_MAP02_NEUTRAL_CAPTURE_LUA_MOCK_PASS cases=" .. scenarios ..
          " owner_bk2=0 actual_bizhawk=0 map02_verified=0")
