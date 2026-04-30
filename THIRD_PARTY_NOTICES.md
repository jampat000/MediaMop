# Third-party notices

MediaMop bundles or installs the following third-party runtime tools for packaged user installs.

## FFmpeg

Windows builds bundle FFmpeg and ffprobe from the BtbN FFmpeg Builds project. Docker builds install FFmpeg from the Debian package repositories.

FFmpeg is a third-party project and is not owned by MediaMop. FFmpeg licensing depends on the specific build configuration used by the distributor. MediaMop's Windows package uses the LGPL-labelled BtbN Windows build archive.

- Project: https://ffmpeg.org/
- Windows build source: https://github.com/BtbN/FFmpeg-Builds
- License information: https://ffmpeg.org/legal.html

## Outfit font

The web app bundles the Outfit typeface locally via the `@fontsource/outfit` package. Outfit is distributed under the SIL Open Font License 1.1.

- Project: https://github.com/Outfitio/Outfit-Fonts
- Package source: https://www.npmjs.com/package/@fontsource/outfit
- License: https://openfontlicense.org/
