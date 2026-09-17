#!/usr/bin/env bash
# Issue #503 trial: generates a throwaway corpus of ~15 synthetic MKV files with ffmpeg's
# `-f lavfi` sources, used to compare Weir's ffmpeg remux argv against an equivalent mkvmerge
# command line. Nothing this script writes is committed: point it at a scratch directory.
#
# Usage: generate-corpus.sh <ffmpeg-dir> <out-dir>
#   <ffmpeg-dir>  directory containing ffmpeg.exe (or ffmpeg on non-Windows)
#   <out-dir>     directory to write the corpus into (created if missing)
#
# What is and is not achievable with this ffmpeg build is documented in
# docs/trials/503-mkvmerge-vs-ffmpeg.md ("Corpus and gaps"). In short, this build has
# --disable-libx264 --disable-libx265: there is no software H.264/HEVC encoder with 10-bit
# support, so true HEVC 10-bit + HDR10 static metadata (mastering display / MaxCLL SEI),
# Dolby Vision RPUs, TrueHD Atmos objects and PGS bitmap subtitles cannot be synthesized here.
# Every file below is 8-bit, and HDR is approximated with BT.2020/PQ colorimetry tags only
# (see file 03).
set -euo pipefail

FFDIR="${1:?usage: generate-corpus.sh <ffmpeg-dir> <out-dir>}"
OUT="${2:?usage: generate-corpus.sh <ffmpeg-dir> <out-dir>}"
FF="$FFDIR/ffmpeg.exe"
[ -x "$FF" ] || FF="$FFDIR/ffmpeg"

mkdir -p "$OUT"
FM="$OUT/.chapters.ffmeta"
FONT_DIR="$OUT/.fonts"
mkdir -p "$FONT_DIR"

# A tiny embeddable font attachment. Rather than depend on a system font being present (and its
# licence), synthesize a minimal but structurally valid SFNT/TTF so libass and the mkvmerge
# attachment path both have a real font file to carry. If a system font is easier to find, prefer
# it; this exists so the script has no external dependency.
FONT_FILE="$FONT_DIR/TrialFont.ttf"
python3 - "$FONT_FILE" <<'PY' 2>/dev/null || true
import struct, sys
path = sys.argv[1]
# A near-empty but well-formed sfnt: header + one required table (no glyphs needed for our purpose,
# this file only has to survive as a Matroska attachment, not actually render text).
tables = {}
data = b"\x00" * 4
tables[b"head"] = data
num_tables = len(tables)
entries = b""
offset = 12 + 16 * num_tables
body = b""
for tag, tdata in tables.items():
    entries += struct.pack(">4sIII", tag, 0, offset, len(tdata))
    body += tdata
    offset += len(tdata)
header = struct.pack(">IHHHH", 0x00010000, num_tables, 0, 0, 0)
with open(path, "wb") as fh:
    fh.write(header + entries + body)
PY
[ -f "$FONT_FILE" ] || printf 'not a real font, placeholder attachment only' > "$FONT_FILE"

srt() {
  cat <<'EOF'
1
00:00:00,000 --> 00:00:00,900
Trial subtitle line one

2
00:00:01,000 --> 00:00:01,900
Trial subtitle line two
EOF
}

ass() {
  cat <<EOF
[Script Info]
ScriptType: v4.00+
PlayResX: 384
PlayResY: 288

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,TrialFont,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:00.90,Default,,0,0,0,,Trial ASS line one
Dialogue: 0,0:00:01.00,0:00:01.90,Default,,0,0,0,,Trial ASS line two
EOF
}

srt > "$OUT/.sub.srt"
ass > "$OUT/.sub.ass"

echo "Generating corpus into $OUT"

