-- Wait for inventory completion and two matching identity samples per generation.
local M = {}
local function identity(w)
    local info, player = w.ffxi.get_info(), w.ffxi.get_player()
    if not info or not info.logged_in or not player or not player.id or not info.server then return nil end
    return table.concat({player.id, info.server, info.zone or '', player.name or ''}, ':')
end

function M.new(w, schedule, emit)
    local generation, pending, completed = 0, false, false
    local result = {}
    function result.invalidate()
        generation = generation + 1
        pending, completed = false, false
    end
    function result.ready(delay)
        if pending or completed then return end
        pending = true
        local expected, previous, attempts = generation, identity(w), 0
        local function attempt()
            if expected ~= generation then return end
            attempts = attempts + 1
            local current = identity(w)
            local ok, err = false, 'Character information has not settled.'
            if current and current == previous then ok, err = pcall(emit) end
            if ok then
                pending, completed = false, true
                return
            end
            previous = current
            if attempts < 5 then schedule(attempt, 2)
            else
                pending = false
                w.add_to_chat(123, 'ff11export auto: ' .. tostring(err) .. ' Waiting for the next inventory update.')
            end
        end
        schedule(attempt, delay or 2)
    end
    function result.changed()
        result.invalidate()
        result.ready(0.2)
    end
    function result.flush()
        if completed then return end
        local ok, err = pcall(emit)
        result.invalidate()
        completed = ok
        if not ok then w.add_to_chat(123, 'ff11export final: ' .. tostring(err)) end
    end
    return result
end
return M
