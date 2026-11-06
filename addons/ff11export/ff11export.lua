-- Output-only Windower addon. No equipment/movement/packet injection calls.
_addon.name='ff11export'
_addon.author='ff11-macro-equip-manager'
_addon.version='1.0.0'
_addon.commands={'ff11export'}
local core=require('export_core')
local extdata=require('extdata')
local ready=false
local generation=0
local function invalidate()
    generation=generation+1
    ready=false
end
windower.register_event('login',invalidate)
windower.register_event('logout',invalidate)
windower.register_event('incoming chunk',function(id,data,modified,injected,blocked)
    if injected or blocked then return end
    if id==0x00A or id==0x00B then invalidate()
    elseif id==0x01D and #data>=8 and data:byte(5)==1 then
        local expected=generation
        coroutine.schedule(function()
            if generation==expected and windower.ffxi.get_info().logged_in then ready=true end
        end,2)
    end
end)
local function save(data)
    local dir=windower.addon_path..'data/'
    windower.create_dir(dir)
    local stem=dir..'inventory-'..os.date('!%Y%m%dT%H%M%SZ')
    local path
    for n=1,10000 do
        local candidate=stem..'-'..n..'.json'
        if not windower.file_exists(candidate) then path=candidate;break end
    end
    assert(path,'No available export filename')
    local temp=path..'.tmp'
    local f=assert(io.open(temp,'wb'))
    local ok,err=f:write(data)
    local closed,close_err=f:close()
    if not ok or not closed then os.remove(temp);error(err or close_err) end
    local renamed,rename_err=os.rename(temp,path)
    if not renamed then os.remove(temp);error(rename_err) end
    return path
end
windower.register_event('addon command',function(command)
    if command~='export' then
        windower.add_to_chat(207,'ff11export: //ff11export export (zone once after loading)')
        return
    end
    local ok,result=pcall(function()
        local data=core.capture(windower.ffxi,extdata.decode,os.date('!%Y-%m-%dT%H:%M:%SZ'),ready,windower.from_shift_jis)
        return save(data)
    end)
    windower.add_to_chat(ok and 207 or 123,'ff11export: '..tostring(result))
end)
