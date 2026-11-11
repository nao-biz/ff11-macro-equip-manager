-- Windower 4 uses Lua 5.1, without LuaJIT's ffi module.
local resolver=require('user_directory')
local loader,why=package.loadlib(windower.addon_path..'ff11identity-v1.dll','luaopen_ff11identity')
assert(loader,why)
local native=loader()
assert(type(native)=='table','Unsupported Windower Lua ABI')
local function uint(data,offset)
    local a,b,c,d=data:byte(offset,offset+3)
    assert(d,'Truncated module header')
    return a+b*256+c*65536+d*16777216
end
local M={}
function M.new(utf8)
    local base,path=native.module()
    local header=native.read(base,64)
    assert(header:sub(1,2)=='MZ','Invalid game module')
    local pe=uint(header,61)
    assert(pe<1024*1024,'Invalid game module header')
    header=native.read(base+pe,84)
    assert(header:sub(1,4)=='PE\0\0','Invalid game module header')
    local size=uint(header,81)
    local installation=utf8(path):match('^(.*)[/\\][^/\\]+$')
    assert(installation,'Game installation path unavailable')
    return resolver.resolve(native.read(base,size),base,native.read,installation)
end
return M