# 1. H.264 (libopenh264) + AAC(eng, default) + AC-3(eng, commentary) + SRT(eng) + ASS(eng, forced) with attached font.
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=4:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=440:duration=4" -f lavfi -i "sine=frequency=220:duration=4" \
  -i "$OUT/.sub.srt" -i "$OUT/.sub.ass" \
  -map 0 -map 1 -map 2 -map 3 -map 4 \
  -c:v libopenh264 -pix_fmt yuv420p -c:a:0 aac -c:a:1 ac3 -c:s srt -c:s:1 ass \
  -attach "$FONT_FILE" -metadata:s:t:0 mimetype=font/ttf -metadata:s:t:0 filename=TrialFont.ttf \
  -metadata:s:a:0 language=eng -metadata:s:a:0 title="English" \
  -metadata:s:a:1 language=eng -metadata:s:a:1 title="Commentary" -disposition:a:1 comment \
  -metadata:s:s:0 language=eng -metadata:s:s:1 language=eng -disposition:s:1 forced \
  "$OUT/01_h264_multi_audio_ass_font.mkv"

# 2. HEVC 8-bit (libkvazaar) + AC-3(eng) + E-AC-3(jpn), no subs.
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc2=duration=4:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=300:duration=4" -f lavfi -i "sine=frequency=600:duration=4" \
  -map 0 -map 1 -map 2 -c:v libkvazaar -c:a:0 ac3 -c:a:1 eac3 \
  -metadata:s:a:0 language=eng -metadata:s:a:1 language=jpn \
  "$OUT/02_hevc8_ac3_eac3.mkv"

# 3. HEVC 8-bit tagged BT.2020/PQ colorimetry (closest achievable approximation of HDR10; no
#    mastering-display/MaxCLL static metadata SEI possible without x265 or hdr10plus_tool/dovi_tool)
#    + TrueHD(experimental encoder, no Atmos objects) + AC-3 fallback + chapters.
cat > "$FM" <<'EOF'
;FFMETADATA1
[CHAPTER]
TIMEBASE=1/1000
START=0
END=2000
title=Chapter One
[CHAPTER]
TIMEBASE=1/1000
START=2000
END=4000
title=Chapter Two
EOF
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc2=duration=4:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=500:duration=4" -f lavfi -i "sine=frequency=750:duration=4" \
  -i "$FM" -map_metadata 3 -map_chapters 3 -map 0 -map 1 -map 2 \
  -c:v libkvazaar -bsf:v hevc_metadata=colour_primaries=9:transfer_characteristics=16:matrix_coefficients=9 \
  -strict -2 -c:a:0 truehd -c:a:1 ac3 \
  -metadata:s:a:0 language=eng -metadata:s:a:1 language=eng \
  "$OUT/03_hevc8_hdr_tag_truehd_chapters.mkv"

# 4. H.264 + DTS(experimental)/FLAC/AAC three audio tracks, different languages/default/forced.
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=4:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=350:duration=4" -f lavfi -i "sine=frequency=450:duration=4" \
  -f lavfi -i "sine=frequency=550:duration=4" \
  -map 0 -map 1 -map 2 -map 3 -c:v libopenh264 -pix_fmt yuv420p \
  -strict -2 -c:a:0 dts -c:a:1 flac -c:a:2 aac \
  -metadata:s:a:0 language=eng -metadata:s:a:1 language=fre -metadata:s:a:2 language=spa \
  -disposition:a:0 default -disposition:a:1 0 -disposition:a:2 0 \
  "$OUT/04_dts_flac_aac_multi_lang.mkv"

# 5. H.264 + AAC + ASS with attached font + SRT.
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=3:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=440:duration=3" -i "$OUT/.sub.ass" -i "$OUT/.sub.srt" \
  -map 0 -map 1 -map 2 -map 3 -c:v libopenh264 -pix_fmt yuv420p -c:a aac -c:s ass -c:s:1 srt \
  -attach "$FONT_FILE" -metadata:s:t:0 mimetype=font/ttf -metadata:s:t:0 filename=TrialFont.ttf \
  -metadata:s:a:0 language=eng -metadata:s:s:0 language=eng -metadata:s:s:1 language=eng \
  "$OUT/05_ass_font_srt.mkv"

