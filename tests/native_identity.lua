local load,why=package.loadlib(bridge_path,'luaopen_ff11identity')
assert(load,why)
local native=load()
assert(type(native)=='table')
assert(native.read(sample_address,24)=='synthetic identity bytes')
for _,args in ipairs({{0,4},{-1,4},{sample_address,0},{sample_address,-1},
                     {sample_address,33554433},{4294967295,2},{sample_address+0.5,4},
                     {sample_address,1.5},{0/0,4},{sample_address,math.huge},{65536,1}}) do
    assert(not pcall(native.read,unpack(args)),'unsafe range accepted')
end
local ok,err=pcall(native.module)
assert(not ok and err:find('Game module unavailable',1,true))
-- A second module open shares the host ABI without replacing the Lua runtime.
assert(load().read(sample_address,9)=='synthetic')
print('Native Lua 5.1 bridge: read, invalid ranges, missing module, reload passed')
