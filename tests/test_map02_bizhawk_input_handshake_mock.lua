-- Synthetic executable mock of the BizHawk movie.getinput Lua contract.
-- Does NOT invoke BizHawk, PS1 game code, BIOS or original user movie.
local script = "tools/map02_bizhawk_private_input_handshake.lua"
local original_print = print
local cases = 0

local function expected_mask(frame)
  if frame == 1661 then return 32 end   -- Start, index 6
  if frame == 1670 then return 256 end  -- Circle, index 9
  if frame == 1680 then return 1 end    -- Up, index 1
  return 0
end

local function run(option)
  cases = cases + 1
  local counter = 1650
  local lines = {}
  local reads = 0
  movie = {
    mode = function()
      if option == "mode-changed" and counter >= 1665 then return "REC" end
      return "PLAY"
    end,
    getinput = function(index, controller)
      assert(controller == 1, "movie.getinput controller should be 1")
      assert(index >= 1650 and index <= 1690, "out-of-window input access")
      reads = reads + 1
      if option == "nil-input" and index == 1661 then return nil end
      if option == "ambiguous-name" and index == 1661 then
        return { Start = true, ["P1 Start"] = false }
      end
      local prefix = option == "prefixed-name" and "P1 " or ""
      local result = {}
      if index == 1661 then result[prefix .. "Start"] = true end
      if index == 1670 then result[prefix .. "Circle"] = true end
      if index == 1680 then result[prefix .. "Up"] = true end
      return result
    end
  }
  emu = {
    framecount = function() return counter end,
    frameadvance = function()
      if counter > 1700 then error("missing termination in read-only probe") end
      if option == "skip-counter" and counter == 1665 then
        counter = counter + 2
      else
        counter = counter + 1
      end
    end
  }
  print = function(line)
    table.insert(lines, tostring(line))
  end
  local ok, err = pcall(dofile, script)
  print = original_print
  assert(ok, tostring(err))
  return lines, reads
end

for _, option in ipairs({ "plain-name", "prefixed-name" }) do
  local lines, reads = run(option)
  assert(#lines == 41, option .. ": must report exactly 41 complete frames")
  assert(reads == 41, option .. ": must read exactly 41 movie input states")
  for i, line in ipairs(lines) do
    local counter, index, mask = line:match(
      "^VH_PRIVATE_BK2_SYNC counter=(%d+) candidate_input=(%d+) mask=(%d+) mode=PLAY$")
    assert(counter ~= nil, option .. ": malformed Lua log format")
    assert(tonumber(counter) == 1650 + i, option .. ": wrong emu frame counter")
    assert(tonumber(index) == 1649 + i, option .. ": wrong zero-based candidate")
    assert(tonumber(mask) == expected_mask(tonumber(index)),
           option .. ": wrong controller bitmask on frame " .. index)
  end
end

for _, option in ipairs({ "nil-input", "ambiguous-name",
                           "mode-changed", "skip-counter" }) do
  local lines = run(option)
  assert(#lines < 41, option .. ": must fail before complete window")
  local failure_found = false
  for _, line in ipairs(lines) do
    if line:match("^VH_PRIVATE_BK2_SYNC_ERROR ") then failure_found = true end
  end
  assert(failure_found, option .. ": missing explicit fail-closed diagnostic")
end

original_print("VH_MAP02_LUA_MOCK_PASS cases=" .. cases ..
               " original_movie=0 bizhawk_emulator=0 map02_verified=0")
