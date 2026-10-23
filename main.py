"""Точка входа проекта custom-archiver.

Команды::

    python main.py identify <путь>          определить, архив это или исходный файл
    python main.py pack <источник> [архив]  упаковать файл в .archive (без сжатия)

Коды выхода:

===== ==============================================================
0     успех: файл является архивом / архив создан
1     файл не является архивом .archive (это исходный файл)
2     ошибка: файла нет, это каталог, архив повреждён и так далее
===== ==============================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from archiver.core import (
    ArchiveError,
    Reason,
    default_archive_path,
    pack,
    read_header,
)

EXIT_OK = 0
EXIT_NOT_ARCHIVE = 1
EXIT_ERROR = 2

# Эти причины означают «файл просто не нашего формата», а не сбой.
NOT_ARCHIVE_REASONS = frozenset({Reason.TOO_SHORT, Reason.BAD_MAGIC})


def _identify(path: str) -> int:
    """Определить тип файла и напечатать результат."""
    try:
        header = read_header(path)
    except ArchiveError as exc:
        if exc.reason in NOT_ARCHIVE_REASONS:
            print(f"это исходный файл: {path}")
            return EXIT_NOT_ARCHIVE
        print(f"ошибка: {exc}", file=sys.stderr)
        return EXIT_ERROR

    print(f"это архив: {path}")
    print(f"версия формата: {header.version}")
    print(f"исходное имя: {header.original_name}")
    print(f"размер данных: {header.payload_len} байт")
    return EXIT_OK


def _pack(source: str, dest: str | None) -> int:
    """Упаковать файл и напечатать сведения о результате."""
    try:
        header = pack(source, dest)
    except ArchiveError as exc:
        print(f"ошибка: {exc}", file=sys.stderr)
        return EXIT_ERROR

    archive_path = Path(dest) if dest is not None else default_archive_path(source)
    print(f"архив создан: {archive_path}")
    print(f"исходное имя: {header.original_name}")
    print(f"размер данных: {header.payload_len} байт")
    return EXIT_OK


def _cmd_identify(args: argparse.Namespace) -> int:
    return _identify(args.path)


def _cmd_pack(args: argparse.Namespace) -> int:
    return _pack(args.source, args.dest)


def build_parser() -> argparse.ArgumentParser:
    """Собрать CLI: подкоманды, справка, значения по умолчанию."""
    parser = argparse.ArgumentParser(
        prog="custom-archiver",
        description="Архиватор собственного формата .archive",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    identify_parser = subparsers.add_parser(
        "identify",
        help="определить, архив это или исходный файл",
    )
    identify_parser.add_argument("path", help="путь к проверяемому файлу")
    identify_parser.set_defaults(handler=_cmd_identify)

    pack_parser = subparsers.add_parser(
        "pack",
        help="упаковать файл в .archive (пока без сжатия)",
    )
    pack_parser.add_argument("source", help="исходный файл")
    pack_parser.add_argument(
        "dest",
        nargs="?",
        help="путь архива (по умолчанию <источник>.archive)",
    )
    pack_parser.set_defaults(handler=_cmd_pack)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Разобрать аргументы и вернуть код выхода, не завершая процесс."""
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    try:
        exit_code = main()
    except KeyboardInterrupt:
        print("прервано пользователем", file=sys.stderr)
        exit_code = EXIT_ERROR
    raise SystemExit(exit_code)
