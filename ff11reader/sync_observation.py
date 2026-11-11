"""Read-only process and file observations; no editor or Tk ownership."""
from dataclasses import dataclass
import hashlib
from pathlib import Path
from .game_process import game_running
from .augment_sources import AugmentSources
from .windower_settings import WindowerSettings


class SyncConflict(ValueError):
    pass


@dataclass(frozen=True)
class Observation:
    state: str
    data: tuple = ()
    exports: tuple = ()
    message: str = ''


class SyncObserver:
    def __init__(self, root, sources, config_directory, probe=game_running):
        self.root = Path(root)
        self.shared = tuple(Path(s['path']) for s in sources
                            if not Path(s['path']).is_relative_to(self.root/'USER'))
        self.config = Path(config_directory)
        self.probe = probe
        self.metadata = None
        self.signature = None
        self.settling = True

    def paths(self):
        data = set(self.shared)
        data.update(p for p in (self.root/'USER').rglob('*') if p.is_file())
        settings = WindowerSettings(self.config/'windower-settings.json')
        inbox = settings.inbox()
        directories = {inbox} if inbox else {Path(s.directory) for s in
            AugmentSources(self.config/'augment-sources.json').read().values()}
        exports = {p for directory in directories for p in directory.glob('auto-*.json')}
        exports.update(p for p in (self.config/'windower-settings.json', self.config/'augment-sources.json')
                       if p.exists())
        return tuple(sorted(data)), tuple(sorted(exports))

    def sample(self):
        if self.probe():
            self.metadata = None
            self.signature = None
            self.settling = True
            return Observation('running')
        paths = self.paths()
        metadata = tuple(tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in group)
                         for group in paths)
        if metadata != self.metadata or self.settling:
            signature = tuple(tuple((str(p), hashlib.sha256(p.read_bytes()).hexdigest()) for p in group)
                              for group in paths)
        else:
            signature = self.signature
        if self.probe():
            self.metadata = None
            self.signature = None
            self.settling = True
            return Observation('running')
        stable = signature == self.signature
        self.metadata, self.signature = metadata, signature
        self.settling = not stable
        return Observation('ready' if stable else 'settling', *signature)

    def validate(self, expected):
        self.metadata = None  # Rehash, including same-timestamp updates during the read.
        actual = self.sample()
        if actual.state != 'ready' or (actual.data, actual.exports) != (expected.data, expected.exports):
            raise ValueError('ゲームまたは保存データが更新中です。終了後に再確認します。')
