# Smoke Checklists

These checklists define the minimum user-level validation before calling a release ready. Automated CI checks are necessary but not enough; these are the click-through paths that catch packaging and first-run regressions.

## Windows installer smoke

Use `MediaMopSetup.exe` from the release being validated.

1. Install MediaMop on a clean Windows user profile or a reset test profile.
2. Confirm application files install under `C:\Program Files\MediaMop`, not a user profile.
3. Confirm runtime data is created under `C:\ProgramData\MediaMop`, not `AppData\Local`.
4. Launch MediaMop from the Start Menu shortcut.
5. Confirm the tray icon appears and the browser opens the app.
6. Confirm first-run user creation appears when no user exists.
7. Attempt a password shorter than 8 characters and confirm it is blocked.
8. Create the first user with a valid password.
9. Confirm the setup wizard opens after first-user creation.
10. Confirm `Skip for now` exits the wizard and can be reopened from Settings.
11. Confirm `Finish setup` saves timezone, display density, backup schedule, and starter module settings.
12. In Settings, confirm setup wizard, timezone, log retention, and display density cards render correctly.
13. Confirm Backup and Restore controls sit consistently at the bottom of their cards.
14. Create a configuration backup.
15. Restore that backup and confirm the app remains usable.
16. Confirm Upgrade shows a meaningful status, even when no update is available.
17. Open Refiner path inputs and use Browse for a local folder.
18. Enter a UNC-style path manually and confirm validation warns without blocking legitimate save paths by design.
19. Confirm Pruner and Subber settings can save required connection/path fields without exposing internal webhook controls.
20. Quit MediaMop from the tray icon.
21. Relaunch MediaMop and confirm the existing user, settings, and wizard completion state persist.
22. Install the next version over the current version and confirm this is treated as an upgrade, not a first-run install.
23. Uninstall and reinstall only when intentionally testing clean-install behavior.

## Docker smoke

Use the published release image, not a locally built image.

1. Pull the versioned image:

   ```bash
   docker pull ghcr.io/jampat000/mediamop:vX.Y.Z
   ```

2. Start with a fresh named volume:

   ```bash
   docker run --rm -p 8788:8788 -v mediamop-smoke:/data/mediamop ghcr.io/jampat000/mediamop:vX.Y.Z
   ```

3. Open `http://localhost:8788/`.
4. Confirm first-run user creation appears.
5. Attempt a password shorter than 8 characters and confirm it is blocked.
6. Create the first user with a valid password.
7. Confirm the setup wizard opens.
8. Complete or skip the setup wizard and confirm Settings can reopen it.
9. Confirm `/health` returns healthy while the container is running.
10. Confirm Activity updates without manual page reload when a module action is triggered.
11. Confirm Logs show application/runtime events, not developer build noise.
12. Confirm Backup and Restore work against the mounted volume.
13. Stop and restart the container with the same volume.
14. Confirm the user, settings, and runtime state persist.
15. Pull and run `latest` and confirm it resolves to the expected release digest.
16. Upgrade from the previous release tag to the new release tag using the same volume.
17. Confirm Docker path wording is clear: paths inside the container may differ from host/NAS paths.
18. Remove the smoke volume only after validation is complete.

## Failure handling

- Any failed smoke step gets a GitHub issue with the install type, version, exact step, expected result, actual result, and screenshots/logs with secrets removed.
- Release-blocking failures get `priority: critical`.
- Core workflow failures without data loss get `priority: high`.
