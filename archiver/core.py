"""Ядро формата .archive — только стандартная библиотека Python.

Формат, версия 2. Раскладка заголовка:

    смещение  поле          размер      значение
    0         magic         4           b"ARCH"
    4         version       1           2
    5         name_len      2           длина имени в байтах
    7         payload_len   8           длина данных в байтах
    15        name          name_len    имя исходного файла, UTF-8

**Все целые числа — big-endian (сетевой порядок байт).** Это осознанное решение:
такой порядок одинаково читается в hex-дампе и совпадает с префиксом ``>`` в
``struct``, поэтому случайный ``<`` не пройдёт незамеченным. Подробности и
правила версионирования — в ``docs/FORMAT.md``.

Модуль не печатает и не принимает решений о кодах выхода: любая проблема
поднимается как :class:`ArchiveError` с машинной причиной :class:`Reason`.
"""

from __future__ import annotations

import os
import struct
from enum import Enum
from pathlib import Path
from typing import BinaryIO, NamedTuple

EXT = ".archive"
MAGIC = b"ARCH"
VERSION = 2
MAX_NAME_BYTES = 0xFFFF
CHUNK_SIZE = 1024 * 1024

_HEADER = struct.Struct(">4sBHQ")
HEADER_SIZE = _HEADER.size  # 15


class Reason(Enum):
    """Машинная причина ошибки — чтобы вызывающий код мог решать сам."""

    NOT_FOUND = "файл не найден"
    IS_DIRECTORY = "это каталог, а не обычный файл"
    NOT_READABLE = "файл нельзя прочитать"
    TOO_SHORT = "файл короче заголовка .archive"
    BAD_MAGIC = "нет сигнатуры .archive"
    BAD_VERSION = "неподдерживаемая версия формата"
    BAD_NAME = "имя исходного файла повреждено"
    NAME_TOO_LONG = "имя исходного файла длиннее 65535 байт"
    TRUNCATED = "файл обрезан: данных меньше, чем указано в заголовке"
    SAME_PATH = "источник и приёмник — один и тот же файл"
    WRITE_ERROR = "не удалось записать архив"


class ArchiveError(Exception):
    """Ошибка ядра: у исключения есть ``reason`` и человекочитаемый текст."""

    def __init__(self, reason: Reason, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason.value}: {detail}" if detail else reason.value)


class Header(NamedTuple):
    """Разобранный заголовок архива."""

    version: int
    original_name: str
    payload_len: int
    payload_offset: int


def read_header(path: str | Path) -> Header:
    """Прочитать только заголовок, не загружая данные в память.

    Raises:
        ArchiveError: с причиной из :class:`Reason`.
    """
    source = Path(path)
    if source.is_dir():
        raise ArchiveError(Reason.IS_DIRECTORY, str(source))
    if not source.exists():
        raise ArchiveError(Reason.NOT_FOUND, str(source))

    try:
        with source.open("rb") as handle:
            return _read_header(handle)
    except PermissionError as exc:
        raise ArchiveError(Reason.NOT_READABLE, f"{source}: {exc}") from exc
    except OSError as exc:
        raise ArchiveError(Reason.NOT_READABLE, f"{source}: {exc}") from exc


def _read_header(handle: BinaryIO) -> Header:
    """Разобрать заголовок из уже открытого файла (потоково)."""
    raw = handle.read(HEADER_SIZE)
    if len(raw) < HEADER_SIZE:
        raise ArchiveError(Reason.TOO_SHORT, f"нужно {HEADER_SIZE} байт, есть {len(raw)}")

    magic, version, name_len, payload_len = _HEADER.unpack(raw)

    if magic != MAGIC:
        raise ArchiveError(Reason.BAD_MAGIC, f"прочитано {magic!r}")

    if version != VERSION:
        raise ArchiveError(
            Reason.BAD_VERSION,
            f"версия {version}, поддерживается {VERSION}",
        )

    if name_len == 0:
        raise ArchiveError(Reason.BAD_NAME, "пустое имя")

    name_bytes = handle.read(name_len)
    if len(name_bytes) < name_len:
        raise ArchiveError(Reason.TRUNCATED, f"имя: ожидалось {name_len} байт")

    try:
        original_name = name_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ArchiveError(Reason.BAD_NAME, str(exc)) from exc

    payload_offset = HEADER_SIZE + name_len
    size = os.fstat(handle.fileno()).st_size
    if size < payload_offset + payload_len:
        raise ArchiveError(
            Reason.TRUNCATED,
            f"ожидалось {payload_offset + payload_len} байт, есть {size}",
        )

    return Header(
        version=version,
        original_name=original_name,
        payload_len=payload_len,
        payload_offset=payload_offset,
    )


def is_archive(path: str | Path) -> bool:
    """Быстрая проверка «наш ли это формат». Ошибки не пробрасывает."""
    try:
        read_header(path)
    except ArchiveError:
        return False
    return True


def default_archive_path(source: str | Path) -> Path:
    """Путь архива по умолчанию: ``<имя источника>.archive``."""
    return Path(str(source) + EXT)


def pack(source: str | Path, dest: str | Path | None = None) -> Header:
    """Упаковать файл без сжатия, копируя данные порциями.

    Args:
        source: путь к исходному файлу.
        dest: путь к архиву; по умолчанию имя источника + ``.archive``.
    """
    src = Path(source)
    dst = default_archive_path(src) if dest is None else Path(dest)

    if src.is_dir():
        raise ArchiveError(Reason.IS_DIRECTORY, str(src))
    if not src.exists():
        raise ArchiveError(Reason.NOT_FOUND, str(src))
    if dst.exists() and dst.resolve() == src.resolve():
        raise ArchiveError(Reason.SAME_PATH, str(src))

    name_bytes = src.name.encode("utf-8")
    if len(name_bytes) > MAX_NAME_BYTES:
        raise ArchiveError(Reason.NAME_TOO_LONG, f"{len(name_bytes)} байт")

    try:
        payload_len = src.stat().st_size
    except OSError as exc:
        raise ArchiveError(Reason.NOT_READABLE, f"{src}: {exc}") from exc

    try:
        _write_archive(src, dst, name_bytes, payload_len)
    except OSError as exc:
        raise ArchiveError(Reason.WRITE_ERROR, f"{dst}: {exc}") from exc

    return Header(
        version=VERSION,
        original_name=src.name,
        payload_len=payload_len,
        payload_offset=HEADER_SIZE + len(name_bytes),
    )


def _write_archive(src: Path, dst: Path, name_bytes: bytes, payload_len: int) -> None:
    """Записать заголовок и скопировать данные кусками по CHUNK_SIZE.

    Пишем во временный ``*.part`` и заменяем цель только после успеха, чтобы
    неудачная упаковка не испортила уже существующий архив.
    """
    header = _HEADER.pack(MAGIC, VERSION, len(name_bytes), payload_len)
    tmp = dst.with_name(dst.name + ".part")
    written = 0

    try:
        with src.open("rb") as reader, tmp.open("wb") as writer:
            writer.write(header)
            writer.write(name_bytes)
            while True:
                chunk = reader.read(CHUNK_SIZE)
                if not chunk:
                    break
                writer.write(chunk)
                written += len(chunk)

        if written != payload_len:
            raise ArchiveError(
                Reason.WRITE_ERROR,
                f"источник изменился при чтении: записано {written} из {payload_len} байт",
            )

        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)
