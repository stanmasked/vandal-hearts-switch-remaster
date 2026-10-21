-- BizHawk/Octoshock owner-private BK2 input handshake.
-- OWNER-LOCAL ONLY: console contents are private, never send to CI.
-- Run in movie PLAY from before frame 1650, with the correct original PSX image.
-- Read-only movie.getinput() access: this does not prove a rendered PS1 scene.
-- Frame indices are zero based; emu.framecount() is one based in this probe.
local START_INPUT = 1650
local END_INPUT = 1690
local BUTTONS = {
  "Up", "Down", "Left", "Right", "Select", "Start", "Square",
  "Triangle", "Circle", "Cross", "L1", "R1", "L2", "R2",
  "L3", "R3", "MODE"
}
local next_input = START_INPUT
while true do
  if movie.mode() == "PLAY" then
    local counter = emu.framecount()
    local candidate = counter - 1
    if candidate >= START_INPUT and candidate <= END_INPUT
       and candidate == next_input then
      local data = movie.getinput(candidate, 1)
      if type(data) ~= "table" then
        print("VH_PRIVATE_BK2_SYNC_ERROR movie_input_unavailable")
        return
      end
      local mask = 0
      for i, name in ipairs(BUTTONS) do
        if data[name] == true then
          mask = mask + 2 ^ (i - 1)
        end
      end
      print(string.format(
        "VH_PRIVATE_BK2_SYNC counter=%d candidate_input=%d mask=%d mode=PLAY",
        counter, candidate, mask))
      next_input = next_input + 1
      if next_input > END_INPUT then
        return
      end
    elseif candidate > next_input and next_input <= END_INPUT then
      print("VH_PRIVATE_BK2_SYNC_ERROR skipped_input_counter")
      return
    end
  end
  emu.frameadvance()
end
