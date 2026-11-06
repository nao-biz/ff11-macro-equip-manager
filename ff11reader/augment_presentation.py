"""Presentation of supplemental inventory observations."""
def describe(observation, row):
    if observation is None:
        return '個体情報: 未取り込み'
    item = observation.item(row)
    stamp = observation.export.captured_at
    if item is None:
        return f'個体情報: 再Exportが必要（取得日時 {stamp}）'
    parts = []
    if item.decode_state != 'decoded':
        parts.append('オーグメント: 解析できません（生データを保持）')
    else:
        if item.path is not None: parts.append('Path: ' + item.path)
        if item.rank is not None: parts.append('Rank: ' + str(item.rank))
        parts.extend(item.augments)
        if not item.augments and item.path is None: parts.append('オーグメント: 解析結果なし')
    parts.extend([f'数量: {item.count}', f'取得日時: {stamp}'])
    return '\n'.join(parts)


def path_label(observation, row):
    """Short label for an exact, reconciled location."""
    item = observation.item(row) if observation is not None else None
    if item is None or item.decode_state != 'decoded' or item.path is None:
        return ''
    return 'Path ' + item.path
