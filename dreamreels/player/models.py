from __future__ import annotations
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

ROLES = ["uid","title","year","poster","backdrop","blurb","source","kind","verified","progress","subtitle","badge"]

class ItemModel(QAbstractListModel):
    def __init__(self, items: list[dict] | None = None):
        super().__init__(); self._items = items or []
    def rowCount(self, parent=QModelIndex()): return len(self._items)
    def data(self, index, role):
        if not index.isValid(): return None
        it = self._items[index.row()]; return it.get(ROLES[role - Qt.UserRole - 1])
    def roleNames(self): return {Qt.UserRole + 1 + i: r.encode() for i, r in enumerate(ROLES)}
    def setItems(self, items): self.beginResetModel(); self._items = list(items); self.endResetModel()
    def get(self, row: int) -> dict: return self._items[row] if 0 <= row < len(self._items) else {}
    @property
    def items(self): return self._items
