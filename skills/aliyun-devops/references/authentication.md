# codeup setup and credentials

Install this repository as a command with `pipx install .` (recommended) or `python -m pip install .`. It provides `codeup` on Windows, macOS, and Linux. Run `codeup setup` for first-time configuration. The command detects the official Alibaba Cloud CLI and installs it from Alibaba's HTTPS distribution if missing, then installs the official plugin with `aliyun plugin install --names aliyun-cli-devops` if needed.

The wrapper stores the Yunxiao PAT in Windows Credential Manager, macOS Keychain, or Linux Secret Service. If a supported native credential backend is unavailable, it fails closed. Linux may require an unlocked Secret Service provider in the user session. The non-sensitive configuration file remains in the user's application config directory, outside this repository.

The official CLI consumes `ALIBABA_CLOUD_YUNXIAO_ACCESS_TOKEN`, `ALIBABA_CLOUD_YUNXIAO_API_BASE_URL`, and `ALIBABA_CLOUD_YUNXIAO_ORGANIZATION_ID`. The wrapper injects the credential only into the official CLI subprocess. Never pass a PAT through a flag, shell history, source file, or chat.

Central edition uses the organization ID with the CLI's central endpoint. Region edition uses the instance's public API base URL; avoid private network domains. Configure non-sensitive settings with `codeup config set` and inspect them with `codeup config show`.

`codeup setup` uses up/down arrow menus for language and edition, then shows the non-secret Base URL and Organization ID in its console summary. It shows only token status, never the token value. `codeup doctor` checks CLI/plugin installation, edition settings, secure credential storage, and connectivity using the plugin's read-only `base-get-user-by-token` operation. It suppresses API response and diagnostic text. Use `codeup auth rotate` to replace the token and `codeup auth revoke` to remove it. `codeup config reset` clears only the non-sensitive settings.
