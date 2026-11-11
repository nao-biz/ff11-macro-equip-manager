-- Opt-in diagnostic markers for correlation with an external file-access trace.
-- This module never opens USER files or changes game state.
local M = {}
local function quoted(value)
    return '"' .. tostring(value):gsub('[%z\1-\31\\"]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end

function M.start(w, schedule)
    if not w.file_exists(w.addon_path .. 'observe-login.enabled') then return end
    local sequence, generation = 0, 0
    local session = os.date('!%Y%m%dT%H%M%SZ')
    local function record(event)
        local ok, err = pcall(function()
            local info = w.ffxi.get_info() or {}
            local player = w.ffxi.get_player()
            local dir = w.addon_path .. 'data/login-observation/'
            w.create_dir(dir)
            repeat
                sequence = sequence + 1
            until not w.file_exists(dir .. session .. '-' .. sequence .. '.json')
            local path = dir .. session .. '-' .. sequence .. '.json'
            local fields = {
                '"format":"ff11-login-observation"', '"version":1',
                '"event":' .. quoted(event),
                '"observed_at":' .. quoted(os.date('!%Y-%m-%dT%H:%M:%SZ')),
                '"generation":' .. generation,
                '"logged_in":' .. tostring(info.logged_in == true),
                '"character_id":' .. tostring(player and player.id or 'null'),
                '"server":' .. tostring(info.server or 'null'),
                '"character_name":' .. (player and quoted(w.from_shift_jis(player.name)) or 'null'),
            }
            local f = assert(io.open(path, 'wb'))
            local wrote, why = f:write('{' .. table.concat(fields, ',') .. '}\n')
            local closed, close_error = f:close()
            assert(wrote, why)
            assert(closed, close_error)
        end)
        if not ok then w.add_to_chat(123, 'ff11export observation: ' .. tostring(err)) end
    end
    local function observe(event)
        generation = generation + 1
        local expected = generation
        record(event)
        if event ~= 'logout' and event ~= 'unload' then
            for _, seconds in ipairs({2, 10, 30}) do
                schedule(function()
                    if expected == generation then record(event .. '+' .. seconds .. 's') end
                end, seconds)
            end
        end
    end
    for _, event in ipairs({'load', 'login', 'logout', 'unload'}) do
        w.register_event(event, function() observe(event) end)
    end
end
return M
