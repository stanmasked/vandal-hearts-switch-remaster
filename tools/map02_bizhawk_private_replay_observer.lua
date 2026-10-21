-- Owner-local BizHawk/Octoshock movie observer. NEVER log raw game data.
-- Use on a PSX/Octoshock replay of the owner's private BK2 only.
-- Press J (not mapped to the gamepad) while visually inspecting a frame.
-- This reports a candidate input offset, NOT a confirmed MAP02 boundary.
local last_pressed = false
while true do
  local state = input.get()
  local pressed = (state["J"] == true)
  if pressed and not last_pressed and movie.mode() == "PLAY" then
    local counter = emu.framecount()
    if counter > 0 then
      print(string.format(
        "VH_PRIVATE_REPLAY_MARKER counter=%d candidate_input=%d mode=PLAY scene=unverified",
        counter, counter - 1))
    end
  end
  last_pressed = pressed
  emu.frameadvance()
end
