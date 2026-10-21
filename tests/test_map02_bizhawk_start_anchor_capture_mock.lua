-- Run the actual private screenshot script using invented movie and client APIs.
-- 12 scenarios; NEVER loads BizHawk, private BK2, PS1 disc/BIOS, or screenshots.
local SCRIPT = "tools/map02_bizhawk_private_start_anchor_capture.lua"
local old_print, old_getenv, old_open = print, os.getenv, io.open
local PNG = "\137PNG\r\n\26\n"
local DIR = "/private/mock-vh-anchor"
local scenarios = 0

local function run(option)
  scenarios = scenarios + 1
  local counter = 1
  local lines, files, shots = {}, {}, {}
  local function start_pressed(index)
    if option == "early-start" then return index == 1660 end
    if option == "missing-start" then return false end
    return index == 1661
  end
  os.getenv = function(key)
    assert(key == "VH_PRIVATE_PNG_DIR")
    if option == "relative-dir" then return "relative/mock" end
    return DIR
  end
  io.open = function(path, mode)
    assert(mode == "rb", "screenshot test must never write via Lua IO")
    local data = files[path]
    if option == "existing-file" and path:match("_0001661%.png$") then
      data = PNG
    end
    if data == nil then return nil end
    return {
      read = function(_, n) assert(n == 8); return data:sub(1, 8) end,
      close = function() end,
    }
  end
  movie = {
    length = function() if option == "wrong-length" then return 10 end return 933949 end,
    getreadonly = function() return option ~= "not-readonly" end,
    mode = function()
      if option == "mode-changed" and counter >= 1662 then return "RECORD" end
      return "PLAY"
    end,
    getinput = function(index, controller)
      assert(controller == 1)
      assert(index >= 1660 and index <= 1662)
      if option == "nil-input" then return nil end
      if option == "ambiguous" and index == 1661 then
        return {Start = true, ["P1 Start"] = false}
      end
      local key = option == "prefixed" and "P1 Start" or "Start"
      return {[key] = start_pressed(index)}
    end,
  }
  emu = {
    framecount = function() return counter end,
    frameadvance = function()
      assert(counter < 1700, "observer failed to terminate")
      if option == "skip-counter" and counter == 1660 then
        counter = counter + 2
      else counter = counter + 1 end
    end,
  }
  client = {
    screenshot = function(path)
      assert(path:sub(1, #DIR) == DIR, "screenshot would leave private root")
      assert(path:find("%.png$"), "screenshot is not a PNG filename")
      table.insert(shots, path)
      if option ~= "missing-file" then
        files[path] = option == "bad-png" and "notPNG!!" or PNG
      end
    end,
  }
  print = function(line) table.insert(lines, tostring(line)) end
  local ok, err = pcall(dofile, SCRIPT)
  print, os.getenv, io.open = old_print, old_getenv, old_open
  assert(ok, tostring(err))
  return lines, shots
end

for _, option in ipairs({"plain", "prefixed"}) do
  local lines, shots = run(option)
  assert(#shots == 3, option .. ": three captures required")
  assert(#lines == 4, option .. ": three records plus completed line required")
  for i = 1, 3 do
    local counter, input, pressed = lines[i]:match(
      "^VH_PRIVATE_START_CAPTURE counter=(%d+) candidate_input=(%d+) start_pressed=(%a+) mode=PLAY png=written$")
    assert(tonumber(counter) == 1660 + i, option .. ": wrong counter")
    assert(tonumber(input) == 1659 + i, option .. ": wrong input index")
    assert(pressed == (i == 2 and "yes" or "no"), option .. ": wrong Start state")
    assert(shots[i] == string.format("%s/vh_start_anchor_counter_%07d.png", DIR, 1660 + i))
  end
  assert(lines[4]:find("displayed_frame_offset=unverified", 1, true))
end

for _, option in ipairs({
  "relative-dir", "wrong-length", "not-readonly", "early-start",
  "missing-start", "ambiguous", "nil-input", "skip-counter",
  "mode-changed", "existing-file", "bad-png", "missing-file",
}) do
  local lines, shots = run(option)
  assert(#lines >= 1, option .. ": missing fail-closed diagnostics")
  local error_found = false
  for _, line in ipairs(lines) do
    if line:match("^VH_PRIVATE_START_CAPTURE_ERROR ") then error_found = true end
    assert(not line:match("^VH_PRIVATE_START_CAPTURE_COMPLETE"), option .. ": unsafe success")
  end
  assert(error_found, option .. ": missing explicit failure")
  assert(#shots <= 2, option .. ": must abort incomplete captures")
end

old_print("VH_MAP02_START_ANCHOR_LUA_MOCK_PASS cases=" .. scenarios ..
          " original_movie=0 real_bizhawk=0 captured_owner_images=0 map02_verified=0")
