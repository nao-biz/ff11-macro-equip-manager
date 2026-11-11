# Windower 4 native reader

Windower 4 embeds Lua 5.1 and does not provide LuaJIT `ffi`. The bundled
`ff11identity-v1.dll` exports a Lua C module loaded from the addon directory.
It resolves the host Lua API from `LuaCore.dll`; it does not load another Lua
runtime. Its two functions report the current FFXiMain module/path and copy a
bounded memory range from the current process. It does not invoke game functions
or write game memory. Lua owns the temporary read buffers.

Build with the official [Zig 0.13.0](https://ziglang.org/download/0.13.0/release-notes.html)
Windows x64 toolchain (archive SHA256
`d859994725ef9402381e557c60bb57497215682e355204d754ee3df75ee3c158`):

```powershell
.venv/Scripts/python.exe tools/build_exporter_native.py --zig <zig.exe>
```

To test the compiled 32-bit DLL outside the game, add
`--lua-source <unpacked-lua-5.1.5>` using the official
[Lua 5.1.5 sources](https://www.lua.org/ftp/lua-5.1.5.tar.gz).
The test creates a separate LuaCore.dll in `work/native-build`, exercises the
Lua 5.1 ABI, real memory copying, invalid/overflow/unreadable ranges, missing game
module, and repeated loading. No Windower or game files are used by this test.

The installer includes the DLL in its hashed bundle and rollback. Once loaded,
Windows may keep it mapped until game exit. A change to native DLL code must use
a new versioned filename in both the loader and installer; Lua-only updates can
retain the existing filename. Keep older loaded DLLs until the game exits.
