import os

content = r"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, sys, json, threading, uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import yt_dlp

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

DOWNLOAD_DIR = Path(__file__).parent / 'downloads'
DOWNLOAD_DIR.mkdir(exist_ok=True)
_COOKIES_SRC = Path(__file__).parent / 'cookies.txt'
tasks = {}

def get_ydl_opts():
    opts = {
        'quiet': False,
        'no_warnings': False,
        'no_check_certificates': True,
        'age_limit': 21,
        'geo_bypass': True,
        'socket_timeout': 60,
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'web_embedded', 'ios', 'android'],
            }
        },
    }
    if _COOKIES_SRC.exists():
        opts['cookiefile'] = str(_COOKIES_SRC)
    return opts

def get_video_info(url):
    opts = get_ydl_opts()
    opts['extract_flat'] = False
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    seen = {}
    for f in info.get('formats', []):
        h = f.get('height') or 0
        vc = f.get('vcodec', 'none')
        if vc == 'none' or h <= 0:
            continue
        key = int(h)
        fs = (f.get('filesize') or f.get('filesize_approx') or 0)
        fps = f.get('fps') or 30
        score = (fps, fs)
        if key not in seen or score > seen[key]['score']:
            seen[key] = {
                'fid': f['format_id'],
                'h': key,
                'ext': f.get('ext', ''),
                'fps': fps,
                'fs': fs,
                'score': score,
            }
    formats = []
    for e in seen.values():
        h = e['h']
        mb = 0
        if e['fs']:
            mb = round(e['fs'] / 1024 / 1024, 1)
        if h >= 2160:
            label = '4K (2160p)'
        elif h >= 1440:
            label = '2K (1440p)'
        elif h >= 1080:
            label = '1080p'
        elif h >= 720:
            label = '720p'
        elif h >= 480:
            label = '480p'
        else:
            label = str(h) + 'p'
        formats.append({
            'format_id': e['fid'],
            'height': h,
            'ext': e['ext'],
            'label': label,
            'size_mb': mb,
            'fps': e['fps'],
        })
    formats.sort(key=lambda x: x['height'], reverse=True)
    formats.append({
        'format_id': 'bestvideo+bestaudio/best',
        'height': 9999,
        'ext': 'mp4',
        'label': 'best auto',
        'size_mb': 0,
        'fps': 60,
    })
    return {
        'title': info.get('title', ''),
        'duration': info.get('duration', 0),
        'thumbnail': info.get('thumbnail', ''),
        'uploader': info.get('uploader', ''),
        'view_count': info.get('view_count', 0),
        'upload_date': info.get('upload_date', ''),
        'formats': formats,
    }

def pick_format(fid):
    try:
        if fid == 'bestvideo+bestaudio/best':
            return 'bestvideo+bestaudio/best'
        if isinstance(fid, str) and fid.isdigit():
            return fid + '+bestaudio/best[height<=' + fid + ']/best'
        h = str(fid).replace('p', '')
        return 'bestvideo[height<=' + h + ']+bestaudio/best[height<=' + h + ']/best'
    except Exception:
        return 'bestvideo+bestaudio/best'

def download_task(tid, url, fid, title):
    tasks[tid]['status'] = 'downloading'
    tasks[tid]['progress'] = 0
    safe = ''.join(c for c in title if c.isalnum() or c in ' -_()[]').strip()[:60]
    if not safe:
        safe = tid
    out = str(DOWNLOAD_DIR / (safe + '_' + tid))
    def hook(d):
        if d['status'] == 'downloading':
            t = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            dl = d.get('downloaded_bytes', 0)
            if t > 0:
                tasks[tid]['progress'] = min(99, int(dl / t * 100))
            tasks[tid]['speed'] = d.get('_speed_str', '')
            tasks[tid]['eta'] = d.get('_eta_str', '')
        elif d['status'] == 'finished':
            tasks[tid]['progress'] = 99
    opts = get_ydl_opts()
    opts.update({
        'format': pick_format(fid),
        'outtmpl': out + '.%(ext)s',
        'progress_hooks': [hook],
        'merge_output_format': 'mp4',
    })
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        f2 = None
        for f in DOWNLOAD_DIR.iterdir():
            if tid in f.name:
                f2 = f
                break
        if f2 and f2.exists():
            tasks[tid] = {
                'status': 'done',
                'progress': 100,
                'speed': '',
                'eta': '',
                'file': str(f2),
                'filename': f2.name,
                'error': None,
            }
        else:
            tasks[tid] = {
                'status': 'error',
                'progress': 0,
                'speed': '',
                'eta': '',
                'file': None,
                'filename': None,
                'error': 'file not found',
            }
    except Exception as e:
        tasks[tid] = {
            'status': 'error',
            'progress': 0,
            'speed': '',
            'eta': '',
            'file': None,
            'filename': None,
            'error': str(e),
        }

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/cookies-status')
def cookies_status():
    return jsonify({'exists': _COOKIES_SRC.exists()})

@app.route('/api/upload-cookies', methods=['POST'])
def upload_cookies():
    if 'file' not in request.files:
        return jsonify({'error': 'no file'}), 400
    f = request.files['file']
    if not f.filename.endswith('.txt'):
        return jsonify({'error': 'need .txt'}), 400
    f.save(str(_COOKIES_SRC))
    return jsonify({'success': True})

@app.route('/api/info', methods=['POST'])
def api_info():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'need url'}), 400
    try:
        info = get_video_info(url)
        return jsonify({'success': True, 'data': info})
    except Exception as e:
        return jsonify({'error': str(e)[:300]}), 500

@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.get_json(force=True, silent=True) or {}
    url = data.get('url', '').strip()
    fid = data.get('format_id', 'bestvideo+bestaudio/best')
    title = data.get('title', 'video')
    if not url:
        return jsonify({'error': 'need url'}), 400
    tid = str(uuid.uuid4())[:8]
    tasks[tid] = {
        'status': 'pending',
        'progress': 0,
        'speed': '',
        'eta': '',
        'file': None,
        'filename': None,
        'error': None,
    }
    t = threading.Thread(target=download_task, args=(tid, url, fid, title), daemon=True)
    t.start()
    return jsonify({'success': True, 'task_id': tid})

@app.route('/api/progress/<tid>')
def api_progress(tid):
    if tid not in tasks:
        return jsonify({'error': 'not found'}), 404
    t = tasks[tid].copy()
    t.pop('file', None)
    return jsonify(t)

@app.route('/api/download-file/<tid>')
def api_file(tid):
    if tid not in tasks or tasks[tid]['status'] != 'done':
        return jsonify({'error': 'not ready'}), 400
    fp = tasks[tid].get('file')
    if not fp or not os.path.exists(fp):
        return jsonify({'error': 'file missing'}), 404
    return send_file(fp, as_attachment=True, download_name=os.path.basename(fp), mimetype='video/mp4')

if __name__ == '__main__':
    print('YouTube DL starting on http://localhost:5050')
    app.run(host='0.0.0.0', port=5050, debug=True, use_reloader=False)
"""

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content.strip() + '\n')

print('app.py written successfully')
