#!/usr/bin/env bash
set -e

echo "==> 安装 ffmpeg ..."
apt-get update && apt-get install -y ffmpeg

echo "==> ffmpeg 安装完成"
ffmpeg -version

echo "==> 安装 Python 依赖..."
pip install -r requirements.txt

echo "==> 构建完成!"
