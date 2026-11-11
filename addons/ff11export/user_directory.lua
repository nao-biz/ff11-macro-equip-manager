-- Read the same selected content ID used by FFXI's USER path formatter.
-- The reader supplies bounded ReadProcessMemory access; no game calls or writes.
local M={}
local function uint(s, at)
    local a,b,c,d=s:byte(at,at+3)
    assert(d,'Truncated identity data')
    return a+b*256+c*65536+d*16777216
end
local function pattern(hex)
    return (hex:gsub('..',function(pair)
        if pair=='??' then return '.' end
        return (string.char(tonumber(pair,16)):gsub('([%%%^%$%(%)%.%[%]%*%+%-%?])','%%%1'))
    end))
end
local path_code=pattern('8B0D????????8B542408528B818000000050E8????????81C6F4010000508B4424145668????????50E8')
local wrapper_code=pattern('8B44240450E8????????83C404C20400')
local getter_code=pattern('8B4C24048D04CD000000002BC18B0D????????8D04808B8481????????C3')
local function relative(data, at, next_address)
    local value=uint(data,at)
    if value>=2147483648 then value=value-4294967296 end
    return next_address+value
end
function M.resolve(image, base, read, installation)
    local start=image:find(path_code)
    assert(start and not image:find(path_code,start+1),'Unsupported USER path formatter')
    local format_address=uint(image,start+36)
    assert(read(format_address,9)=='%s/%x/%s\0','Unsupported USER path format')
    local wrapper=relative(image,start+19,base+start-1+23)
    local code=read(wrapper,16)
    assert(code:find('^'..wrapper_code),'Unsupported USER identity wrapper')
    local getter=relative(code,7,wrapper+10)
    code=read(getter,30)
    assert(code:find('^'..getter_code),'Unsupported USER identity getter')
    local selection_address=uint(image,start+2)
    local table_address=uint(code,16)
    local records_offset=uint(code,26)
    local function word(address) return uint(read(address,4),1) end
    local function sample()
        local selected=word(word(selection_address)+0x80)
        assert(selected<16,'Character selection has not settled')
        local entry=read(word(table_address)+records_offset+selected*140,44)
        local content=uint(entry,1)
        assert(content>0,'Character storage ID unavailable')
        return selected,content,entry
    end
    return function(player_name,server_name)
        local selected,content,entry=sample()
        local name=entry:sub(13,28):match('^([^%z]*)%z')
        local world=entry:sub(29,44):match('^([^%z]*)%z')
        assert(name==player_name and world==server_name,'Selected character has not settled')
        local again,id,other=sample()
        assert(again==selected and id==content and other==entry,'Character changed during identity read')
        return {method='ffxi-user-directory-v1',installation=installation,
                folder_id=string.format('%x',content)}
    end
end
return M
