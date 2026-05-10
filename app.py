#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube 视频下载工具 - Flask 后端
支持年龄限制视频（通过上传 cookies.txt）
"""

import os
import json
import threading
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import yt_dlp

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# 强制刷新输出（Windows 上 print 可能会被缓冲）
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(line_buffering=True)

# 兼容本地 Windows 和云端 Linux
import tempfile
if os.environ.get('RENDER'):
    # Render 云端：用 /tmp 目录（ ephemeral，但下载完成后立即发送给用户）
    DOWNLOAD_DIR = Path('/tmp/ytdl_downloads')
else:
    DOWNLOAD_DIR = Path(__file__).parent / 'downloads'
DOWNLOAD_DIR.mkdir(exist_ok=True)

# cookies 源文件路径
_COOKIES_SRC = Path(__file__).parent / 'cookies.txt'


def _get_working_cookies_path():
    """
    返回 yt-dlp 可读取的 cookies 文件路径。
    复制到 C:\yt_cookies.txt（无空格、无短路径问题）。
    """
    if not _COOKIES_SRC.exists():
        return None

    import shutil
    dst = Path('C:/yt_cookies.txt')
    try:
        shutil.copy(str(_COOKIES_SRC), str(dst))
        with open(dst, 'r', encoding='utf-8', errors='ignore') as f:
            first = f.readline()
            if first.startswith('# ') or first.startswith('# Netscape'):
                print('[cookies] C:/yt_cookies.txt', flush=True)
                return str(dst)
            else:
                print('[cookies] 格式异常: ' + first[:30], flush=True)
    except Exception as e:
        print('[cookies] 复制失败: ' + str(e), flush=True)

    return str(_COOKIES_SRC)


def _find_deno():
    """查找 deno 可执行文件，返回路径或 None"""
    import shutil
    deno = shutil.which('deno')
    if deno:
        return deno
    for p in ['C:\\deno\\deno.exe', 'C:\\Tools\\deno\\deno.exe']:
        if os.path.exists(p):
            return p
    return None


def get_ydl_opts():
    """返回通用 yt-dlp 选项"""
    opts = {
        'quiet': False,
        'no_warnings': False,
        'no_check_certificates': True,
        'age_limit': 21,
        'geo_bypass': True,
        'socket_timeout': 60,
    }

    # deno（用于绕过 bot 检测）
    deno_path = _find_deno()
    if deno_path:
        os.environ['YTDLP_JS_RUNTIME'] = deno_path
        os.environ['PATH'] = os.path.dirname(deno_path) + os.pathsep + os.environ.get('PATH', '')
        print('[deno] found: ' + deno_path, flush=True)
    else:
        print('[deno] NOT found - JS challenge may fail', flush=True)

    # cookies
    cookies_path = _get_working_cookies_path()
    if cookies_path and os.path.exists(cookies_path):
        opts['cookiefile'] = cookies_path
        print('[cookies] loaded: ' + cookies_path, flush=True)
    else:
        print('[cookies] 未找到 cookies.txt', flush=True)

    # 强制使用 web 客户端，避免自动降级到 tv/android
    opts['extractor_args'] = {
        'youtube': {
            'player_client': ['web'],
            'player_skip': [],
        }
    }

    return opts


def get_video_info(url):
    """获取视频信息（不下载），返回所有可用清晰度选项"""
    opts = get_ydl_opts()
    opts['extract_flat'] = False
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    all_formats = info.get('formats', [])
    print('[get_video_info] 共 ' + str(len(all_formats)) + ' 个原始格式，开始过滤...', flush=True)

    # 调试：打印前5个格式的详细信息
    for i, f in enumerate(all_formats[:5]):
        print('  fmt[' + str(i) + ']: id=' + str(f.get('format_id')) + ' height=' + str(f.get('height')) + ' vcodec=' + str(f.get('vcodec')), flush=True)

    # 按 (height, fps, filesize) 选每个高度下的最佳格式
    best = {}
    for f in all_formats:
        height = f.get('height') or 0
        vcodec = f.get('vcodec', 'none')
        if vcodec == 'none' or height <= 0:
            continue
        fid = f['format_id']
        filesize = (f.get('filesize') or f.get('filesize_approx') or 0)
        fps = f.get('fps') or 30
        score = (fps, filesize)
        key = int(height)
        if key not in best or score > best[key]['score']:
            best[key] = {
                'format_id': fid,
                'height': key,
                'ext': f.get('ext', ''),
                'fps': fps,
                'filesize': filesize,
                'score': score,
            }

    print('[get_video_info] 去重后 ' + str(len(best)) + ' 个高度', flush=True)

    formats = []
    for entry in best.values():
        h = entry['height']
        fs = entry['filesize']
        size_mb = round(fs / 1024 / 1024, 1) if fs else 0
        if h >= 2160:
            label = '4K (2160p)'
        elif h >= 1440:
            label = '2K (1440p)'
        elif h >= 1080:
            label = '1080p 高清'
        elif h >= 720:
            label = '720p 高清'
        elif h >= 480:
            label = '480p 标清'
        else:
            label = str(h) + 'p'
        formats.append({
            'format_id': entry['format_id'],
            'height': h,
            'ext': entry['ext'],
            'label': label,
            'size_mb': size_mb,
            'fps': entry['fps'],
        })

    formats.sort(key=lambda x: x['height'], reverse=True)

    # 强制追加 1080p 和 720p（如果尚未存在），确保前端始终显示这两个选项
    existing_heights = {f['height'] for f in formats}
    forced = []
    if 1080 not in existing_heights:
        forced.append({'height': 1080, 'label': '1080p 高清', 'format_id': '1080p'})
    if 720 not in existing_heights:
        forced.append({'height': 720, 'label': '720p 高清', 'format_id': '720p'})
    # 按高度倒序插入到正确位置
    for entry in forced:
        formats.append({
            'format_id': entry['format_id'],
            'height': entry['height'],
            'ext': 'mp4',
            'label': entry['label'],
            'size_mb': 0,
            'fps': 30,
        })
    formats.sort(key=lambda x: x['height'], reverse=True)

    # 附加「最佳质量」选项
    formats.append({
        'format_id': 'bestvideo+bestaudio/best',
        'height': 9999,
        'ext': 'mp4',
        'label': '最佳质量（自动）',
        'size_mb': 0,
        'fps': 60,
    })

    print('[get_video_info] 返回 ' + str(len(formats)) + ' 个选项', flush=True)
    return {
        'title': info.get('title', '未知标题'),
        'duration': info.get('duration', 0),
        'thumbnail': info.get('thumbnail', ''),
        'uploader': info.get('uploader', '未知'),
        'view_count': info.get('view_count', 0),
        'upload_date': info.get('upload_date', ''),
        'formats': formats,
    }


def pick_format(format_id):
    """根据前端传来的 format_id 生成 yt-dlp format 字符串
    始终用 /best 兜底，确保格式不存在时自动降级到可用格式
    """
    try:
        if format_id == 'bestvideo+bestaudio/best':
            return 'bestvideo+bestaudio/best'
        if isinstance(format_id, str) and format_id.isdigit():
            # 纯数字 format_id（如 '137'），直接用作 yt-dlp format 选择器
            return format_id + '+bestaudio/best'
        # 处理 '1080p'、'720p' 等格式
        s = str(format_id).replace('p', '').replace('K', '')
        # 处理 '4K' → 2160
        if '4' in str(format_id) and 'K' in str(format_id):
            height = 2160
        else:
            height = int(s)
        # 用 /best 兜底，格式不存在时自动降级
        return 'bestvideo[height<=' + str(height) + ']+bestaudio/best[height<=' + str(height) + ']/bestvideo+bestaudio/best'
    except (ValueError, TypeError):
        return 'bestvideo+bestaudio/best'


def download_task(task_id, url, format_id, title):
    """后台下载任务"""
    tasks[task_id]['status'] = 'downloading'
    tasks[task_id]['progress'] = 0

    safe_title = ''.join(c for c in title if c.isalnum() or c in ' -_()[]').strip()[:60]
    if not safe_title:
        safe_title = task_id

    output_path = str(DOWNLOAD_DIR / (safe_title + '_' + task_id))

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                pct = min(99, int(downloaded / total * 100))
                tasks[task_id]['progress'] = pct
            tasks[task_id]['speed'] = d.get('_speed_str', '')
            tasks[task_id]['eta'] = d.get('_eta_str', '')
        elif d['status'] == 'finished':
            tasks[task_id]['progress'] = 99

    dl_opts = get_ydl_opts()
    fmt = pick_format(format_id)
    print('[download] format=' + fmt, flush=True)
    dl_opts.update({
        'format': fmt,
        'outtmpl': output_path + '.%(ext)s',
        'progress_hooks': [progress_hook],
        'merge_output_format': 'mp4',
    })

    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])
            final_file = None
            for f in DOWNLOAD_DIR.iterdir():
                if f.stem.startswith(safe_title + '_' + task_id):
                    final_file = f
                    break
            if not final_file:
                for f in DOWNLOAD_DIR.iterdir():
                    if task_id in f.name:
                        final_file = f
                        break
            if final_file and final_file.exists():
                tasks[task_id]['status'] = 'done'
                tasks[task_id]['progress'] = 100
                tasks[task_id]['file'] = str(final_file)
                tasks[task_id]['filename'] = final_file.name
                print('[下载完成] ' + final_file.name, flush=True)
            else:
                tasks[task_id]['status'] = 'error'
                tasks[task_id]['error'] = '下载完成但未找到文件'
    except Exception as e:
        err = str(e)
        print('[下载失败] ' + err, flush=True)
        tasks[task_id]['status'] = 'error'
        tasks[task_id]['error'] = err


tasks = {}


# ── 路由 ─────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/cookies-status')
def api_cookies_status():
    return jsonify({'exists': _COOKIES_SRC.exists(), 'path': str(_COOKIES_SRC)})


@app.route('/api/upload-cookies', methods=['POST'])
def api_upload_cookies():
    if 'file' not in request.files:
        return jsonify({'error': '未收到文件'}), 400
    file = request.files['file']
    if not file.filename.endswith('.txt'):
        return jsonify({'error': '请上传 .txt 格式文件'}), 400
    try:
        file.save(str(_COOKIES_SRC))
        with open(_COOKIES_SRC, 'r', encoding='utf-8', errors='ignore') as f:
            if not f.readline().startswith('# '):
                return jsonify({'error': 'cookies.txt 格式不正确，请用浏览器扩展重新导出'}), 400
        return jsonify({'success': True, 'message': 'cookies 已上传！'})
    except Exception as e:
        return jsonify({'error': '保存失败：' + str(e)}), 500


@app.route('/api/info', methods=['POST'])
def api_get_info():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': '请输入视频链接'}), 400
    if 'youtube.com' not in url and 'youtu.be' not in url:
        return jsonify({'error': '请输入有效的 YouTube 链接'}), 400
    try:
        info = get_video_info(url)
        return jsonify({'success': True, 'data': info})
    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        print('[DownloadError] ' + err, flush=True)
        keywords = ['sign in', 'login', 'age', 'restricted', 'bot']
        if any(k in err.lower() for k in keywords):
            msg = 'YouTube 验证失败，请上传浏览器 cookies.txt（点击「上传 Cookies」按钮）。'
            return jsonify({'error': msg}), 400
        elif any(k in err.lower() for k in ['unavailable', 'removed', 'private']):
            return jsonify({'error': '该视频不可用、已删除或为私人视频'}), 400
        else:
            return jsonify({'error': '获取视频信息失败：' + err[:200]}), 500
    except Exception as e:
        print('[api_get_info 异常] ' + str(e), flush=True)
        return jsonify({'error': '服务器错误：' + str(e)[:200]}), 500


@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url', '').strip()
    format_id = data.get('format_id', 'bestvideo+bestaudio/best')
    title = data.get('title', 'video')

    if not url:
        return jsonify({'error': '请输入视频链接'}), 400

    task_id = str(uuid.uuid4())[:8]
    tasks[task_id] = {
        'status': 'pending', 'progress': 0,
        'speed': '', 'eta': '',
        'file': None, 'filename': None, 'error': None,
    }
    t = threading.Thread(target=download_task, args=(task_id, url, format_id, title), daemon=True)
    t.start()
    return jsonify({'success': True, 'task_id': task_id})


@app.route('/api/progress/<task_id>')
def api_progress(task_id):
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    task = tasks[task_id].copy()
    task.pop('file', None)
    return jsonify(task)


@app.route('/api/download-file/<task_id>')
def api_download_file(task_id):
    if task_id not in tasks:
        return jsonify({'error': '任务不存在'}), 404
    task = tasks[task_id]
    if task['status'] != 'done':
        return jsonify({'error': '文件尚未准备好'}), 400
    file_path = task.get('file')
    if not file_path or not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404
    return send_file(file_path, as_attachment=True,
                     download_name=os.path.basename(file_path),
                     mimetype='video/mp4')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    print('=' * 50, flush=True)
    print('  YouTube 视频下载工具已启动', flush=True)
    print('  http://localhost:' + str(port), flush=True)
    print('  yt-dlp: ' + yt_dlp.version.__version__, flush=True)
    print('  cookies.txt:', _COOKIES_SRC.exists(), flush=True)
    print('  RENDER env:', os.environ.get('RENDER', 'not set'), flush=True)
    print('=' * 50, flush=True)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