# 6. Chapters only, single edition (ffmpeg's CLI has no way to write a second Matroska edition or
#    ordered chapters; see docs/trials write-up).
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=4:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=440:duration=4" -i "$FM" -map_metadata 2 -map_chapters 2 \
  -map 0 -map 1 -c:v libopenh264 -pix_fmt yuv420p -c:a aac -metadata:s:a:0 language=eng \
  "$OUT/06_chapters_single_edition.mkv"

# 7. VFR: concatenate two segments encoded at different frame rates without forcing CFR, so the
#    Matroska block timestamps are genuinely variable (an approximation of mixed telecine/anime).
SEGA="$OUT/.vfr_a.mkv"; SEGB="$OUT/.vfr_b.mkv"
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=2:size=640x360:rate=24000/1001" \
  -c:v libopenh264 -pix_fmt yuv420p -an "$SEGA"
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=2:size=640x360:rate=30" \
  -c:v libopenh264 -pix_fmt yuv420p -an "$SEGB"
printf "file '%s'\nfile '%s'\n" "$SEGA" "$SEGB" > "$OUT/.vfr_concat.txt"
"$FF" -hide_banner -loglevel error -y -f concat -safe 0 -i "$OUT/.vfr_concat.txt" \
  -f lavfi -i "sine=frequency=440:duration=4" -map 0:v -map 1:a -fps_mode vfr -c:v copy -c:a aac \
  -metadata:s:a:0 language=eng "$OUT/07_vfr_video.mkv"

# 8. Long-duration, sparse (1 fps) file: exercises duration/timestamp handling without a huge file.
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=5400:size=320x240:rate=1" \
  -f lavfi -i "sine=frequency=440:duration=5400" -map 0 -map 1 \
  -c:v libopenh264 -pix_fmt yuv420p -c:a aac -metadata:s:a:0 language=eng \
  "$OUT/08_long_sparse_90min.mkv"

# 9. Four audio tracks + three subtitle tracks exercising the full default/forced/commentary matrix.
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=4:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=300:duration=4" -f lavfi -i "sine=frequency=400:duration=4" \
  -f lavfi -i "sine=frequency=500:duration=4" -f lavfi -i "sine=frequency=600:duration=4" \
  -i "$OUT/.sub.srt" -i "$OUT/.sub.srt" -i "$OUT/.sub.ass" \
  -map 0 -map 1 -map 2 -map 3 -map 4 -map 5 -map 6 -map 7 \
  -c:v libopenh264 -pix_fmt yuv420p -c:a aac -c:s srt -c:s:2 ass \
  -metadata:s:a:0 language=eng -disposition:a:0 default \
  -metadata:s:a:1 language=jpn -metadata:s:a:1 title="Japanese" \
  -metadata:s:a:2 language=fre -metadata:s:a:2 title="Commentary" -disposition:a:2 comment \
  -metadata:s:a:3 language=spa -metadata:s:a:3 title="Audio Description" -disposition:a:3 descriptions \
  -metadata:s:s:0 language=eng -disposition:s:0 default \
  -metadata:s:s:1 language=spa -disposition:s:1 forced \
  -metadata:s:s:2 language=jpn \
  "$OUT/09_multi_lang_flags.mkv"

# 10. Two font attachments referenced by ASS.
"$FONT_FILE" > /dev/null 2>&1 || true
FONT_FILE2="$FONT_DIR/TrialFont2.ttf"
cp "$FONT_FILE" "$FONT_FILE2"
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=3:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=440:duration=3" -i "$OUT/.sub.ass" \
  -map 0 -map 1 -map 2 -c:v libopenh264 -pix_fmt yuv420p -c:a aac -c:s ass \
  -attach "$FONT_FILE" -metadata:s:t:0 mimetype=font/ttf -metadata:s:t:0 filename=TrialFont.ttf \
  -attach "$FONT_FILE2" -metadata:s:t:1 mimetype=font/ttf -metadata:s:t:1 filename=TrialFont2.ttf \
  -metadata:s:a:0 language=eng "$OUT/10_two_font_attachments.mkv"

