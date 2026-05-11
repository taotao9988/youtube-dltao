#!/usr/bin/env python3
"""
YouTube Video Downloader - Flask Backend
"""

import os
import sys
import io
import time
import shutil
import threading
import tempfile
import platform
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS

# ── yt-dlp ──
import yt_dlp

# ── Invidious 备用服务器列表（定期更新）──
INVIDIOUS_INSTANCES = [
    'https://invidious.tiekoetter.com',
    'https://invidious.kavin.rocks',
    'https://invidious.slipfox.xyz',
    'https://yt.artemislena.eu',
    'https://invidious.private.coffee',
    'https://invidious.protokolla.info',
    'https://invidious.denolet.com',
    'https://inv.nadeko.net',
    'https://yewtu.be',
]

def get_video_info_via_invidious(url):
    """通过 Invidious 获取视频信息（备用方案）"""
    import urllib.request
    import json
    
    # 从 URL 提取视频 ID
    video_id = None
    if 'youtu.be' in url:
        video_id = url.split('/')[-1].split('?')[0]
    elif 'youtube.com' in url:
        import re
        match = re.search(r'[?&]v=([^&]+)', url)
        if match:
            video_id = match.group(1)
    
    if not video_id:
        return None
    
    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f'{instance}/api/v1/videos/{video_id}'
            req = urllib.request.Request(
                api_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                
            # 解析格式信息
            formats = []
            for f in data.get('formatStreams', []):
                height = int(f.get('resolution', '0').replace('p', '') or '0')
                if height > 0:
                    formats.append({
                        'format_id': f.get('itag', str(height)),
                        'height': height,
                        'fps': 30,
                        'label': f'{height}p',
                        'ext': f.get('type', 'video/mp4').split('/')[1].split(';')[0],
                        'size_mb': None,
                        'score': 0,
                    })
            
            # 去重
            seen = set()
            unique_formats = []
            for f in sorted(formats, key=lambda x: x['height'], reverse=True):
                if f['height'] not in seen:
                    seen.add(f['height'])
                    unique_formats.append(f)
            
            return {
                'title': data.get('title', '未知标题'),
                'duration': data.get('lengthSeconds', 0),
                'thumbnail': data.get('thumbnailUrl', ''),
                'uploader': data.get('author', ''),
                'view_count': data.get('viewCount', 0),
                'upload_date': '',
                'description': '',
                'formats': unique_formats,
                'age_limit': 0,
                'is_live': False,
                'source': 'invidious',
            }
        except Exception as e:
            print(f'  ! Invidious {instance} failed: {e}')
            continue
    
    return None

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# ── 全局配置 ──
PORT = int(os.environ.get('PORT', 5050))
BASE_DIR = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / 'downloads'
TEMP_DIR = BASE_DIR / 'temp'
FFMPEG_PATH = BASE_DIR / 'ffmpeg' / 'bin' / 'ffmpeg.exe'

# ── 初始化目录 ──
DOWNLOAD_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)

# ── 多组 User-Agent（轮换使用，提高成功率） ──
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15',
]

# ── 任务存储 ──
tasks = {}

# ── 获取随机 User-Agent ──
def get_random_ua():
    import random
    return random.choice(USER_AGENTS)

# ── 检查 ffmpeg ──
def check_ffmpeg():
    ffmpeg_locations = [
        FFMPEG_PATH,
        Path('ffmpeg/bin/ffmpeg.exe'),
        Path(__file__).parent / 'ffmpeg' / 'bin' / 'ffmpeg.exe',
        shutil.which('ffmpeg') or shutil.which('ffmpeg.exe'),
    ]
    for loc in ffmpeg_locations:
        if loc and (isinstance(loc, Path) and loc.exists() or isinstance(loc, str) and Path(loc).exists()):
            print(f'  ✓ ffmpeg found: {loc}')
            return str(loc)
        elif loc:
            print(f'  ✗ not found: {loc}')
    print('  ! ffmpeg not found — HD merge disabled')
    return None

