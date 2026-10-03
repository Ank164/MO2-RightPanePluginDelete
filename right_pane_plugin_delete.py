# SPDX-License-Identifier: GPL-3.0-only
"""MO2 2.5.2 / 2.5.3 plugin: delete plugin files from the right-pane context menu."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import mobase
from PyQt6.QtCore import QEvent, QFile, QObject, QTimer, Qt
from PyQt6.QtGui import QAction, QIcon, QKeySequence
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox, QTreeView


PLUGIN_EXTENSIONS = {".esp", ".esm", ".esl"}


class PluginMenuEventFilter(QObject):
    """PyQt-owned event filter that can be installed on QApplication."""

    def __init__(self, plugin: "RightPanePluginDelete") -> None:
        super().__init__()
        self._plugin = plugin

    def eventFilter(self, watched, event) -> bool:
        return self._plugin.filterMenuEvent(watched, event)


class RightPanePluginDelete(mobase.IPluginTool):
    def __init__(self) -> None:
        super().__init__()
        self._organizer = None
        self._parent_widget = None
        self._menu_filter = None
        self._plugin_view = None
        self._attach_attempts = 0
        self._context_events = 0
        self._menus_augmented = 0
        self._delete_shortcut_action = None
        self._attached_view_name = ""
        self._main_window = None
        self._application_filter_installed = False

    # IPlugin
    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        self._menu_filter = PluginMenuEventFilter(self)
        organizer.onUserInterfaceInitialized(self._on_ui_initialized)
        self._log("plugin initialized; waiting for MO2 user interface")
        return True

    def _on_ui_initialized(self, main_window) -> None:
        self._main_window = main_window
        app = QApplication.instance()
        if app is not None:
            # The extended manager creates its QMenu inside a blocking exec().
            # Filtering QApplication catches QEvent.Show on that menu directly;
            # watching only the tree/viewport misses it.
            app.installEventFilter(self._menu_filter)
            self._application_filter_installed = True
        self._attach_to_plugin_view()

    def name(self) -> str:
        return "Right Pane Plugin Delete"

    def localizedName(self) -> str:
        return self.name()

    def author(self) -> str:
        return "Ron / OpenAI"

    def description(self) -> str:
        return (
            "Adds 'Move plugin file to Recycle Bin' to the Plugins tab "
            "right-click menu."
        )

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 5, 0, mobase.ReleaseType.FINAL)

    def settings(self) -> list[mobase.PluginSetting]:
        return []

    # IPluginTool
    def displayName(self) -> str:
        return "Plugin Delete Help"

    def tooltip(self) -> str:
        return "How to delete ESP/ESM/ESL files from the Plugins tab"

    def icon(self) -> QIcon:
        return QIcon()

    def setParentWidget(self, widget) -> None:
        self._parent_widget = widget

    def display(self) -> None:
        status = (
            f"Status: attached to {self._attached_view_name}."
            if self._plugin_view is not None
            else "Status: Plugins tab not found. Try opening the Plugins tab first."
        )
        QMessageBox.information(
            self._parent_widget,
            self.name(),
            "In the right-hand Plugins tab, select one or more ESP/ESM/ESL "
            "files and press:\n\n"
            "Ctrl+Delete\n\n"
            + status
            + f"\nRight-click events seen: {self._context_events}"
            + f"\nMenus modified: {self._menus_augmented}",
        )

    def filterMenuEvent(self, watched, event) -> bool:
        try:
            is_context_event = event.type() == QEvent.Type.ContextMenu
            is_right_release = (
                event.type() == QEvent.Type.MouseButtonRelease
                and event.button() == Qt.MouseButton.RightButton
            )
            if is_context_event or is_right_release:
                view = self._plugin_view_for(watched)
                if view is not None:
                    self._context_events += 1
                    # MO2 handles this event after the filter returns and enters
                    # QMenu.exec(). The zero-delay callback runs inside that
                    # nested event loop, when activePopupWidget() is the menu.
                    QTimer.singleShot(
                        0,
                        lambda plugin_view=view: self._augment_active_menu(
                            plugin_view, 0
                        ),
                    )
            if (
                event.type() == QEvent.Type.Show
                and self._is_plugin_list_menu(watched)
            ):
                self._augment_menu(watched, watched.parent())
        except Exception as error:
            self._show_error(f"Could not add the delete action:\n\n{error}")
        return False

    def _attach_to_plugin_view(self) -> None:
        if self._plugin_view is not None:
            return

        if self._main_window is not None:
            for wanted_name in ("pluginList", "espList"):
                widget = self._main_window.findChild(QTreeView, wanted_name)
                if widget is not None and (
                    wanted_name == "pluginList" or widget.isVisible()
                ):
                    self._attach_view(widget, wanted_name)
                    return

        # Bethesda Plugin Manager Extended uses "pluginList".  MO2's dormant
        # stock pane is still present as "espList", so attaching to the first
        # espList produces a misleading success while the visible pane receives
        # no events.
        widgets = list(QApplication.allWidgets())
        for wanted_name in ("pluginList", "espList"):
            candidates = [
                widget for widget in widgets
                if hasattr(widget, "objectName")
                and widget.objectName() == wanted_name
                and hasattr(widget, "selectionModel")
                and hasattr(widget, "viewport")
            ]
            candidates.sort(key=lambda widget: not widget.isVisible())
            for widget in candidates:
                if wanted_name == "espList" and not widget.isVisible():
                    continue
                self._attach_view(widget, wanted_name)
                return

        self._attach_attempts += 1
        if self._attach_attempts in (1, 10, 50):
            self._log(
                f"pluginList not found after UI initialization "
                f"(attempt {self._attach_attempts})"
            )
        QTimer.singleShot(500, self._attach_to_plugin_view)

    def _attach_view(self, widget, name: str) -> None:
        self._plugin_view = widget
        self._attached_view_name = name
        widget.installEventFilter(self._menu_filter)
        widget.viewport().installEventFilter(self._menu_filter)
        action = QAction("Move plugin file(s) to Recycle Bin", widget)
        action.setShortcut(QKeySequence("Ctrl+Delete"))
        action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        action.triggered.connect(
            lambda _checked=False, plugin_view=widget:
                self._delete(self._selected_plugin_names(plugin_view))
        )
        widget.addAction(action)
        self._delete_shortcut_action = action
        self._log(
            f"attached to {name}; visible={widget.isVisible()}; "
            f"application_filter={self._application_filter_installed}"
        )

    @staticmethod
    def _plugin_view_for(widget):
        current = widget
        while current is not None:
            if (
                hasattr(current, "objectName")
                and current.objectName() in ("pluginList", "espList")
            ):
                return current
            current = current.parent() if hasattr(current, "parent") else None
        return None

    def _augment_active_menu(self, view, attempt: int) -> None:
        menu = QApplication.activePopupWidget()
        if menu is not None and self._augment_menu(menu, view):
            return
        if attempt < 20:
            QTimer.singleShot(
                25,
                lambda plugin_view=view, next_attempt=attempt + 1:
                    self._augment_active_menu(plugin_view, next_attempt),
            )

    def _augment_menu(self, menu, view) -> bool:
        # QApplication receives Show events for every widget.  In particular,
        # pluginList's viewport is a QWidget whose parent is pluginList; it is
        # not the context menu and has no addSeparator().
        if not isinstance(menu, QMenu):
            return False
        if menu.property("rightPanePluginDeleteAdded"):
            return True
        if view is None or view is not self._plugin_view:
            return False

        menu.setProperty("rightPanePluginDeleteAdded", True)
        names = self._selected_plugin_names(view)
        menu.addSeparator()
        action = QAction("Move plugin file(s) to Recycle Bin", menu)
        action.setEnabled(bool(names))
        action.triggered.connect(
            lambda _checked=False, selected=names: self._delete(selected)
        )
        menu.addAction(action)
        self._menus_augmented += 1
        self._log(
            f"added delete action to context menu; selected={len(names)}"
        )
        return True

    @staticmethod
    def _is_plugin_list_menu(menu: QMenu) -> bool:
        # MO2's PluginListContextMenu and PluginListView are custom C++ Qt
        # subclasses. PyQt does not always report them as instances of their
        # Python base wrappers, so identify them without isinstance().
        if not isinstance(menu, QMenu):
            return False
        parent = menu.parent()
        if parent is None or not hasattr(parent, "objectName"):
            return False
        if parent.objectName() not in ("pluginList", "espList"):
            return False
        return True

    @staticmethod
    def _selected_plugin_names(view: QTreeView) -> list[str]:
        selection_model = view.selectionModel()
        if selection_model is None:
            return []

        names: list[str] = []
        seen: set[str] = set()
        for index in selection_model.selectedRows(0):
            # Group rows in Bethesda Plugin Manager Extended also have text in
            # column zero. Only leaf rows represent actual plugin files.
            if index.model().hasChildren(index):
                continue
            name = str(index.data() or "").strip()
            key = name.casefold()
            if Path(name).suffix.casefold() in PLUGIN_EXTENSIONS and key not in seen:
                names.append(name)
                seen.add(key)
        return names

    def _resolve_plugin(self, name: str) -> tuple[Path, str, Path | None]:
        if Path(name).name != name or Path(name).suffix.casefold() not in PLUGIN_EXTENSIONS:
            raise ValueError(f"Invalid plugin filename: {name}")

        plugin_list = self._organizer.pluginList()
        origin = str(plugin_list.origin(name))
        if not origin:
            raise ValueError(f"MO2 could not determine the origin of {name}.")
        if origin.casefold() == "data":
            raise PermissionError(
                f"{name} belongs to the real game Data directory. "
                "This plugin will not delete base-game files."
            )

        if origin.casefold() == "overwrite":
            root = Path(str(self._organizer.overwritePath()))
            display_origin = "Overwrite"
            cleanup_root = None
        else:
            mod = self._organizer.modList().getMod(origin)
            if mod is None:
                raise ValueError(f"MO2 could not find the owning mod '{origin}'.")
            root = Path(str(mod.absolutePath()))
            display_origin = str(self._organizer.modList().displayName(origin)) or origin
            cleanup_root = root

        root = root.resolve()
        target = (root / name).resolve()
        if target.parent != root:
            raise ValueError(f"Refusing a path outside the owning mod: {target}")
        if not target.is_file():
            raise FileNotFoundError(f"The file no longer exists:\n{target}")
        return target, display_origin, cleanup_root

    @staticmethod
    def _metadata_only_folders_after_delete(
        resolved: list[tuple[str, Path, str, Path | None]],
    ) -> dict[Path, str]:
        selected_by_root: dict[Path, set[Path]] = {}
        display_names: dict[Path, str] = {}
        for _name, path, display_origin, cleanup_root in resolved:
            if cleanup_root is None:
                continue
            root = cleanup_root.resolve()
            selected_by_root.setdefault(root, set()).add(path.resolve())
            display_names[root] = display_origin

        removable: dict[Path, str] = {}
        for root, selected_paths in selected_by_root.items():
            try:
                remaining = [
                    entry
                    for entry in root.iterdir()
                    if entry.resolve() not in selected_paths
                ]
            except OSError:
                continue
            if (
                len(remaining) == 1
                and remaining[0].is_file()
                and remaining[0].name.casefold() == "meta.ini"
            ):
                removable[root] = display_names[root]
        return removable

    def _dependents(self, selected: Iterable[str]) -> list[str]:
        plugin_list = self._organizer.pluginList()
        selected_keys = {name.casefold() for name in selected}
        dependents: list[str] = []
        for candidate in plugin_list.pluginNames():
            candidate = str(candidate)
            if candidate.casefold() in selected_keys:
                continue
            masters = {str(master).casefold() for master in plugin_list.masters(candidate)}
            if masters & selected_keys:
                dependents.append(candidate)
        return dependents

    def _delete(self, names: list[str]) -> None:
        if not names:
            return

        try:
            resolved = [(name, *self._resolve_plugin(name)) for name in names]
        except Exception as error:
            self._show_error(str(error))
            return

        cleanup_folders = self._metadata_only_folders_after_delete(resolved)
        lines = [
            f"• {name}\n  From: {origin}"
            for name, _path, origin, _cleanup_root in resolved
        ]
        dependents = self._dependents(names)
        warning = ""
        if dependents:
            warning = (
                "\n\nWarning: these installed plugins require the selected file(s):\n"
                + "\n".join(f"• {name}" for name in dependents)
            )
        answer = QMessageBox.warning(
            self._parent_widget,
            "Move plugin file(s) to Recycle Bin?",
            "The selected files will be removed from their mods and sent to the "
            "Windows Recycle Bin:\n\n"
            + "\n".join(lines)
            + warning
            + "\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        if cleanup_folders:
            remove_folders = QMessageBox.question(
                self._parent_widget,
                "Remove metadata-only mod folder(s)?",
                "After the selected plugin file(s) are removed, these mod "
                "folders will contain only meta.ini:\n\n"
                + "\n".join(
                    f"• {display_name}"
                    for display_name in cleanup_folders.values()
                )
                + "\n\nMove these folders to the Recycle Bin too?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if remove_folders != QMessageBox.StandardButton.Yes:
                cleanup_folders = {}

        failures: list[str] = []
        moved: list[str] = []
        for name, path, _origin, _cleanup_root in resolved:
            try:
                result = QFile.moveToTrash(str(path))
                success = bool(result[0]) if isinstance(result, tuple) else bool(result)
                if success:
                    moved.append(name)
                else:
                    failures.append(f"{name}: Windows refused the operation")
            except Exception as error:
                failures.append(f"{name}: {error}")

        removed_folders: list[str] = []
        for root, display_name in cleanup_folders.items():
            try:
                remaining = list(root.iterdir())
                if not (
                    len(remaining) == 1
                    and remaining[0].is_file()
                    and remaining[0].name.casefold() == "meta.ini"
                ):
                    continue
                result = QFile.moveToTrash(str(root))
                success = bool(result[0]) if isinstance(result, tuple) else bool(result)
                if success:
                    removed_folders.append(display_name)
                else:
                    failures.append(
                        f"{display_name}: Windows refused to remove the "
                        "metadata-only mod folder"
                    )
            except Exception as error:
                failures.append(f"{display_name} folder: {error}")

        self._organizer.refresh(True)
        if removed_folders:
            self._log(
                "moved metadata-only mod folder(s) to Recycle Bin: "
                + ", ".join(removed_folders)
            )
        if failures:
            QMessageBox.critical(
                self._parent_widget,
                "Some plugin files were not removed",
                ("Moved:\n" + "\n".join(moved) + "\n\n" if moved else "")
                + "Failed:\n"
                + "\n".join(failures),
            )

    def _show_error(self, message: str) -> None:
        self._log(f"ERROR: {message}")
        QMessageBox.critical(
            self._parent_widget, "Right Pane Plugin Delete", message
        )

    @staticmethod
    def _log(message: str) -> None:
        try:
            log_path = Path(__file__).resolve().parent.parent / "logs"
            log_path.mkdir(exist_ok=True)
            with (log_path / "right-pane-plugin-delete.log").open(
                "a", encoding="utf-8"
            ) as stream:
                stream.write(message + "\n")
        except Exception:
            pass


def createPlugin() -> RightPanePluginDelete:
    return RightPanePluginDelete()
