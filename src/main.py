import sys
from PySide6 import QtWidgets
from editor import EditorMainWindow

APP_NAME = "Simpledit"

def main():
    print("[Simpledit] Starting app")
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    w = EditorMainWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
