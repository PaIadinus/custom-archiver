import os
import struct

MAGIC = b'ARCHIVE\x01'
MAGIC_LEN = len(MAGIC)
MAX_NAME_BYTES = 0xFFFF

TEST_ARCHIVE_FILENAME = 'test.archive'
TEST_ORIGINAL_NAME = 'test_original.txt'
TEST_PAYLOAD = b'Hello from test archive'
CREATE_COMMAND = 'create_archive'


def create_archive(path: str, original_name: str, payload: bytes = b'') -> None:
    name_bytes = original_name.encode('utf-8')
    if len(name_bytes) > MAX_NAME_BYTES:
        raise ValueError('Имя слишком длинное (максимум 65535 байт UTF-8)')
    with open(path, 'wb') as f:
        f.write(MAGIC)
        f.write(struct.pack('>H', len(name_bytes)))
        f.write(name_bytes)
        f.write(payload)


def _parse_archive(path: str):
    try:
        with open(path, 'rb') as f:
            data = f.read()
    except OSError:
        return None

    if len(data) < MAGIC_LEN + 2:
        return None

    if data[:MAGIC_LEN] != MAGIC:
        return None

    name_len = struct.unpack('>H', data[MAGIC_LEN:MAGIC_LEN + 2])[0]
    name_start = MAGIC_LEN + 2
    name_end = name_start + name_len

    if len(data) < name_end:
        return None

    try:
        original_name = data[name_start:name_end].decode('utf-8')
    except UnicodeDecodeError:
        return None

    payload = data[name_end:]
    return original_name, payload


def is_archive(path: str) -> bool:
    return _parse_archive(path) is not None


def get_archive_info(path: str):
    info = _parse_archive(path)
    if info is None:
        raise ValueError(f'Файл {path!r} не является .archive')
    return info


def _core_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _create_test_archive() -> dict:
    archive_path = os.path.join(_core_dir(), TEST_ARCHIVE_FILENAME)
    create_archive(archive_path, TEST_ORIGINAL_NAME, TEST_PAYLOAD)
    return {
        'created': True,
        'path': archive_path,
        'original_name': TEST_ORIGINAL_NAME,
        'size': len(TEST_PAYLOAD),
    }


def identify(path: str):
    if path == CREATE_COMMAND:
        result = _create_test_archive()
        print(f"Тестовый архив создан: {result['path']}")
        print(f"Исходное имя внутри: {result['original_name']}")
        print(f"Размер payload: {result['size']} байт")
        return result

    info = _parse_archive(path)
    if info is None:
        print(f'Файл {path!r} не является .archive.')
        return False

    original_name, payload = info
    print(f'Файл {path!r} — это .archive.')
    print(f'Исходное имя: {original_name}')
    print(f'Размер payload: {len(payload)} байт')
    return True