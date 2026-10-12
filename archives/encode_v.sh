#!/bin/bash
# Encodage H.264 deux passes d'images PNG verticales + audio WAV.
# usage : encode_v.sh DOSSIER_IMAGES AUDIO.wav SORTIE.mp4 DEBIT_VIDEO_KBPS
set -e
FR=$1; AU=$2; OUT=$3; VB=$4
P="aq-mode=3:aq-strength=0.85:deblock=-1,-1:psy-rd=1.00,0.10:keyint=60:min-keyint=6:rc-lookahead=60"
VF="scale=out_color_matrix=bt709:out_range=tv,format=yuv420p"
WD=$(dirname "$OUT")
cd "$WD"
ffmpeg -y -hide_banner -loglevel error -framerate 30 -i "$FR/f_%04d.png" -vf "$VF" \
  -c:v libx264 -profile:v high -preset slow -b:v ${VB}k -x264-params "$P" \
  -pass 1 -passlogfile x264v -an -f mp4 /dev/null
ffmpeg -y -hide_banner -loglevel error -framerate 30 -i "$FR/f_%04d.png" -i "$AU" -map 0:v -map 1:a -vf "$VF" \
  -c:v libx264 -profile:v high -preset slow -b:v ${VB}k -x264-params "$P" \
  -pass 2 -passlogfile x264v \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 160k -ar 48000 -movflags +faststart -shortest "$OUT"
rm -f x264v*.log x264v*.mbtree
ls -la "$OUT"
