"""Detailed section timing with source-call attribution for path and hash work."""
import json
import sys
import time
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import persistence_cycles
from ff11reader import save_state, combined_saving, equipment_saving, file_transaction, saving, macro_saving, application
from ff11reader.edit_state import SnapshotState
from ff11reader.edit_application import Editor


def main():
    rows = []
    nesting = []
    result_path = []
    output = sys.stdout

    class Output:
        def write(self, value):
            if value.startswith('RESULT '):
                result_path.append(Path(value[7:].strip()))
            return output.write(value)

        def flush(self): return output.flush()

    def measured(name, function):
        def call(*args, **kwargs):
            low_level = name in ('Path.resolve', 'Path.read_bytes') or name.endswith('.digest')
            if low_level and not nesting:
                return function(*args, **kwargs)
            caller = sys._getframe(1).f_code
            caller_name = Path(caller.co_filename).name + ':' + caller.co_name
            entry = [time.perf_counter(), 0.0]
            parent = nesting[-1][2] if nesting else None
            nesting.append([entry, None, name])
            try:
                return function(*args, **kwargs)
            finally:
                duration = time.perf_counter()-entry[0]
                nesting.pop()
                if nesting: nesting[-1][0][1] += duration
                rows.append(dict(name=name, parent=parent, caller=caller_name, seconds=duration,
                                 exclusive_seconds=duration-entry[1]))
        return call

    targets = [
        (application, 'load_snapshot'),
        (macro_saving, 'replay_macro_proposal' if hasattr(macro_saving, 'replay_macro_proposal') else 'deepcopy'),
        (macro_saving, 'prepare_macro_save'),
        (Path, 'resolve'),
        (Path, 'read_bytes'),
        (saving, 'digest'),
        (combined_saving, 'digest'),
        (equipment_saving, 'digest'),
        (file_transaction, 'digest'),
        (equipment_saving, 'require_same_targets'),
        (equipment_saving, 'validate_evidence'),
        (equipment_saving, 'plan_fixes'),
        (equipment_saving, 'transfer_data'),
        (SnapshotState, 'save_input'),
        (save_state, 'prepare_writeback'),
        (save_state, 'save_checkpoint'),
        (combined_saving, 'prepare_combined_save'),
        (combined_saving, 'execute_batch'),
        (equipment_saving, 'prepare_equipment_save'),
        (SnapshotState, 'read_character'),
        (SnapshotState, 'items'),
        (SnapshotState, 'updated'),
        (Editor, 'prepare_equipment_slot_edit'),
        (Editor, 'apply'),
        (Editor, 'writeback'),
    ]
    with ExitStack() as stack:
        stack.enter_context(patch.object(sys, 'stdout', Output()))
        for owner, name in targets:
            label = owner.__name__+'.'+name
            stack.enter_context(patch.object(owner, name, measured(label, getattr(owner, name))))
        capture = save_state.SaveRequest.capture
        stack.enter_context(patch.object(save_state.SaveRequest, 'capture',
                                         measured('SaveRequest.capture', capture)))
        persistence_cycles.main()
    path = result_path[0].with_name('detailed-profile.json')
    path.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    print('PROFILE '+str(path))
    for name in sorted({r['name'] for r in rows}):
        values = [r for r in rows if r['name'] == name]
        print(json.dumps(dict(name=name, calls=len(values),
            total_seconds=sum(r['seconds'] for r in values),
            exclusive_seconds=sum(r['exclusive_seconds'] for r in values))))


if __name__ == '__main__': main()
