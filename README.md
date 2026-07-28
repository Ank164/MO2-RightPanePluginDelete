# Right Pane Plugin Delete for MO2 2.5.2

Adds **Move plugin file(s) to Recycle Bin** to the context menu in MO2's
right-hand **Plugins** tab.

## Install

1. Close Mod Organizer 2.
2. Copy `right_pane_plugin_delete.py` into MO2's `plugins` directory:
   `Mod Organizer 2\plugins\right_pane_plugin_delete.py`
3. Start MO2.
4. Open **Settings > Plugins** and confirm **Right Pane Plugin Delete** is
   enabled.

## Use

Select one or more `.esp`, `.esm`, or `.esl` entries in the right-hand
**Plugins** tab, right-click, and choose **Move plugin file(s) to Recycle Bin**.

The confirmation dialog shows the owning mod and warns when other installed
plugins depend on a selected file. Files from the real game `Data` directory
are deliberately blocked. Files owned by normal MO2 mods or `Overwrite` are
moved to the Windows Recycle Bin, then MO2 refreshes its lists.

If removing the selected plugin file(s) leaves a normal mod folder containing
only `meta.ini`, a separate **Yes / No** prompt asks whether the entire folder
should also be moved to the Recycle Bin. **No** is the default. This cleanup
never applies to `Overwrite` or the real game `Data` directory.

## Compatibility

Built against the MO2 2.5.2 UI and Python API (Python 3.12 / PyQt 6).

The MO2 API does not currently provide a public context-menu extension point
for the Plugins tab. This plugin supports both MO2's stock `espList` and
Bethesda Plugin Manager Extended's `pluginList` through Qt; a future MO2 UI
update may require a small compatibility update.

Attachment and context-menu diagnostics are written to
`MO2\logs\right-pane-plugin-delete.log`.
