"""Macro field and page byte conversion without file access."""
import hashlib
from .codecs import checked, macros
from .macro_inventory import parse_equip


def patch_line(raw, before, after, resolver):
    """Map displayed character boundaries back to original bytes, including ATs."""
    if len(raw)!=61:raise ValueError('マクロ行のサイズが不正です。')
    displayed=''; boundaries=[0]; index=0
    while index<len(raw) and raw[index]:
        if raw[index]==0xFD and index+5<len(raw) and raw[index+5]==0xFD:
            name=resolver(raw[index+1:index+5])
            if name is None:raise ValueError('定型文を解決できません。')
            segment='【'+name+'】';index+=6
        else:
            byte=raw[index];size=2 if 0x81<=byte<=0x9f or 0xe0<=byte<=0xfc else 1
            segment=raw[index:index+size].decode('cp932',errors='strict');index+=size
        displayed+=segment
        boundaries.extend([None]*(len(segment)-1)+[index])
    if displayed!=before or index>=61:raise ValueError('マクロの元バイトと表示が一致しません。')
    command=parse_equip(before);new=parse_equip(after)
    if not command or not new or not command.valid or not new.valid or new.storage is None:
        raise ValueError('収納番号Fixの形式を確認してください。')
    start,end=command.storage_span or (command.item_end,command.item_end)
    inserted=str(new.storage) if command.storage_span else ' '+str(new.storage)
    if before[:start]+inserted+before[end:]!=after:raise ValueError('収納番号以外の変更が含まれています。')
    left,right=boundaries[start],boundaries[end]
    if left is None or right is None:raise ValueError('定型文の内部を変更することはできません。')
    payload=raw[:left]+inserted.encode('ascii')+raw[right:index]
    if len(payload)>60:raise ValueError('収納番号を追加するとマクロ行の60バイト上限を超えます。')
    # Keep the unused trailing bytes; only the new content and NUL are written.
    out=bytearray(raw);out[:len(payload)+1]=payload+b'\0'
    return bytes(out)


def patch_file(original,page,changes,records=()):
    checked(original,7624);out=bytearray(original);seen=set()
    record_keys=set()
    for address,before,base in records:
        book,palette,bank,key=address
        if (book-1)*10+palette-1!=page or bank not in ('ctrl','alt') or type(key) is not int or not 1<=key<=10 or address in record_keys or len(before)!=380 or len(base)!=380:raise ValueError('マクロ原本の配置が不正です。')
        record_keys.add(address)
        offset=24+((0 if bank=='ctrl' else 10)+key-1)*380
        if original[offset:offset+380]!=before:raise ValueError('マクロ原本が変わっています。')
        out[offset:offset+380]=base
    base_data=bytes(out)
    for change in changes:
        book,palette,bank,key=change.address
        if (book-1)*10+palette-1!=page or bank not in ('ctrl','alt') or not 1<=key<=10 or not 0<=change.line<=6:
            raise ValueError('マクロの保存位置が不正です。')
        identity=(change.address,change.line)
        if identity in seen:raise ValueError('保存位置が重複しています。')
        seen.add(identity)
        width=10 if change.line==0 else 61
        offset=24+((0 if bank=='ctrl' else 10)+key-1)*380+(370 if change.line==0 else 4+(change.line-1)*61)
        if base_data[offset:offset+width]!=change.original or len(change.replacement)!=width:
            raise ValueError('元のマクロ行が変わっています。')
        out[offset:offset+width]=change.replacement
    out[8:24]=hashlib.md5(out[24:]).digest()
    macros(bytes(out),page)
    return bytes(out)
