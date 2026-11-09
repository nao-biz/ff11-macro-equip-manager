"""Read-only source adapter. All source handles are opened in rb mode."""
import hashlib
from pathlib import Path
import re
import struct
from . import codecs
from .domain import Character
from . import dictionaries
from .read_requests import CharacterReadRequest
from .resource_catalog import (AUTO_TRANSLATE_RESOURCE, PHRASE_LINKS, AUGMENT_NAME_RESOURCES,
                               RANK_RESOURCES, resource_path, resource_paths)


def discover():
    import winreg
    roots=[]
    for region in ('PlayOnline','PlayOnlineUS','PlayOnlineEU'):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                 rf'SOFTWARE\{region}\InstallFolder',0,
                 winreg.KEY_READ|winreg.KEY_WOW64_32KEY) as key:
                p=Path(winreg.QueryValueEx(key,'0001')[0]).resolve()
                if (p/'USER').is_dir() and p not in roots: roots.append(p)
        except OSError: pass
    return roots


def character_sources(root, request):
    """Enumerate the requested character files without choosing use-case policy."""
    folders = (sorted((root/'USER').iterdir()) if request.folders is None
               else (root/'USER'/folder for folder in request.folders))
    for folder in folders:
        if not folder.is_dir() or not re.fullmatch('[0-9a-fA-F]+', folder.name):
            continue
        paths = (p for p in sorted(folder.iterdir()) if request.filenames is None or p.name.lower() in request.filenames)
        yield folder, (p for p in paths if p.is_file())


class LocalReader:
    def __init__(self, root):
        self.root=Path(root).resolve(); self.sources=[]; self.diagnostics=[]; self.phrase_readings={}

    def read(self,path):
        path=path.resolve()
        if not path.is_relative_to(self.root): raise ValueError('Source outside installation')
        before=path.stat()
        with path.open('rb') as f: data=f.read()
        after=path.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
            raise ValueError('File changed during read; retry loading')
        self.sources.append({'path':str(path),'size':len(data),
            'mtime_ns':after.st_mtime_ns,'sha256':hashlib.sha256(data).hexdigest()})
        return data

    def guarded(self,path,decode):
        try: return decode(self.read(path))
        except (OSError,ValueError,struct.error) as exc:
            self.diagnostics.append({'code':'source_unreadable','path':str(path),'message':str(exc)})
            return None

    def observe_resources(self, logical_ids):
        """Capture raw source evidence independently of successful decoding."""
        table = self.guarded(self.root/'FTABLE.DAT', lambda raw: raw)
        if table is None:
            return
        observed = {Path(source['path']) for source in self.sources}
        for path in resource_paths(self.root, table, logical_ids):
            if path.resolve() not in observed:
                self.guarded(path, lambda raw: None)

    def load_items(self, icon_ids=None):
        items={}; table=self.guarded(self.root/'FTABLE.DAT',lambda b:b)
        if table is None: return items
        for logical in codecs.DAT_IDS:
            if logical*2+2>len(table):
                self.diagnostics.append({'code':'master_table_truncated','logical_id':logical}); continue
            path=resource_path(self.root,table,logical)
            result=self.guarded(path,lambda b:codecs.item_records(b,icon_ids))
            if result:
                source_path=str(path.resolve())
                items.update({key:dict(value,source_path=source_path) for key,value in result.items()})
        return items

    def load_phrases(self):
        table=self.guarded(self.root/'FTABLE.DAT',lambda b:b)
        if table is None: return {}
        def read_dat(logical,decode):
            return self.guarded(resource_path(self.root,table,logical),decode) or {}
        self.phrase_readings={}
        phrases=read_dat(AUTO_TRANSLATE_RESOURCE,lambda data:dictionaries.auto_translate(data,self.phrase_readings))
        linked={key:read_dat(logical,dictionaries.dmsg_names)
                for key,logical in PHRASE_LINKS}
        for key,value in list(phrases.items()):
            if re.fullmatch(r'@[ACJY][0-9A-Fa-f]+',value):
                phrases[key]=linked[value[1]].get(int(value[2:],16),value)
        return phrases

    def load_augment_names(self):
        from .equipment_stat_names import from_dictionary
        table = self.guarded(self.root/'FTABLE.DAT', lambda b: b)
        if table is None:
            return {}
        languages = []
        for logical in AUGMENT_NAME_RESOURCES:
            if logical * 2 + 2 > len(table):
                self.diagnostics.append({'code': 'augment_dictionary_unavailable', 'logical_id': logical})
                return {}
            path = resource_path(self.root, table, logical)
            names = self.guarded(path, dictionaries.dmsg_names)
            if names is None:
                return {}
            languages.append(names)
        return from_dictionary(*languages)

    def load_rank_augments(self):
        from .rank_augments import RankCatalog, decode_bundles
        table = self.guarded(self.root/'FTABLE.DAT', lambda b: b)
        if table is None:
            return None
        results = []
        for logical, decode in zip(RANK_RESOURCES, (decode_bundles, dictionaries.dmsg_names)):
            if logical * 2 + 2 > len(table):
                self.diagnostics.append({'code': 'rank_augments_unavailable', 'logical_id': logical})
                return None
            result = self.guarded(resource_path(self.root, table, logical), decode)
            if result is None:
                return None
            results.append(result)
        return RankCatalog(*results)

    def load_characters(self, resolver=None, *, request=CharacterReadRequest()):
        result=[]
        for folder, paths in character_sources(self.root, request):
            c=Character(folder.name); result.append(c)
            c.inventory_coverage={bag:'missing' for bag in codecs.BAGS.values()}
            for path in paths:
                name=path.name.lower(); decoded=None
                match=re.fullmatch(r'mcr([1-9][0-9]{0,2})?\.dat',name)
                if match and int(match[1] or 0)<400:
                    page=int(match[1] or 0)
                    decoded=self.guarded(path,lambda b:codecs.macros(b,page,resolver))
                    if decoded is not None: c.macros.extend(decoded)
                elif name in ('mcr.ttl','mcr_2.ttl'):
                    decoded=self.guarded(path,lambda b:codecs.book_titles(b,name=='mcr_2.ttl'))
                    if decoded is not None: c.books.update(decoded)
                elif re.fullmatch(r'es[0-9]\.dat',name):
                    decoded=self.guarded(path,lambda b:codecs.equipsets(b,int(name[2])))
                    if decoded is not None: c.equipsets.extend(decoded)
                elif name in codecs.BAGS:
                    decoded=self.guarded(path,lambda b:codecs.inventory(b,codecs.BAGS[name]))
                    c.inventory_coverage[codecs.BAGS[name]]='loaded' if decoded is not None else 'unreadable'
                    if decoded is not None: c.inventory.extend(decoded)
            c.macros.sort(key=lambda m:(m.book,m.palette,m.bank!='ctrl',m.key))
            c.equipsets.sort(key=lambda s:s.number)
        return result

    def verify_unchanged(self):
        changed=[]
        for entry in self.sources:
            p=Path(entry['path']); stat=p.stat()
            with p.open('rb') as f: digest=hashlib.sha256(f.read()).hexdigest()
            if digest!=entry['sha256'] or stat.st_mtime_ns!=entry['mtime_ns']:
                changed.append(str(p))
        return changed
