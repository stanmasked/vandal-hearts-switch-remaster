-- Executable Lua capture test with entirely invented BizHawk APIs and PNG bytes.
-- Does NOT run Octoshock, use the owner's BK2 or publish original gameplay.
local SCRIPT = "tools/map02_bizhawk_private_neutral_capture.lua"
local old_print, old_getenv, old_open = print, os.getenv, io.open
local ROOT = "/private/fake-local-images"
local PLAN = "/private/fake-capture-plan.txt"
local SIGNATURE = "\137PNG\r\n\26\n"
local BASE = "VH_MAP02_CAPTURE_PLAN_V1\nmovie_frames=933949\ncapture_count=3\n" ..
             "1,before,1664,held\n1,middle,1666,neutral\n1,after,1669,held\n"
local scenarios = 0

local function run(option)
  scenarios = scenarios + 1
  local counter = 1
  local lines, screenshots, saved = {}, {}, {}
  local content = BASE
  if option == "bad-header" then content = content:gsub("VH_MAP02_CAPTURE_PLAN_V1", "OTHER") end
  if option == "bad-count" then content = content:gsub("capture_count=3", "capture_count=4") end
  if option == "duplicate-index" then content = content:gsub("1,middle,1666", "1,middle,1664") end
  if option == "invalid-role" then content = content:gsub("1,middle,1666", "1,before,1666") end
  os.getenv = function(name)
    if name == "VH_PRIVATE_CAPTURE_PLAN" then
      return option == "relative-plan" and "fake-plan.txt" or PLAN
    end
    if name == "VH_PRIVATE_PNG_DIR" then
      return option == "relative-root" and "fake-images" or ROOT
    end
    error("unexpected environment variable")
  end
  io.open = function(path, mode)
    assert(mode == "rb", "capture script must not write through Lua io")
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
      assert(idx == 1664 or idx == 1666 or idx == 1669)
      local pressed = (idx ~= 1666)
      if option == "neutral-mismatch" then pressed = not pressed end
      local key = option == "prefixed" and "P1 Up" or "Up"
      return {[key] = pressed}
    end,
  }
  emu = {
    framecount = function() return counter end,
    frameadvance = function()
      assert(counter < 1700, "capture observer should terminate")
      if option == "skip-counter" and counter == 1663 then
        counter = counter + 2
      else
        counter = counter + 1
      end
    end,
  }
  client = {
    screenshot = function(path)
      assert(path:sub(1, #ROOT) == ROOT and path:match("%.png$"),
             "screenshot not confined to intended fake root")
      table.insert(screenshots, path)
      if option ~= "missing-write" then
        saved[path] = option == "malformed-png" and "badbytes" or SIGNATURE
      end
    end,
  }
  print = function(line) table.insert(lines, tostring(line)) end
  local ok, err = pcall(dofile, SCRIPT)
  print, os.getenv, io.open = old_print, old_getenv, old_open
  assert(ok, tostring(err))
  return lines, screenshots
end

for _, option in ipairs({"plain", "prefixed"}) do
  local lines, shots = run(option)
  assert(#shots == 3, option .. ": expected three screenshot calls")
  assert(#lines == 4, option .. ": three capture lines and summary")
  local frames = {1664, 1666, 1669}
  local roles = {"before", "middle", "after"}
  for i = 1, 3 do
    local group, role, counter, candidate, held = lines[i]:match(
      "^VH_PRIVATE_NEUTRAL_CAPTURE window=(%d+) role=([a-z]+) counter=(%d+) candidate_input=(%d+) expected_buttons=([a-z]+) png=written display_offset=unverified$")
    assert(tonumber(group) == 1 and role == roles[i], option .. ": bad role/group")
    assert(tonumber(counter) == frames[i] + 1, option .. ": bad core counter")
    assert(tonumber(candidate) == frames[i], option .. ": off-by-one movie frame")
    assert(held == (i == 2 and "neutral" or "held"), option .. ": expected button state")
  end
  assert(lines[4] == "VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE snapshots=3 movie_input_only=yes actual_map02=unverified")
end

for _, option in ipairs({
  "relative-plan", "relative-root", "wrong-length", "not-readonly",
  "bad-header", "bad-count", "duplicate-index", "neutral-mismatch",
  "mode-leaves", "skip-counter", "saved-exists", "missing-write",
  "malformed-png", "invalid-role"
}) do
  local lines, shots = run(option)
  local rejected = false
  for _, line in ipairs(lines) do
    if line:match("^VH_PRIVATE_NEUTRAL_CAPTURE_ERROR ") then rejected = true end
    assert(not line:match("^VH_PRIVATE_NEUTRAL_CAPTURE_COMPLETE"),
           option .. ": unsafe false-success")
  end
  assert(rejected, option .. ": fail-closed diagnostic missing")
  assert(#shots < 3, option .. ": should reject before three successful PNGs")
end
old_print("VH_MAP02_NEUTRAL_CAPTURE_LUA_MOCK_PASS cases=" .. scenarios ..
          " owner_bk2=0 actual_bizhawk=0 map02_verified=0")
