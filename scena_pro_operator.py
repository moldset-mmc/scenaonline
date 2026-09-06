"""Local SCENA operator console. Customer installations never receive a private key."""
from __future__ import annotations

import getpass
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from scena_licensing import sign_code

APP_DIR = Path(__file__).resolve().parent


def _outside_app(path, app_dir=APP_DIR):
    target = Path(path).expanduser().resolve()
    if target == Path(app_dir).resolve() or Path(app_dir).resolve() in target.parents:
        raise ValueError('Закрытый ключ должен храниться отдельно от папки SCENA и её архивов.')
    return target


def create_issuer_keys(directory, password, *, app_dir=APP_DIR):
    directory = _outside_app(directory, app_dir)
    if len(password) < 12:
        raise ValueError('Для ключа нужен пароль не короче 12 символов.')
    directory.mkdir(parents=True, exist_ok=True)
    private_path, public_path = directory / 'scena-issuer-private.pem', directory / 'scena-issuer-public.pem'
    if private_path.exists() or public_path.exists():
        raise ValueError('Ключи уже существуют. Они не были заменены.')
    key = Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.BestAvailableEncryption(password.encode()))
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    fd = os.open(private_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(private)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        with public_path.open('xb') as stream:
            stream.write(public)
    except Exception:
        # Preserve the successfully created encrypted private key for the operator.
        raise ValueError('Закрытый ключ сохранён; публичный файл не записан. Не создавайте новую пару поверх него.')
    return private_path, public_path


def public_key_fingerprint(path):
    raw = Path(path).read_bytes()
    key = serialization.load_pem_public_key(raw)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError('Нужен публичный ключ Ed25519 SCENA.')
    canonical = key.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return canonical, hashlib.sha256(canonical).hexdigest()


def install_public_key(source, app_dir=APP_DIR):
    public, fingerprint = public_key_fingerprint(source)
    config = Path(app_dir) / 'config'
    config.mkdir(exist_ok=True)
    if config.is_symlink() or Path(app_dir).resolve() not in config.resolve().parents:
        raise ValueError('Небезопасная папка настроек.')
    target = config / 'pro-issuer-public.pem'
    if target.is_symlink():
        raise ValueError('Небезопасный путь публичного ключа.')
    import tempfile
    fd, temp = tempfile.mkstemp(prefix='pro-public-', suffix='.tmp', dir=config)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(public)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, target)
    finally:
        if Path(temp).exists():
            Path(temp).unlink()
    return fingerprint


def main():
    print('SCENA · Управление кодами PRO — только для владельца платформы')
    print('1. Создать ключи владельца\n2. Установить публичный ключ в этот клиентский комплект\n3. Выдать код после проверки оплаты')
    action = input('Выберите 1, 2 или 3: ').strip()
    if action == '1':
        directory = input('Отдельная защищённая папка для ключей (вне папки сайта): ').strip().strip('"')
        password = getpass.getpass('Новый пароль закрытого ключа (не короче 12 символов): ')
        if password != getpass.getpass('Повторите пароль: '):
            raise ValueError('Пароли не совпали. Ключи не созданы.')
        private, public = create_issuer_keys(directory, password)
        print(f'Закрытый ключ: {private}\nПубличный ключ: {public}')
        print('Сохраните закрытый ключ и пароль отдельно. Клиенту передаётся только публичный ключ.')
    elif action == '2':
        source = input('Путь к проверенному публичному ключу SCENA: ').strip().strip('"')
        _, fingerprint = public_key_fingerprint(source)
        print(f'Отпечаток SHA-256: {fingerprint}\nНазначение: {APP_DIR / "config" / "pro-issuer-public.pem"}')
        if input('Сверьте отпечаток с вашим ключом владельца. Для установки введите TRUST SCENA: ').strip() != 'TRUST SCENA':
            print('Установка отменена.')
            return
        install_public_key(source)
        print('Публичный ключ установлен. Закрытый ключ в сайт не копировался.')
    elif action == '3':
        profile = input('Номер профиля клиента из страницы PRO: ').strip()
        days = int(input('Число оплаченных дней (1–730): ').strip())
        print(f'Будет создан код для профиля {profile}, срок продления: {days} дней.')
        if input('Вы лично проверили поступление оплаты? Введите PAYMENT VERIFIED: ').strip() != 'PAYMENT VERIFIED':
            print('Код не создан.')
            return
        path = _outside_app(input('Путь к вашему закрытому ключу: ').strip().strip('"'))
        password = getpass.getpass('Пароль закрытого ключа: ')
        key = serialization.load_pem_private_key(path.read_bytes(), password=password.encode())
        token = sign_code(key, profile, days)
        print('\nПерсональный код. Передайте клиенту всю строку; срок активации — 14 дней:\n')
        print(token)
        print('\nЗапишите выдачу кода в своём учёте оплат. Программа не проверяет банк и не отправляет сообщения.')
    else:
        print('Действие не выбрано.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, EOFError) as exc:
        print(f'Действие не выполнено: {exc}')
        raise SystemExit(1)
