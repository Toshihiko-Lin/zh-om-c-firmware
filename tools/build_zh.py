"""Build the Chinese desktop UI from the pinned upstream Windows release.

Only UI Python modules are replaced. Firmware engines, profiles, fonts and
camera resources are copied byte-for-byte and verified after rebuilding.
"""
import hashlib
import json
import marshal
import string
import sys
import types
from pathlib import Path

from pyinstaller_archive import Archive, Pyz, EXPECTED_SHA256

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'upstream-releases/db.firmware.0.3.1.exe'
OUTPUT = ROOT / 'dist/db-firmware-0.3.1-zh-CN.exe'


def load(name):
    return json.loads((ROOT / 'localization' / name).read_text(encoding='utf-8'))


def strings(value):
    if isinstance(value, types.CodeType):
        for child in value.co_consts:
            yield from strings(child)
    elif isinstance(value, (tuple, frozenset)):
        for child in value:
            yield from strings(child)
    elif isinstance(value, str):
        yield value


def replace(value, mapping):
    if isinstance(value, types.CodeType):
        if value.co_name == '_sync_editor_tabs':
            mapping = dict(mapping, **{'한국어': '韩语语言包'})
        return value.replace(co_consts=tuple(replace(v, mapping) for v in value.co_consts))
    if isinstance(value, tuple):
        return tuple(replace(v, mapping) for v in value)
    if isinstance(value, frozenset):
        return frozenset(replace(v, mapping) for v in value)
    return mapping.get(value, value) if isinstance(value, str) else value


def wrap(original, source, filename):
    # Compile a normal wrapper; never change opcodes, branch targets or code sizes.
    source = 'import marshal as _zh_marshal\nexec(_zh_marshal.loads(' + repr(marshal.dumps(original)) + '), globals())\n' + source
    return compile(source, filename, 'exec')