# 11. Forced+default subtitle combinations, including a name that should read as hearing-impaired
#     (issue #495's TrackFlagsReader.Detect looks at track names for this).
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=3:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=440:duration=3" -i "$OUT/.sub.srt" -i "$OUT/.sub.srt" \
  -map 0 -map 1 -map 2 -map 3 -c:v libopenh264 -pix_fmt yuv420p -c:a aac -c:s srt -c:s:1 srt \
  -metadata:s:a:0 language=eng \
  -metadata:s:s:0 language=eng -metadata:s:s:0 title="English [SDH]" \
  -metadata:s:s:1 language=eng -metadata:s:s:1 title="Forced" -disposition:s:1 forced+default \
  "$OUT/11_sdh_forced_default_subs.mkv"

# 12. Deliberately truncated Matroska (the #494/#539 shape: full header duration, half the bytes).
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=4:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=440:duration=4" -map 0 -map 1 -c:v libopenh264 -pix_fmt yuv420p -c:a aac \
  "$OUT/.trunc_source.mkv"
SIZE=$(stat -c%s "$OUT/.trunc_source.mkv" 2>/dev/null || stat -f%z "$OUT/.trunc_source.mkv")
HALF=$((SIZE / 2))
head -c "$HALF" "$OUT/.trunc_source.mkv" > "$OUT/12_truncated.mkv"

# 13. 5.1 AC-3 vs stereo AAC, to compare channel-layout/channel-count reporting.
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=3:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=440:duration=3" -f lavfi -i "sine=frequency=440:duration=3" \
  -filter_complex "[1:a]pan=5.1|FL=c0|FR=c0|FC=c0|LFE=c0|BL=c0|BR=c0[a51]" \
  -map 0:v -map "[a51]" -map 2:a \
  -c:v libopenh264 -pix_fmt yuv420p -c:a:0 ac3 -c:a:1 aac \
  -metadata:s:a:0 language=eng -metadata:s:a:0 title="5.1" \
  -metadata:s:a:1 language=eng -metadata:s:a:1 title="Stereo" \
  "$OUT/13_surround_vs_stereo.mkv"

# 14. Embedded poster/thumbnail (mjpeg attached_pic) alongside real video, testing image-stream
#     detection (MetadataStreams.IsImageStream / RemoveImages).
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=3:size=640x360:rate=24" \
  -f lavfi -i "color=c=blue:s=64x64:d=1" -f lavfi -i "sine=frequency=440:duration=3" \
  -map 0:v -map 1:v -map 2:a -c:v:0 libopenh264 -pix_fmt yuv420p -c:v:1 mjpeg \
  -disposition:v:1 attached_pic -c:a aac -metadata:s:a:0 language=eng \
  "$OUT/14_embedded_poster.mkv"

# 15. WebVTT-style plain text subtitle track alongside SRT, to compare text-subtitle handling
#     between the two muxers (mkvmerge maps WebVTT to S_TEXT/WEBVTT; ffmpeg keeps its own).
"$FF" -hide_banner -loglevel error -y -f lavfi -i "testsrc=duration=3:size=640x360:rate=24" \
  -f lavfi -i "sine=frequency=440:duration=3" -i "$OUT/.sub.srt" -i "$OUT/.sub.srt" \
  -map 0 -map 1 -map 2 -map 3 -c:v libopenh264 -pix_fmt yuv420p -c:a aac -c:s webvtt -c:s:1 srt \
  -metadata:s:a:0 language=eng -metadata:s:s:0 language=eng -metadata:s:s:1 language=fre \
  "$OUT/15_webvtt_and_srt.mkv"

rm -f "$SEGA" "$SEGB" "$OUT/.vfr_concat.txt" "$OUT/.trunc_source.mkv"
echo "Done. Files:"
ls -la "$OUT"/*.mkv
