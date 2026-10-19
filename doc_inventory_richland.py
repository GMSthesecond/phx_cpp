"""Richland County (MT) scanned-document inventory; second step of the "Index" button.

Thin wrapper: the work is in doc_inventory.py (see its docstring for inputs, outputs and the
@PROGRESS / @DONE tags main.cpp reads). Mirror's Index step calls main() too.
"""
import doc_inventory

COUNTY = doc_inventory.RICHLAND  # this county's folders, workbook tab and matching rules


def main():
    """Inventory this county; returns the number of new documents."""
    return doc_inventory.run(COUNTY)


if __name__ == "__main__":
    doc_inventory.run_button(COUNTY)
