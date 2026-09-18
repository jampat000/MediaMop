# Third-party notices

Weir bundles or installs the following third-party runtime tools for packaged user installs.

## FFmpeg

Windows builds bundle FFmpeg and ffprobe from the BtbN FFmpeg Builds project. Docker builds install FFmpeg from the Debian package repositories.

FFmpeg is a third-party project and is not owned by Weir. FFmpeg licensing depends on the specific build configuration used by the distributor. Weir's Windows package uses the LGPL-labelled BtbN Windows build archive.

- Project: https://ffmpeg.org/
- Windows build source: https://github.com/BtbN/FFmpeg-Builds
- License information: https://ffmpeg.org/legal.html

## MKVToolNix (mkvmerge)

Windows builds bundle `mkvmerge.exe` from the official MKVToolNix portable Windows archive. Docker builds install MKVToolNix from the Debian/Ubuntu `mkvtoolnix` package. Weir uses mkvmerge to write Matroska output; it is optional, and Weir falls back to FFmpeg wherever it is absent.

MKVToolNix is a third-party project and is not owned by Weir. It is distributed under the GNU General Public License, version 2.

- Project: https://mkvtoolnix.download/
- Windows build source: https://mkvtoolnix.download/windows/releases/
- Source code: https://gitlab.com/mbunkus/mkvtoolnix
- License: https://www.gnu.org/licenses/old-licenses/gpl-2.0.html

## Outfit font

The web app bundles the Outfit typeface locally via the `@fontsource/outfit` package. Outfit is distributed under the SIL Open Font License 1.1.

- Project: https://github.com/Outfitio/Outfit-Fonts
- Package source: https://www.npmjs.com/package/@fontsource/outfit
- License: https://openfontlicense.org/
