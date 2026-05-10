#!/usr/bin/env bash
set -e

echo "==> 安装 Python 依赖（含 imageio-ffmpeg，自带 ffmpeg 二进制）..."
pip install -r requirements.txt

echo "==> 验证 ffmpeg 可用 ..."
python -c "import imageio_ffmpeg; print('ffmpeg exe:', imageio_ffmpeg.get_ffmpeg_exe())"

echo "==> 构建完成!"
