/* Lua 5.1 bridge for Windower 4. Current-process reads only. */
#include <windows.h>
#include <stdint.h>
typedef struct lua_State lua_State;
typedef int (__cdecl *lua_CFunction)(lua_State *);
static double (__cdecl *checknumber)(lua_State *, int);
static int (__cdecl *errorf)(lua_State *, const char *, ...);
static void *(__cdecl *newuserdata)(lua_State *, size_t);
static void (__cdecl *pushlstring)(lua_State *, const char *, size_t);
static void (__cdecl *pushnumber)(lua_State *, double);
static void (__cdecl *createtable)(lua_State *, int, int);
static void (__cdecl *pushcclosure)(lua_State *, lua_CFunction, int);
static void (__cdecl *setfield)(lua_State *, int, const char *);
static int read_bytes(lua_State *L) {
    double address = checknumber(L, 1), length = checknumber(L, 2);
    if (!(address >= 65536 && address <= UINT32_MAX && length >= 1 &&
          length <= 32 * 1024 * 1024 && address + length <= 4294967296.0) ||
        address != (double)(uint32_t)address || length != (double)(uint32_t)length)
        return errorf(L, "Invalid identity read range");
    SIZE_T size = (SIZE_T)length, count = 0;
    void *buffer = newuserdata(L, size);
    if (!ReadProcessMemory(GetCurrentProcess(), (void *)(uintptr_t)address,
                           buffer, size, &count) || count != size)
        return errorf(L, "Cannot read game identity (Windows error %lu)", GetLastError());
    pushlstring(L, buffer, size);
    return 1;
}
static int module_info(lua_State *L) {
    HMODULE module = GetModuleHandleA("FFXiMain.dll");
    if (!module) return errorf(L, "Game module unavailable");
    char *path = newuserdata(L, 32768);
    DWORD length = GetModuleFileNameA(module, path, 32768);
    if (!length || length >= 32768) return errorf(L, "Game installation path unavailable");
    pushnumber(L, (double)(uintptr_t)module);
    pushlstring(L, path, length);
    return 2;
}
/* Bind the host Lua ABI rather than bundling a second Lua runtime. */
__declspec(dllexport) int __cdecl luaopen_ff11identity(lua_State *L) {
    HMODULE host = GetModuleHandleA("LuaCore.dll");
    if (!host) return 0;
#define BIND(variable, symbol) do { *(FARPROC *)&variable = GetProcAddress(host, symbol); if (!variable) return 0; } while (0)
    BIND(checknumber, "luaL_checknumber");
    BIND(errorf, "luaL_error");
    BIND(newuserdata, "lua_newuserdata");
    BIND(pushlstring, "lua_pushlstring");
    BIND(pushnumber, "lua_pushnumber");
    BIND(createtable, "lua_createtable");
    BIND(pushcclosure, "lua_pushcclosure");
    BIND(setfield, "lua_setfield");
#undef BIND
    createtable(L, 0, 2);
    pushcclosure(L, read_bytes, 0); setfield(L, -2, "read");
    pushcclosure(L, module_info, 0); setfield(L, -2, "module");
    return 1;
}
