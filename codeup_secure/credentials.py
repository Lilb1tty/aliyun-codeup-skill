"""Only built-in native keyring backends are accepted. No plaintext fallback."""

import platform
import uuid
from .errors import CodeupError

SERVICE = "aliyun-cli-devops"


class Credentials:
    def __init__(self):
        try:
            import keyring
            modules = {"Windows": "keyring.backends.Windows",
                       "Darwin": "keyring.backends.macOS",
                       "Linux": "keyring.backends.SecretService"}
            backend = keyring.get_keyring()
            if type(backend).__module__ != modules.get(platform.system()) or backend.priority <= 0:
                raise ValueError()
            self.backend = backend
        except Exception:
            raise CodeupError("credential_store_unavailable",
                              "Native credential store unavailable. Enable Windows Credential Manager, macOS Keychain, or Linux Secret Service.") from None

    def get(self, reference: str) -> str | None:
        try:
            return self.backend.get_password(SERVICE, reference)
        except Exception:
            raise CodeupError("credential_read_failed", "Cannot read native credential store.") from None

    def put(self, token: str) -> str:
        if not token or len(token) > 4096 or any(c.isspace() or not c.isprintable() for c in token):
            raise CodeupError("invalid_token", "PAT must be nonempty, printable, without whitespace (maximum 4096 characters).")
        reference = "profile-" + uuid.uuid4().hex
        try:
            self.backend.set_password(SERVICE, reference, token)
        except Exception:
            raise CodeupError("credential_write_failed", "Cannot write native credential store.") from None
        return reference

    def delete(self, reference: str) -> None:
        try:
            if self.backend.get_password(SERVICE, reference) is not None:
                self.backend.delete_password(SERVICE, reference)
        except Exception:
            raise CodeupError("credential_delete_failed", "Cannot delete native credential reference " + reference + "; retry or remove this reference in the OS vault.") from None
