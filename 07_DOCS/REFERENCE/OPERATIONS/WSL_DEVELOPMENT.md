# WSL-native development

`8-AGENT` is a Linux-native repository stored at `/home/jin/8-AGENT`. Use one toolchain boundary:

- Codex desktop **Agent environment**: `Windows Subsystem for Linux`
- repository path inside tools: `/home/jin/8-AGENT`
- Git, Python, tests, and shell scripts: WSL binaries only
- Windows Explorer access: viewing and editor integration only through `\\wsl$`

After changing the Codex setting, restart the desktop app. The setting does not affect a running
agent until restart.

Verify the environment from WSL:

```bash
cd /home/jin/8-AGENT
scripts/check_wsl_dev_environment.sh
```

The check intentionally fails outside WSL, under `/mnt/<drive>`, or when local Git configuration
can rewrite LF line endings or ignore Linux executable bits.

Do not add the UNC repository to Windows Git's `safe.directory`. If native Windows development is
required later, make a separate clone on a Windows drive instead of sharing this working tree
between the two Git implementations.
