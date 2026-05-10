from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem


def make_table(headers: list[str], min_rows: int = 5) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(24)
    table.horizontalHeader().setStretchLastSection(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    table.setMinimumHeight(26 * min_rows + 34)
    return table


def fill_table(table: QTableWidget, rows: list[list[str]]):
    table.setRowCount(0)
    for row in rows:
        add_row(table, row)


def add_row(table: QTableWidget, values: list[str], top: bool = False):
    row_index = 0 if top else table.rowCount()
    table.insertRow(row_index)
    for col, value in enumerate(values):
        item = QTableWidgetItem(str(value))
        item.setTextAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        table.setItem(row_index, col, item)


def selected_row_text(table: QTableWidget) -> str:
    indexes = table.selectionModel().selectedRows()
    if not indexes:
        return ""
    row = indexes[0].row()
    values = []
    for col in range(table.columnCount()):
        header = table.horizontalHeaderItem(col).text()
        item = table.item(row, col)
        values.append(f"{header}: {item.text() if item else ''}")
    return "\n".join(values)