def build():
    if sys.version_info[:2] != (3, 12):
        raise SystemExit('Build requires Python 3.12 (same bytecode version as upstream).')
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise SystemExit('Upstream SHA-256 mismatch; refusing to patch another build.')
    archive = Archive(SOURCE)
    pyz = Pyz(archive.read('PYZ.pyz'))
    original_i18n = pyz.read('i18n')
    ns = {}
    exec(original_i18n, ns)  # i18n only defines dictionaries/functions; no GUI or I/O.
    zh = load('zh_CN.json')
    assert zh.keys() == ns['STRINGS']['ko'].keys(), 'Translation key mismatch'
    mapping = dict(zip(ns['STRINGS']['ko'].values(), (zh[k] for k in ns['STRINGS']['ko'])))
    mapping.update(load('extra_strings.json'))
    mapping.update(load('sound_strings.json'))
    mapping.update(load('feature_strings.json'))
    for old, new in zip(ns['GUIDE_STEPS_TRANSLATIONS']['ko'], load('guide_zh_CN.json')):
        mapping.update(zip(old, new))
    # Keep format names, conversions and numeric specifications intact.
    def fields(s):
        return sorted((name, spec, conversion) for _, name, spec, conversion in string.Formatter().parse(s) if name is not None)
    for k, v in zh.items():
        assert fields(v) == fields(ns['STRINGS']['ko'][k]), k

    sound = pyz.read('sound_panel')
    guide = next(s for s in strings(sound) if s.startswith('① 권장 음원:'))
    p4 = next(s for s in mapping if s.startswith('④ 펌웨어 음원 공간은'))
    p5 = '최종 카메라 볼륨은 카메라의 셔터음 항목에서 조절합니다.'
    mapping[guide] = '\n'.join([
        '① 建议使用 0.2～0.5 秒、清晰短促的音效。开头应尽量少留静音，并有明显起音，以便连拍时辨识。',
        '② 支持导入 WAV（PCM／Float）、MP3、FLAC、M4A 和 OGG。压缩格式取决于内置解码器；解码失败时请先转为 PCM WAV。输入最大 32 MB、最长 5 秒，支持单声道和立体声。',
        '③ 导入后转为 48 kHz、16 位、立体声 PCM。慢／快快门默认速率为 90%／110%。单拍完整播放；连拍在下一次允许的拍摄事件重新触发，最后一次播放至结束。',
        mapping[p4] + '自动适配会压缩整段音频的时长，同时提高音调。若要保持自然效果，请用起止位置选取较短片段。',
        '⑤ 自动音量将峰值调整至约 80%，并在首尾加入短淡入淡出，避免爆音。起音增强可提高连拍时的可辨识度。' + mapping[p5] + '电脑扬声器音量与相机音量不同。',
        '⑥ 可导出慢／快快门 WAV 和连拍示例。相机根据拍摄事件重新触发同一完整音频，而非循环播放单独的连拍录音。SH2 最多每秒触发 50 次，SH1 不播放快门音效。更改设置后需要重新生成固件。'
    ])
    patches = {}
    counts = {}
    for name in ('app', 'i18n', 'sound_panel'):
        old = pyz.read(name)
        local = dict(mapping)
        if name == 'app':
            local['Pretendard'] = 'Microsoft YaHei UI'
            local['DBFirmware'] = 'DBFirmwareZhCN'
            for text in strings(old):
                if "font-family: 'Pretendard'" in text:
                    local[text] = text.replace("font-family: 'Pretendard'", "font-family: 'Microsoft YaHei UI', 'Microsoft YaHei', 'Pretendard'")
        patches[name] = replace(old, local)
        counts[name] = sum(s in local for s in strings(old))
    # Feature labels live in immutable firmware profiles. Translate the values
    # returned to the UI, without modifying profiles or their patch data.
    features = load('feature_strings.json')
    features['한국어'] = '韩语语言包'
    features.update({k: v for k, v in mapping.items() if k in (
        'Korean menus/help (camera display unverified)',
        'Replaces the Japanese language slot. Exact stock v1.1 only; resource/font/checksum checks passed offline.',
        'Unavailable: PEN-F v0.2.8 boot-loop incident.',
        'A physical boot failure was reported. This patch is blocked in both the UI and firmware generator.')})
    patches['i18n'] = wrap(patches['i18n'], f'''
_zh_features = {features!r}
_zh_original_features = get_feature_strings
def get_feature_strings(fid, raw_title, raw_status, raw_detail):
    result = _zh_original_features(fid, raw_title, raw_status, raw_detail)
    if CURRENT_LANG == 'ko':
        return tuple(_zh_features.get(v, v) for v in result)
    return result
''', 'i18n_zh.py')
    patches['app'] = wrap(patches['app'], f'''
_zh_font_original = ensure_pretty_fonts
_zh_font_loaded = False
def ensure_pretty_fonts():
    global _zh_font_loaded
    _zh_font_original()
    if not _zh_font_loaded:
        from PySide6.QtGui import QFontDatabase
        from pathlib import Path
        import os
        font_dir = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for filename in ('msyh.ttc', 'msyhbd.ttc'):
            path = font_dir / filename
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))
        _zh_font_loaded = True
_zh_card_init_original = HoverFeatureCard.__init__
_zh_card_strings = {features!r}
def _zh_card_init(self, short_text, detail_text, parent=None):
    if i18n.get_language() == 'ko':
        short_text = _zh_card_strings.get(short_text, short_text)
        detail_text = _zh_card_strings.get(detail_text, detail_text)
    _zh_card_init_original(self, short_text, detail_text, parent)
HoverFeatureCard.__init__ = _zh_card_init
_zh_rebuild_original = Studio._rebuild_features_for_profile
def _zh_rebuild(self, profile):
    _zh_rebuild_original(self, profile)
    if i18n.get_language() == 'ko':
        from PySide6.QtWidgets import QLabel
        for card in self.feature_cards.values():
            for label in card.findChildren(QLabel):
                text = label.text()
                if text in _zh_card_strings:
                    label.setText(_zh_card_strings[text])
Studio._rebuild_features_for_profile = _zh_rebuild
''', 'app_zh.py')
    rebuilt_pyz = pyz.write(patches)
    # The script entry and PYZ app module must receive the same UI/font edits.
    original_app = patches['app']
    bootstrap = '''
import sys, os, marshal
if '--zh-ui-test' in sys.argv:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    import app as _zh_app
    exec(compile(ZH_TEST, 'zh_ui_test.py', 'exec'), {'app_module': _zh_app, '__name__': '__main__'})
else:
    import app as _zh_app
    if any(arg in sys.argv for arg in ('--remaining-audio-self-test', '--wifi-self-test')):
        exec(marshal.loads(APP_CODE), globals())
    else:
        sys.exit(_zh_app.main())
'''.replace('ZH_TEST', repr((ROOT / 'tools/ui_smoke.py').read_text(encoding='utf-8'))).replace('APP_CODE', repr(marshal.dumps(original_app)))
    OUTPUT.parent.mkdir(exist_ok=True)
    archive.write(OUTPUT, {'PYZ.pyz': rebuilt_pyz, 'app': marshal.dumps(compile(bootstrap, 'zh_bootstrap.py', 'exec'))})
    rebuilt = Archive(OUTPUT)
    unchanged = [name for name, *_ in archive.entries if name not in ('app', 'PYZ.pyz')]
    for name in unchanged:
        assert archive.read(name) == rebuilt.read(name), name
    check = Pyz(rebuilt.read('PYZ.pyz'))
    untouched = [name for name, _ in pyz.entries if name not in patches]
    old_index = dict(pyz.entries)
    new_index = dict(check.entries)
    for name in untouched:
        kind, pos, size = old_index[name]
        new_kind, new_pos, new_size = new_index[name]
        assert (kind, size) == (new_kind, new_size), name
        assert pyz.data[pos:pos + size] == check.data[new_pos:new_pos + new_size], name
    report = {
        'source_sha256': EXPECTED_SHA256,
        'output_sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        'modified_modules': list(patches), 'translation_occurrences': counts,
        'unchanged_archive_entries': len(unchanged),
        'unchanged_python_modules': len(untouched),
        'firmware_profiles_and_assets_unchanged': True,
        'output': OUTPUT.name
    }
    (OUTPUT.parent / 'build-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    build()
