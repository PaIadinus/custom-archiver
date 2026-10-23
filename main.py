"""Точка входа проекта custom-archiver."""

import sys
from core import identify

def main() -> None:
    path = input("Введите путь до файла (или 'create_archive' для теста): ").strip()
    if not path:
        print("Путь не может быть пустым.")
        return

    result = identify(path)

    if isinstance(result, dict) and result.get('created'):
        sys.exit(0)

    sys.exit(0 if result else 1)


if __name__ == "__main__":
    main()