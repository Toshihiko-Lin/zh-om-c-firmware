"""Run only UI construction/rendering; never download or generate firmware."""
import json
import os
import sys
import traceback
from pathlib import Path

target = Path(sys.argv[sys.argv.index('--zh-ui-test') + 1]).resolve()
target.mkdir(parents=True, exist_ok=True)
try:
    from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QCheckBox, QComboBox, QLineEdit, QWidget
    from PySide6.QtGui import QFont
    from PySide6.QtCore import QSettings
    import i18n
    import message_boxes
    qt = QApplication([])
    QSettings.setDefaultFormat(QSettings.IniFormat)
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(target / 'settings'))
    qt.setFont(QFont('Microsoft YaHei UI', 10))
    qt.setStyleSheet(app_module.STYLE)
    window = app_module.Studio()
    window.resize(1440, 1000)
    window.show()
    qt.processEvents()
    assert window.btn_lang_ko.text() == '简体中文'
    (target / 'language-debug.json').write_text(json.dumps({
        'module_file': i18n.__file__, 'current': i18n.get_language(),
        'title': i18n.t('step1_title'), 'ko_title': i18n.STRINGS['ko']['step1_title'],
        'app_i18n_same': app_module.i18n is i18n,
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    assert i18n.t('step1_title') == '选择相机与固件', repr(i18n.t('step1_title'))
    assert i18n.t('csv_label_custom', count=3) == '正在使用自定义翻译（3 项）'
    window.grab().save(str(target / '01-selection.png'))
    report = {'checks': [], 'korean_ui_residuals': [], 'attributes': list(vars(window))}
    def inspect(root, context):
        for widget in root.findChildren(QWidget):
            if not widget.isVisible():
                continue
            values = []
            if isinstance(widget, (QLabel, QPushButton, QCheckBox)):
                values.append(widget.text())
            if isinstance(widget, QComboBox):
                values.extend(widget.itemText(i) for i in range(widget.count()))
            if isinstance(widget, QLineEdit):
                values.append(widget.placeholderText())
            values.append(widget.toolTip())
            for value in values:
                if any('\uac00' <= c <= '\ud7a3' for c in value):
                    report['korean_ui_residuals'].append({'context': context, 'text': value})
    inspect(window, 'selection')
    for profile in window.catalog:
        body, version = profile['body'], profile['version']
        window.select_profile(body, version)
        p = window.profile()
        if not p:
            report['checks'].append({'body': body, 'skipped': 'profile not found'})
            continue
        window.stack.setCurrentIndex(1)
        qt.processEvents()
        inspect(window, body)
        if body in ('OM-1', 'OM-5 Mark II', 'E-P7', 'PEN-F'):
            window.grab().save(str(target / (body.replace(' ', '-') + '-workspace.png')))
        report['checks'].append({'body': body, 'profile': p['id'], 'feature_count': len(window.checks)})
    window.select_profile('OM-1','1.9')
    if 'korean' in window.checks:
        window.checks['korean'].setChecked(True)
    if 'shutter-sound' in window.checks:
        window.checks['shutter-sound'].setChecked(True)
    qt.processEvents()
    window.grab().save(str(target / '02-editors.png'))
    inspect(window, 'editors')
    assert window.editor_tabs.tabText(0) == '韩语语言包'
    window.editor_tabs.setCurrentIndex(0)
    qt.processEvents()
    inspect(window, 'font-editor')
    window.grab().save(str(target / '02-fonts.png'))
    window.editor_tabs.setCurrentIndex(1)
    if window.sound_panel:
        panel = window.sound_panel
        from PySide6.QtWidgets import QTabWidget
        for tabs in panel.findChildren(QTabWidget):
            for index in range(tabs.count()):
                tabs.setCurrentIndex(index)
                qt.processEvents()
                inspect(window, 'sound-slot-' + str(index))
    window.open_install_guide()
    qt.processEvents()
    inspect(window, 'guide')
    window.grab().save(str(target / '03-guide.png'))
    box = message_boxes.create(window, i18n.t('dialog_confirm_wipe_title'), i18n.t('dialog_confirm_wipe_msg'),
                               message_boxes.QMessageBox.Question,
                               message_boxes.QMessageBox.Yes | message_boxes.QMessageBox.No,
                               message_boxes.QMessageBox.No)
    box.show()
    qt.processEvents()
    assert box.button(message_boxes.QMessageBox.Yes).text() == '是'
    assert box.defaultButton() == box.button(message_boxes.QMessageBox.No)
    assert box.escapeButton() == box.button(message_boxes.QMessageBox.No)
    box.grab().save(str(target / '04-confirmation.png'))
    box.close()
    window.set_language('en')
    qt.processEvents()
    assert i18n.t('step1_title') == 'Select Camera & Stock Firmware'
    window.go_back_step1()
    qt.processEvents()
    window.grab().save(str(target / '05-english.png'))
    window.set_language('ko')
    assert i18n.t('step1_title') == '选择相机与固件'
    (target / 'ui-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    assert not report['korean_ui_residuals'], report['korean_ui_residuals']
    report['language_switch'] = 'PASS'
    report['confirmation_default_and_escape'] = 'No'
    report['status'] = 'PASS'
    (target / 'ui-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    window.close()
    qt.processEvents()
    os._exit(0)
except BaseException:
    (target / 'failure.txt').write_text(traceback.format_exc(), encoding='utf-8')
    os._exit(1)
