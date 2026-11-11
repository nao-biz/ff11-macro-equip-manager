-- Output-only Windower addon. No equipment/movement/packet injection calls.
_addon.name='ff11export'
_addon.author='ff11-macro-equip-manager'
_addon.version='1.2.0'
_addon.commands={'ff11export'}
local core=require('export_core')
local extdata=require('extdata')
if windower.file_exists(windower.addon_path..'observe-login.enabled') then
    require('login_observation').start(windower,coroutine.schedule)
end
local ready=false
local generation=0
local automatic
local function invalidate()
    generation=generation+1
    ready=false
    if automatic then automatic.invalidate() end
end
windower.register_event('login',invalidate)
local function finish()
    if ready and automatic then automatic.flush() end
    invalidate()
end
windower.register_event('logout',finish)
windower.register_event('unload',finish)
windower.register_event('outgoing chunk',function(id,data,modified,injected,blocked)
    if id==0x00D and not injected and not blocked and ready then automatic.flush() end
end)
windower.register_event('incoming chunk',function(id,data,modified,injected,blocked)
    if injected or blocked then return end
    if id==0x00A then invalidate()
    elseif id==0x00B then finish()
    elseif (id==0x01E or id==0x01F or id==0x020) and ready then automatic.changed()
    elseif id==0x01D and #data>=8 and data:byte(5)==1 then
        local expected=generation
        coroutine.schedule(function()
            if generation==expected and windower.ffxi.get_info().logged_in then
                ready=true
                automatic.ready()
            end
        end,2)
    end
end)
local function save(data, auto_stem)
    local dir=windower.addon_path..'data/'
    windower.create_dir(dir)
    local stem=dir..(auto_stem or ('inventory-'..os.date('!%Y%m%dT%H%M%SZ')))
    local path
    for n=1,10000 do
        local candidate=stem..'-'..string.format('%06d',n)..'.json'
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
automatic=require('auto_export').new(windower,coroutine.schedule,function()
    local info, player = windower.ffxi.get_info(), windower.ffxi.get_player()
    local stamp=os.date('!%Y-%m-%dT%H:%M:%SZ')
    local data=core.capture(windower.ffxi,extdata.decode,stamp,ready,windower.from_shift_jis,true)
    local stem='auto-'..info.server..'-'..player.id..'-'..stamp:gsub('[-:]','')
    local path=save(data,stem)
    windower.add_to_chat(207,'ff11export auto: '..path)
end)
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
