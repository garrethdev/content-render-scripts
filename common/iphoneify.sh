#!/bin/zsh
# iphoneify.sh — the approved "v1 subtle" iPhone-look pass for Seedance renders.
# Usage: ./iphoneify.sh input.mp4 [output.mp4]
# Verified recipe (chosen 2026-07-01): 1080x1920/30fps, ~1% off-center + micro
# vibration, mild cool shift (R/B 1.085->1.03), light surviving grain, x264
# tune-grain, Apple metadata.

set -e
IN="$1"
[[ -z "$IN" ]] && { echo "usage: iphoneify.sh input.mp4 [output.mp4]"; exit 1; }
OUT="${2:-${IN:r}_iphone.mp4}"

ffmpeg -y -i "$IN" -vf "scale=1112:1976:flags=lanczos,crop=1080:1920:x='(iw-ow)/2+12+1.5*sin(n/19)':y='(ih-oh)/2+1.2*sin(n/23+0.5)',colorchannelmixer=rr=0.975:gg=1.0:bb=1.03,curves=all='0/0.01 1/0.985',fps=30,noise=alls=9:allf=t+u" \
 -c:v libx264 -crf 18 -preset slow -tune grain -pix_fmt yuv420p -c:a aac -b:a 128k \
 -metadata make="Apple" -metadata model="iPhone 15 Pro" -movflags use_metadata_tags \
 "$OUT" -loglevel error

echo "done: $OUT"
