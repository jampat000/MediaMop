# Smoke Checklists

These checklists define the minimum user-level validation before calling a release ready. Automated CI checks are necessary but not enough; these are the click-through paths that catch packaging and first-run regressions.

## Windows installer smoke

Use the Velopack setup exe from the release being validated.

1. Run the setup exe on a clean Windows user profile or a reset test profile.
2. Confirm application files install under `%LocalAppData%\Weir`.
3. Confirm runtime data is created under `C:\ProgramData\Weir`.
4. Launch Weir from the Start Menu shortcut.
5. Confirm the tray icon appears and the browser opens the app.
6. Confirm first-run user creation appears when no user exists.
7. Attempt a password shorter than 8 characters and confirm it is blocked.
8. Create the first user with a valid password.
9. Confirm the setup wizard opens after first-user creation.
10. Confirm `Skip for now` exits the wizard and can be reopened from Settings.
11. Confirm `Finish setup` saves timezone, display density, and the configuration backup schedule. (There are no "starter module settings" — the wizard saves those three things and nothing else.)
12. In Settings, confirm the reopened setup wizard renders correctly as borderless sections (it lost its card in #592; do not expect card chrome there), and that the timezone, log retention, and display density cards in Settings General render correctly.
13. Confirm Backup and Restore controls sit consistently at the bottom of their cards. (Still card-shaped after the content-language pass on Settings in #599, which applied the redesign sparingly there and left the action cards in Backup and restore alone. Re-verified against `apps/web/src/pages/settings/settings-backup-tab.tsx`, which still uses `mm-card-action-body` / `mm-card-action-footer`.)
14. Create a configuration backup.
15. Restore that backup and confirm the app remains usable.
16. Confirm Upgrade shows a meaningful status, even when no update is available.
17. Right-click the tray icon and confirm `Check for updates` is present and reaches the current release status.
18. Open Processing path inputs and use Browse for a local folder.
19. Enter a UNC-style path manually and confirm validation warns without blocking legitimate save paths by design.
20. Quit Weir from the tray icon.
21. Relaunch Weir and confirm the existing user, settings, and wizard completion state persist.
22. Install the next version over the current version and confirm Velopack applies a delta update cleanly.
23. Uninstall and reinstall only when intentionally testing clean-install behavior.
24. Confirm the automated packaged smoke reports that Processing placed a byte-identical
    pass-through file in the processed tree before removing its watched source.

## Docker smoke

Use the published release image, not a locally built image. The Git tag is `vX.Y.Z`; the image tag
drops the `v`, so `ghcr.io/jampat000/weir:3.0.0` is the image for tag `v3.0.0`.

1. Pull the versioned image:

   ```bash
   docker pull ghcr.io/jampat000/weir:X.Y.Z
   ```

2. Start with a fresh named volume:

   ```bash
   docker run --rm -p 9347:9347 -v weir-smoke:/data/weir ghcr.io/jampat000/weir:X.Y.Z
   ```

3. Open `http://localhost:9347/`.
4. Confirm first-run user creation appears.
5. Confirm the release-candidate audit artifact includes `pass-through-proof.json`
   showing completed, byte-identical delivery and watched-source cleanup through a
   mounted Docker path.
6. Attempt a password shorter than 8 characters and confirm it is blocked.
7. Create the first user with a valid password.
8. Confirm the setup wizard opens.
9. Complete or skip the setup wizard and confirm Settings can reopen it.
10. Confirm `/health` returns healthy while the container is running.
11. Confirm Activity updates without manual page reload when a Processing action is triggered.
12. Confirm Logs show application/runtime events, not developer build noise.
13. Confirm Backup and Restore work against the mounted volume.
14. Stop and restart the container with the same volume.
15. Confirm the user, settings, and runtime state persist.
16. Pull and run `latest` and confirm it resolves to the expected release digest.
17. Upgrade from the previous release tag to the new release tag using the same volume.
18. Confirm Docker path wording is clear: paths inside the container may differ from host/NAS paths.
19. Remove the smoke volume only after validation is complete.

## Failure handling

- Any failed smoke step gets a GitHub issue with the install type, version, exact step, expected result, actual result, and screenshots/logs with secrets removed.
- Release-blocking failures get `priority: critical`.
- Core workflow failures without data loss get `priority: high`.
