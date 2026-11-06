-- Pure capture formatting. All game access is supplied by the adapter.
local M = {}
local null = {}
local function array() return setmetatable({}, {array=true}) end
local function quote(s)
    return '"' .. s:gsub('[%z\1-\31\\"]', function(c)
        return string.format('\\u%04x', string.byte(c))
    end) .. '"'
end
local function json(v)
    if v == null then return 'null' end
    if type(v) == 'string' then return quote(v) end
    if type(v) == 'number' then
        assert(v == v and v ~= math.huge and v ~= -math.huge, 'Invalid number')
        return tostring(v)
    end
    if type(v) == 'boolean' then return tostring(v) end
    assert(type(v) == 'table', 'Invalid JSON value')
    local parts = {}
    if getmetatable(v) and getmetatable(v).array then
        for i=1,#v do parts[#parts+1] = json(v[i]) end
        return '[' .. table.concat(parts, ',') .. ']'
    end
    for k,x in pairs(v) do parts[#parts+1] = quote(k) .. ':' .. json(x) end
    table.sort(parts)
    return '{' .. table.concat(parts, ',') .. '}'
end
local function hex(s)
    return (s:gsub('.', function(c) return string.format('%02x', string.byte(c)) end))
end
local function integer(x, low, high)
    return type(x)=='number' and x==math.floor(x) and x>=low and x<=high
end
function M.capture(api, decode, stamp, complete, utf8)
    assert(complete, 'Inventory loading has not completed. Zone once after loading ff11export.')
    local info, player = api.get_info(), api.get_player()
    assert(info and info.logged_in and player, 'Log in before exporting.')
    assert(integer(player.id,1,4294967295), 'Character ID unavailable')
    assert(integer(info.server,0,65535), 'Server ID unavailable')
    local result = {format='ff11-inventory-export',version=1,captured_at=stamp,
        character={id=player.id,name=utf8(player.name),server=info.server},bags=array()}
    for bag=0,16 do
        local ok, meta = pcall(api.get_bag_info,bag)
        local entry = {id=bag,state='unavailable',items=array()}
        result.bags[#result.bags+1] = entry
        if ok and type(meta)=='table' and meta.enabled and meta.enabled ~= 0 then
            entry.state='incomplete'
            local read_ok, rows=pcall(api.get_items,bag)
            if read_ok and type(rows)=='table' and integer(meta.max,0,80) then
                local valid=true
                for index=1,meta.max do
                    local item=rows[index]
                    if type(item)~='table' or not integer(item.id,0,65535) then valid=false;break end
                    if item.id~=0 and item.id~=65535 then
                        if not integer(item.count,1,4294967295) or type(item.extdata)~='string' or #item.extdata~=24
                           or (item.slot~=nil and item.slot~=index) then valid=false;break end
                        local out={index=index,item_id=item.id,count=item.count,extdata=hex(item.extdata),
                            decode_state='unsupported',augments=array(),path=null,rank=null}
                        local decoded,d=pcall(decode,item)
                        if not decoded then out.decode_state='error'
                        elseif type(d)=='table' then
                            out.decode_state='decoded'
                            if type(d.augments)=='table' then
                                for _,a in ipairs(d.augments) do
                                    if type(a)=='string' and a~='none' then out.augments[#out.augments+1]=utf8(a) end
                                end
                            end
                            if d.path=='A' or d.path=='B' or d.path=='C' or d.path=='D' then out.path=d.path end
                            if integer(d.rank,0,127) then out.rank=d.rank end
                        end
                        entry.items[#entry.items+1]=out
                    end
                end
                if valid and integer(meta.count,0,80) and #entry.items==meta.count then entry.state='ready'
                else entry.items=array() end
            end
        end
    end
    local after=api.get_player()
    assert(api.get_info().logged_in and after and after.id==player.id, 'Character changed during export')
    return json(result)
end
return M
