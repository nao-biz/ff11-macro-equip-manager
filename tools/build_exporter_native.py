"""Build the Windower 4 bridge with Zig 0.13.0; optionally run a standalone Lua 5.1 test."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--zig', required=True, type=Path)
p.add_argument('--lua-source', type=Path, help='Optional unpacked official Lua 5.1.5 source root')
a = p.parse_args()
zig = str(a.zig.resolve())
assert subprocess.check_output([zig, 'version'], text=True).strip() == '0.13.0'
work = ROOT/'work/native-build'
work.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, ZIG_GLOBAL_CACHE_DIR=str(work/'cache'))
def cc(*args):
    subprocess.run([zig, 'cc', '-target', 'x86-windows-gnu', '-Os', *map(str,args)], check=True, env=env, cwd=ROOT)
bridge = work/'ff11identity-v1.dll'
cc('-shared','-Wall','-Wextra','-Werror',ROOT/'addons/ff11export/native/identity.c','-o',bridge)
if a.lua_source:
    source = a.lua_source.resolve()/'src'
    files = sorted(x for x in source.glob('*.c') if x.name not in ('lua.c','luac.c','print.c'))
    assert len(files)==29, 'Expected Lua 5.1.5 sources'
    cc('-shared','-DLUA_BUILD_AS_DLL',*files,'-o',work/'LuaCore.dll')
    cc(ROOT/'tests/native_identity_host.c','-o',work/'native_identity_host.exe')
    subprocess.run([str(work/'native_identity_host.exe'),str(bridge),str(ROOT/'tests/native_identity.lua')],check=True,cwd=work)
shutil.copyfile(bridge, ROOT/'addons/ff11export'/bridge.name)
