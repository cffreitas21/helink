from PySide6.QtWidgets import QMenu, QSizePolicy, QToolButton

from helink.models.flight import AlertTrigger


class TriggerButton(QToolButton):
    def __init__(self, alert, parent=None):
        super().__init__(parent)
        triggers = self.valid_triggers(alert)
        self.setObjectName('triggerList')
        self.setMinimumWidth(112)
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        self.setText(
            f'{len(triggers)} trigger' if len(triggers) == 1
            else f'{len(triggers)} triggers'
        )
        menu = QMenu(self)
        heading = menu.addAction('TRIGGER DETAILS')
        heading.setEnabled(False)
        menu.addSeparator()
        if triggers:
            for trigger in triggers:
                value = ' '.join(
                    part for part in (trigger.value, trigger.units) if part
                ) or '—'
                state = f'  [{trigger.state}]' if trigger.state else ''
                action = menu.addAction(
                    f'{trigger.name}:  {value}{state}'
                )
                action.setEnabled(False)
        else:
            empty = menu.addAction('No trigger details')
            empty.setEnabled(False)
        self.setMenu(menu)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setToolTip(
            '<br>'.join(
                f'<b>{trigger.name}</b>: {trigger.value} '
                f'{trigger.units} ({trigger.state})'
                for trigger in triggers
            ) or 'No trigger details'
        )

    @staticmethod
    def valid_triggers(alert):
        triggers = [
            trigger for trigger in alert.triggers
            if str(trigger.value or '').strip().upper() != 'UNK'
        ]
        legacy_value = str(alert.trigger_value or '').strip()
        if not triggers and alert.trigger_name and legacy_value.upper() != 'UNK':
            triggers = [AlertTrigger(
                alert.trigger_name,
                legacy_value,
                alert.trigger_units or '',
                alert.trigger_state or '',
            )]
        return triggers
