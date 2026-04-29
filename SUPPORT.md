# Support

Use GitHub Issues for reproducible bugs, feature requests, documentation gaps, and release packaging problems.

Do not open public issues for unpatched security vulnerabilities. Use the process in `SECURITY.md` instead.

When opening an issue, include:

- MediaMop version or commit
- install type: Windows installer, Docker, or local development
- operating system and browser
- exact steps to reproduce
- expected result
- actual result
- relevant logs with secrets and private paths removed

## Windows LAN access

The Windows installer tries to add a firewall rule for `MediaMopServer.exe` on private and domain network profiles. If
Windows policy blocks that rule, setup shows a warning instead of failing silently.

If MediaMop opens locally but another device on your LAN cannot reach it, allow
`C:\Program Files\MediaMop\MediaMopServer.exe` through Windows Firewall for your current network profile. Public network
profiles are not opened automatically; switch the network to Private/Domain or add a manual rule only if that matches
your security setup.