# ── 获取 yt-dlp 选项（增强版浏览器模拟） ──
def get_ydl_opts():
    opts = {
        'quiet': False,
        'no_warnings': False,
        'no_check_certificates': True,
        'age_limit': 25,  # 提高年龄限制
        'geo_bypass': True,
        'geo_bypass_countries': ['US', 'JP', 'KR', 'CN'],
        'socket_timeout': 60,
        # ── 增强浏览器模拟 ──
        'http_headers': {
            'User-Agent': get_random_ua(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7,ja;q=0.6',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        },
        # ── 多播放器客户端策略 ──
        'extractor_args': {
            'youtube': {
                'player_client': [
                    'web',              # Web 端
                    'web_embedded',     # Web 嵌入式
                    'ios',              # iOS 客户端
                    'android',          # Android 客户端
                ],
                'player_skip': ['configs', 'webpage'],
            }
        },
        'format_sort': [
            'quality', 'res', 'fps', 
            'hdr:12', 'vcodec:avc', 'acodec:mp4a'
        ],
        'ignoreerrors': False,
    }

    # 检查 cookies.txt
    cookies_path = BASE_DIR / 'cookies.txt'
    temp_cookies = None
    
    if cookies_path.exists():
        # 复制到无空格路径
        temp_cookies = TEMP_DIR / 'cookies.txt'
        try:
            shutil.copy2(cookies_path, temp_cookies)
            opts['cookiefile'] = str(temp_cookies)
            print(f'  ✓ cookies loaded')
        except Exception as e:
            print(f'  ! cookies copy failed: {e}')

    # ffmpeg
    ffmpeg = check_ffmpeg()
    if ffmpeg:
        opts['ffmpeg_location'] = ffmpeg

    # deno（可选）
    deno_path = BASE_DIR / 'deno' / 'deno.exe'
    if deno_path.exists():
        opts['extractor_retries'] = 3
        opts['skip_download'] = False

    return opts


def get_video_info(url):
    """获取视频信息"""
    # 首先尝试 yt-dlp（直接方式）
    try:
        opts = get_ydl_opts()
        opts['extract_flat'] = False
        opts['skip_download'] = True

        all_formats = []
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError('No info from yt-dlp')
            
            all_formats = info.get('formats', [])
            
    except Exception as e:
        print(f'  ! yt-dlp failed: {e}')
        print('  → Trying Invidious backup...')
        
        # 备用：通过 Invidious 获取
        inv_info = get_video_info_via_invidious(url)
        if inv_info:
            print('  ✓ Invidious worked!')
            return inv_info
        else:
            print('  ✗ All methods failed')
            return None

    # 整理格式（每个分辨率只保留最好的）
    best = {}
    seen_heights = set()
    
    for f in all_formats:
        height = f.get('height') or 0
        vcodec = f.get('vcodec', 'none')
        acodec = f.get('acodec', 'none')
        
        # 只保留视频（跳过纯音频）
        if vcodec == 'none' or height <= 0:
            continue
            
        # 按 fps 和 filesize 评分
        fps = f.get('fps', 30) or 30
        size = f.get('filesize') or f.get('filesize_approx') or 0
        score = fps * 1000 + (size // (1024 * 1024))
        
        key = (height, f.get('ext'))
        if key not in best or score > best[key]['score']:
            label = f'{height}p'
            if fps >= 60:
                label += f'{fps}'
            best[key] = {
                'format_id': f['format_id'],
                'height': height,
                'fps': fps,
                'label': label,
                'ext': f.get('ext', 'mp4'),
                'size_mb': round(size / (1024 * 1024), 1) if size else None,
                'score': score,
            }
        seen_heights.add(height)

    formats = sorted(best.values(), key=lambda x: x['height'], reverse=True)

    return {
        'title': info.get('title', '未知标题'),
        'duration': info.get('duration', 0),
        'thumbnail': info.get('thumbnail', ''),
        'uploader': info.get('uploader', ''),
        'view_count': info.get('view_count', 0),
        'upload_date': info.get('upload_date', ''),
        'description': (info.get('description') or '')[:200],
        'formats': formats,
        'age_limit': info.get('age_limit', 0),
        'is_live': info.get('is_live', False),
    }


def pick_format(format_id):
    """生成 yt-dlp format 字符串"""
    if not format_id or format_id == 'bestvideo+bestaudio/best':
        return 'bestvideo+bestaudio/best'
    
    # 如果是 'best' 也直接返回
    if format_id == 'best':
        return 'best'
    
    # 如果是纯数字（format_id）
    if isinstance(format_id, str) and format_id.isdigit():
        return f'{format_id}+bestaudio/best'
    
    # 如果是带 p 的分辨率
    if isinstance(format_id, str) and format_id.endswith('p'):
        try:
            height = int(format_id[:-1])
            return f'bestvideo[height<={height}]+bestaudio/best'
        except ValueError:
            pass
    
    # 直接作为 format_id
    return f'{format_id}+bestaudio/best'


def download_task(task_id, url, format_id, title=None):
    """后台下载任务"""
    tasks[task_id]['status'] = 'downloading'
    tasks[task_id]['progress'] = 0
    tasks[task_id]['speed'] = ''
    tasks[task_id]['eta'] = ''

    safe_title = ''.join(c for c in (title or 'video') if c.isalnum() or c in ' -_()[]').strip()[:60]
    output_path = str(DOWNLOAD_DIR / (safe_title + '_' + task_id))
    final_file = None

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
    dl_opts.update({
        'format': fmt,
        'outtmpl': output_path + '.%(ext)s',
        'progress_hooks': [progress_hook],
        'merge_output_format': 'mp4',
    })

    # 如果 yt-dlp 失败，尝试 Invidious 直接下载
    download_success = False
    try:
        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])
        download_success = True
    except Exception as e:
        print(f'  ! yt-dlp download failed: {e}')
        print('  → Trying direct download via Invidious...')
        
        # 尝试从 Invidious 获取直链并下载
        inv_info = get_video_info_via_invidious(url)
        if inv_info and inv_info.get('formats'):
            try:
                import urllib.request
                # 选择最高质量的格式
                best_format = inv_info['formats'][0]  # 已按高度排序
                
                # 这里只是记录，实际下载仍需要 yt-dlp
                # 因为 Invidious 返回的流可能需要特殊处理
                print(f'  ! Invidious direct download not implemented, yt-dlp retry...')
                # 强制重试一次 yt-dlp
                with yt_dlp.YoutubeDL(dl_opts) as ydl:
                    ydl.download([url])
                download_success = True
            except:
                pass

        # 找下载好的文件
        base = Path(output_path)
        for ext in ['mp4', 'mkv', 'webm', 'avi', 'flv', 'mov']:
            f = base.parent / (base.name + f'.{ext}')
            if f.exists():
                final_file = f
                break

        if final_file:
            ext = final_file.suffix.lstrip('.')
            filename = f'{safe_title}.{ext}'
            tasks[task_id]['status'] = 'done'
            tasks[task_id]['file'] = str(final_file)
            tasks[task_id]['filename'] = filename
        else:
            raise FileNotFoundError('No output file found')

    except Exception as e:
        tasks[task_id]['status'] = 'error'
        tasks[task_id]['error'] = str(e)
        print(f'[!] download error: {e}')


# ═══════════════════════════════════════════
# 路由
# ═══════════════════════════════════════════

@app.route('/')
def index():
    return app.send_static_file('index.html')


@app.route('/api/cookies-status')
def cookies_status():
    """检查 cookies 状态"""
    cookies_path = BASE_DIR / 'cookies.txt'
    return jsonify({
        'exists': cookies_path.exists(),
        'message': 'Cookies file found' if cookies_path.exists() else 'No cookies.txt in project root'
    })


@app.route('/api/upload-cookies', methods=['POST'])
def upload_cookies():
    """上传 cookies.txt"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    f = request.files['file']
    if not f.filename.endswith('.txt'):
        return jsonify({'success': False, 'error': 'Only .txt files allowed'}), 400

    cookies_path = BASE_DIR / 'cookies.txt'
    try:
        # 保存到项目根目录
        f.save(str(cookies_path))
        return jsonify({
            'success': True,
            'message': f'Cookies saved! ({os.path.getsize(cookies_path)} bytes)'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/info', methods=['POST'])
def api_info():
    """获取视频信息"""
    # 同时支持 JSON 和 FormData
    if request.is_json:
        data = request.get_json()
        url = data.get('url', '').strip()
    else:
        url = request.form.get('url', '').strip()
    
    if not url:
        return jsonify({'success': False, 'error': 'URL is required'}), 400

    try:
        info = get_video_info(url)
        if not info:
            return jsonify({'success': False, 'error': 'Failed to fetch video info'}), 500
        return jsonify({'success': True, 'data': info})
    except yt_dlp.utils.DownloadError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error: {str(e)}'}), 500


@app.route('/api/download', methods=['POST'])
def api_download():
    """启动下载任务"""
    # 同时支持 JSON 和 FormData
    if request.is_json:
        data = request.get_json()
        url = data.get('url', '').strip()
        format_id = data.get('format_id', 'bestvideo+bestaudio/best')
        title = data.get('title', 'video')
    else:
        url = request.form.get('url', '').strip()
        format_id = request.form.get('format_id', 'bestvideo+bestaudio/best')
        title = request.form.get('title', 'video')

    if not url:
        return jsonify({'error': 'URL is required'}), 400

    task_id = f'{int(time.time() * 1000)}'
    tasks[task_id] = {
        'status': 'pending',
        'progress': 0,
        'url': url,
        'format': format_id,
    }

    thread = threading.Thread(target=download_task, args=(task_id, url, format_id, title))
    thread.daemon = True
    thread.start()

    return jsonify({'task_id': task_id})


@app.route('/api/progress/<task_id>')
def api_progress(task_id):
    """查询下载进度"""
    task = tasks.get(task_id)
    if not task:
        return jsonify({'status': 'not_found', 'error': 'Task not found'}), 404
    return jsonify(task)


@app.route('/api/download-file/<task_id>')
def api_download_file(task_id):
    """下载完成的文件"""
    task = tasks.get(task_id)
    if not task or task['status'] != 'done':
        return jsonify({'error': 'File not ready'}), 404

    filepath = Path(task['file'])
    if not filepath.exists():
        return jsonify({'error': 'File not found'}), 404

    filename = task.get('filename', filepath.name)
    return send_file(
        filepath,
        as_attachment=True,
        download_name=filename,
        mimetype='video/mp4'
    )


# ═══════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════

if __name__ == '__main__':
    print('═' * 50)
    print('  YouTube 视频下载工具已启动')
    print(f'  http://localhost:{PORT}')
    print(f'  cookies.txt: {(BASE_DIR / "cookies.txt").exists()}')
    print(f'  ffmpeg: {"✓" if check_ffmpeg() else "✗"}')
    print('═' * 50)
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
