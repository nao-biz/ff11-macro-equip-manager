"""Character-wide clear confirmation using the shared modal and worker."""
from . import dialogs
from .ui_tasks import background


def clear_character(view):
    character = view.character
    if character is None or view.editor.blocked:return
    folder = character.folder_id
    message = (f'対象キャラ: {character.display_name or "名前未確認"} [{folder}]\n\n'
               '全40ブックのブック名・マクロ名・本文と、全200件の装備セット名・装備内容を空にします。\n'
               'このキャラの入力中のマクロも消去対象です。所持品情報と他キャラのデータは保持します。\n\n'
               '全消去はUndoで戻せます。ゲームへの反映は「ゲームへ書き戻す…」で行います。\n\n'
               'マクロと装備セットを全消去しますか？')
    modal = dialogs.Modal(view.app, 'マクロ・装備セットを全消去', message, 'confirm')
    modal.ok_button.configure(text='全消去する')
    modal.cancel_button.configure(text='キャンセル')
    if not modal.wait():return
    try:
        # Validate readability before publishing pending text into edit history.
        background(view.app, view.editor.prepare_character_clear, folder)
        view.macro_panel.apply_pending(folder)
        preview = background(view.app, view.editor.prepare_character_clear, folder)
        view.run_edit(lambda:view.editor.clear_character(folder, preview))
    except (ValueError, OSError) as exc:
        dialogs.showerror('全消去できません', str(exc), parent=view.app)
        return
    view.footer.configure(text=f'{character.display_name or folder} のマクロ・装備セットを全消去しました。Undoで戻せます。')
