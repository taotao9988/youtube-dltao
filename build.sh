#!/usr/bin/env bash
set -o errexit

echo "==> 安装 ffmpeg ..."
apt-get update && apt-get install -y ffmpeg

echo "==> ffmpeg 安装完成"
ffmpeg -version
