"""Gestión segura de secretos.

Filosofía (lo que el usuario pidió explícitamente): un token o dato sensible
**nunca se escribe en texto plano en disco** ni queda en los datos de Prisma.
Solo se mantiene el tiempo justo para hacer la petición.

Dos backends:

- :class:`KeychainSecretStore` — **Llavero de macOS** (opt-in). Guarda el secreto
  cifrado por el sistema, accesible solo por tu usuario. Usa el binario
  ``security`` de macOS; Prisma nunca ve el fichero, solo pide el valor al sistema
  en el momento de usarlo.
- :class:`MemorySecretStore` — **solo en memoria**. El secreto vive en la RAM del
  proceso y desaparece al cerrar. Es el fallback fuera de macOS y la opción
  máxima-privacidad. Tú lo apuntas en tu libreta y lo reintroduces cuando haga falta.

El "servicio" en el Llavero se prefija con ``prisma:`` para no mezclarse con otras
credenciales.
"""

from __future__ import annotations

import subprocess
import sys
from abc import ABC, abstractmethod
from typing import Optional

SERVICE_PREFIX = "prisma:"

#: Indirección para poder testear sin tocar el Llavero real.
_run = subprocess.run


class SecretStore(ABC):
    """Almacén de secretos. Las claves se identifican por ``name``."""

    @abstractmethod
    def set(self, name: str, value: str) -> None: ...

    @abstractmethod
    def get(self, name: str) -> Optional[str]: ...

    @abstractmethod
    def delete(self, name: str) -> bool: ...

    @property
    @abstractmethod
    def persistent(self) -> bool:
        """¿Sobrevive el secreto al cierre del proceso?"""


class MemorySecretStore(SecretStore):
    """Secretos solo en memoria: nada toca el disco. Se olvidan al salir."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def set(self, name: str, value: str) -> None:
        self._data[name] = value

    def get(self, name: str) -> Optional[str]:
        return self._data.get(name)

    def delete(self, name: str) -> bool:
        return self._data.pop(name, None) is not None

    @property
    def persistent(self) -> bool:
        return False


class KeychainSecretStore(SecretStore):
    """Secretos en el Llavero de macOS vía el binario ``security``."""

    def __init__(self, account: str = "prisma") -> None:
        self.account = account

    def _service(self, name: str) -> str:
        return f"{SERVICE_PREFIX}{name}"

    def set(self, name: str, value: str) -> None:
        # -U actualiza si ya existe. El valor va por -w (no queda en el shell
        # como argumento visible si se pasa por stdin; aquí usamos -w por
        # simplicidad del binario, que no lo registra en disco).
        _run(
            ["security", "add-generic-password", "-a", self.account,
             "-s", self._service(name), "-w", value, "-U"],
            check=True, capture_output=True, text=True,
        )

    def get(self, name: str) -> Optional[str]:
        proc = _run(
            ["security", "find-generic-password", "-a", self.account,
             "-s", self._service(name), "-w"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout.strip() or None

    def delete(self, name: str) -> bool:
        proc = _run(
            ["security", "delete-generic-password", "-a", self.account,
             "-s", self._service(name)],
            capture_output=True, text=True,
        )
        return proc.returncode == 0

    @property
    def persistent(self) -> bool:
        return True


def keychain_available() -> bool:
    """¿Estamos en macOS con el binario ``security`` disponible?"""
    if sys.platform != "darwin":
        return False
    try:
        _run(["security", "help"], capture_output=True, text=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def get_secret_store(use_keychain: bool = True) -> SecretStore:
    """Devuelve el mejor almacén disponible.

    Con ``use_keychain=True`` y en macOS, usa el Llavero; en cualquier otro caso
    cae a memoria (nada en disco).
    """
    if use_keychain and keychain_available():
        return KeychainSecretStore()
    return MemorySecretStore()
