"""Elevated worker entry: authenticate a request and dispatch guarded saving."""
from pathlib import Path
import hashlib
import json
from .elevation import decode


def execute_request(request, expected_hash):
    """Helper entry: read once, authenticate reviewed bytes, then revalidate on disk."""
    raw=Path(request).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_hash:raise ValueError('保存要求が変更されました。プレビューを開き直してください。')
    data=json.loads(raw)
    if set(data)!={'version','plan','backup_root'} or data['version']!=1:raise ValueError('保存要求の形式が不正です。')
    plan=decode(data['plan'])
    from .macro_saving import MacroSavePlan, execute_macro_save
    from .equipment_saving import EquipmentSavePlan, execute_equipment_save
    from .combined_saving import CombinedSavePlan, execute_combined_save
    executors={CombinedSavePlan:execute_combined_save,MacroSavePlan:execute_macro_save,EquipmentSavePlan:execute_equipment_save}
    if type(plan) not in executors:raise ValueError('保存要求の種類が不正です。')
    return executors[type(plan)](plan,Path(data['backup_root']))
