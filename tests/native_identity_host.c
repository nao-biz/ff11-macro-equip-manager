/* Standalone 32-bit Lua 5.1 host, independent from Windower/game files. */
#include <windows.h>
#include <stdio.h>
typedef struct lua_State lua_State;
int main(int argc, char **argv) {
    if (argc != 3) return 2;
    HMODULE host = LoadLibraryA("LuaCore.dll");
    if (!host) return 3;
    lua_State *(__cdecl *newstate)(void) = (void *)GetProcAddress(host,"luaL_newstate");
    void (__cdecl *openlibs)(lua_State *) = (void *)GetProcAddress(host,"luaL_openlibs");
    int (__cdecl *loadfile)(lua_State *,const char *) = (void *)GetProcAddress(host,"luaL_loadfile");
    int (__cdecl *pcall)(lua_State *,int,int,int) = (void *)GetProcAddress(host,"lua_pcall");
    const char *(__cdecl *tolstring)(lua_State *,int,size_t *) = (void *)GetProcAddress(host,"lua_tolstring");
    void (__cdecl *pushnumber)(lua_State *,double) = (void *)GetProcAddress(host,"lua_pushnumber");
    void (__cdecl *pushstring)(lua_State *,const char *) = (void *)GetProcAddress(host,"lua_pushstring");
    void (__cdecl *setfield)(lua_State *,int,const char *) = (void *)GetProcAddress(host,"lua_setfield");
    void (__cdecl *close)(lua_State *) = (void *)GetProcAddress(host,"lua_close");
    if (!newstate || !openlibs || !loadfile || !pcall || !tolstring || !pushnumber || !pushstring || !setfield || !close) return 4;
    lua_State *L = newstate();
    openlibs(L);
    char bytes[] = "synthetic identity bytes";
    pushnumber(L,(double)(uintptr_t)bytes); setfield(L,-10002,"sample_address");
    pushstring(L,argv[1]); setfield(L,-10002,"bridge_path");
    int status = loadfile(L,argv[2]);
    if (!status) status = pcall(L,0,0,0);
    if (status) fprintf(stderr,"%s\n",tolstring(L,-1,NULL));
    close(L);
    return status;
}
