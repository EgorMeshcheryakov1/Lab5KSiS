#!/usr/bin/env python3
"""
Запуск:
  python app.py

Тестирование curl:
  curl -X PUT http://localhost:5000/docs/hello.txt -d "Hello, World!"
  curl http://localhost:5000/docs/hello.txt
  curl -H "Accept: application/json" http://localhost:5000/docs/
  curl -I http://localhost:5000/docs/hello.txt
  curl -X DELETE http://localhost:5000/docs/hello.txt
  curl -X PUT http://localhost:5000/docs/copy.txt -H "X-Copy-From: /docs/hello.txt"
"""
import os
import logging
from http import HTTPStatus
import shutil
import json
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, Response, send_file, jsonify, render_template_string
STORAGE_ROOT = Path(os.environ.get('STORAGE_ROOT', './storage')).resolve()
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
app = Flask(__name__)
import logging
from http import HTTPStatus
DIR_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Каталог: /{{ path }}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #f5f7fa; color: #333; }
    .container { max-width: 900px; margin: 40px auto; padding: 0 20px; }
    h1 { font-size: 1.4rem; font-weight: 600; margin-bottom: 4px; color: #1a1a2e; }
    .breadcrumb { font-size: 0.85rem; color: #888; margin-bottom: 24px; }
    .breadcrumb a { color: #4a6fa5; text-decoration: none; }
    .breadcrumb a:hover { text-decoration: underline; }
    .card { background: #fff; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,.08); overflow: hidden; }
    table { width: 100%; border-collapse: collapse; }
    th { background: #f0f4ff; font-size: 0.78rem; text-transform: uppercase;
         letter-spacing: .05em; color: #666; padding: 10px 16px; text-align: left; }
    td { padding: 11px 16px; font-size: 0.92rem; border-top: 1px solid #f0f0f0; vertical-align: middle; }
    tr:hover td { background: #fafbff; }
    .icon { margin-right: 8px; }
    a { color: #4a6fa5; text-decoration: none; }
    a:hover { text-decoration: underline; }
    .size { color: #888; }
    .date { color: #aaa; font-size: 0.82rem; white-space: nowrap; }
    .empty { padding: 32px; text-align: center; color: #bbb; font-size: 0.95rem; }
    .badge { display: inline-block; font-size: 0.7rem; padding: 2px 7px;
             border-radius: 10px; font-weight: 600; }
    .badge-dir  { background: #e8f0fe; color: #3c6fd4; }
    .badge-file { background: #e8f8e8; color: #2e7d32; }
  </style>
</head>
<body>
<div class="container">
  <h1>📁 /{{ path if path else '(корень)' }}</h1>
  <div class="breadcrumb">
    {% set parts = path.split('/') if path else [] %}
    <a href="/">Хранилище</a>
    {% set ns = namespace(acc='') %}
    {% for part in parts %}
      {% if part %}
        {% set ns.acc = ns.acc + '/' + part %}
        &nbsp;/&nbsp;<a href="{{ ns.acc }}/">{{ part }}</a>
      {% endif %}
    {% endfor %}
  </div>
  <div class="card">
    {% if entries %}
    <table>
      <thead>
        <tr>
          <th>Имя</th>
          <th>Тип</th>
          <th>Размер</th>
          <th>Изменён</th>
        </tr>
      </thead>
      <tbody>
        {% if path %}
        <tr>
          <td><a href="../">⬆ ..</a></td>
          <td></td><td></td><td></td>
        </tr>
        {% endif %}
        {% for e in entries %}
        <tr>
          <td>
            {% if e.type == 'directory' %}
              <span class="icon">📂</span><a href="{{ e.name }}/">{{ e.name }}</a>
            {% else %}
              <span class="icon">📄</span><a href="{{ e.name }}">{{ e.name }}</a>
            {% endif %}
          </td>
          <td>
            {% if e.type == 'directory' %}
              <span class="badge badge-dir">каталог</span>
            {% else %}
              <span class="badge badge-file">файл</span>
            {% endif %}
          </td>
          <td class="size">
            {% if e.type == 'file' %}{{ e.size | filesizeformat }}{% endif %}
          </td>
          <td class="date">{{ e.modified }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty">Каталог пуст</div>
    {% endif %}
  </div>
</div>
</body>
</html>
"""
def resolve_path(url_path: str) -> Path:
    clean = url_path.lstrip('/')
    full = (STORAGE_ROOT / clean).resolve()
    if not str(full).startswith(str(STORAGE_ROOT)):
        return None
    return full

def format_datetime(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime('%a, %d %b %Y %H:%M:%S GMT')

def format_datetime_iso(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

def format_datetime_human(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime('%d.%m.%Y %H:%M')

def filesizeformat(value):
    for unit in ('Б', 'КБ', 'МБ', 'ГБ', 'ТБ'):
        if abs(value) < 1024.0:
            return f'{value:3.1f} {unit}'
        value /= 1024.0
    return f'{value:.1f} ПБ'
app.jinja_env.filters['filesizeformat'] = filesizeformat

def get_dir_entries(dir_path: Path) -> list:
    entries = []
    for item in sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name)):
        stat = item.stat()
        entry = {'name': item.name, 'type': 'directory' if item.is_dir() else 'file', 'modified': format_datetime_iso(stat.st_mtime)}
        if item.is_file():
            entry['size'] = stat.st_size
        entries.append(entry)
    return entries

def get_dir_entries_html(dir_path: Path) -> list:
    entries = []
    for item in sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name)):
        stat = item.stat()
        entry = {'name': item.name, 'type': 'directory' if item.is_dir() else 'file', 'modified': format_datetime_human(stat.st_mtime)}
        if item.is_file():
            entry['size'] = stat.st_size
        else:
            entry['size'] = 0
        entries.append(entry)
    return entries
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.after_request
def log_request(response):
    try:
        phrase = HTTPStatus(response.status_code).phrase
    except ValueError:
        phrase = 'Unknown'
    now = datetime.now().strftime('%d/%b/%Y %H:%M:%S')
    protocol = request.environ.get('SERVER_PROTOCOL', 'HTTP/1.1')
    print(f'[{now}] "{request.method} {request.path} {protocol}" {response.status_code} - {phrase}')
    return response

@app.route('/', defaults={'url_path': ''}, methods=['GET', 'PUT', 'DELETE', 'HEAD'])
@app.route('/<path:url_path>', methods=['GET', 'PUT', 'DELETE', 'HEAD'])
def storage_handler(url_path):
    fs_path = resolve_path(url_path)
    if fs_path is None:
        return (jsonify({'error': 'Недопустимый путь (выход за пределы хранилища)'}), 400)
    method = request.method.upper()
    if method == 'PUT':
        return handle_put(url_path, fs_path)
    elif method == 'GET':
        return handle_get(url_path, fs_path)
    elif method == 'HEAD':
        return handle_head(url_path, fs_path)
    elif method == 'DELETE':
        return handle_delete(url_path, fs_path)
    else:
        return (jsonify({'error': f'Метод {method} не поддерживается'}), 405)

def handle_put(url_path: str, fs_path: Path):
    copy_from = request.headers.get('X-Copy-From')
    if copy_from:
        src_path = resolve_path(copy_from)
        if src_path is None:
            return (jsonify({'error': 'Недопустимый путь источника X-Copy-From'}), 400)
        if not src_path.exists():
            return (jsonify({'error': f'Файл источника не найден: {copy_from}'}), 404)
        if src_path.is_dir():
            return (jsonify({'error': 'X-Copy-From должен указывать на файл, а не на каталог'}), 400)
        fs_path.parent.mkdir(parents=True, exist_ok=True)
        existed = fs_path.exists()
        shutil.copy2(src_path, fs_path)
        status = 200 if existed else 201
        return (jsonify({'message': 'Файл скопирован', 'source': copy_from, 'destination': f'/{url_path}', 'size': fs_path.stat().st_size}), status)
    else:
        if url_path.endswith('/'):
            return (jsonify({'error': "Нельзя записать файл по пути, заканчивающемуся на '/'"}), 400)
        fs_path.parent.mkdir(parents=True, exist_ok=True)
        if fs_path.is_dir():
            return (jsonify({'error': 'По указанному пути уже существует каталог'}), 409)
        existed = fs_path.exists()
        data = request.get_data()
        with open(fs_path, 'wb') as f:
            f.write(data)
        status = 200 if existed else 201
        return (jsonify({'message': 'Файл обновлён' if existed else 'Файл создан', 'path': f'/{url_path}', 'size': len(data)}), status)

def handle_get(url_path: str, fs_path: Path):
    if not fs_path.exists():
        return (jsonify({'error': f'Путь не найден: /{url_path}'}), 404)
    if fs_path.is_file():
        return send_file(fs_path, as_attachment=False)
    accept = request.headers.get('Accept', '')
    wants_json = 'application/json' in accept or request.args.get('format') == 'json'
    if wants_json:
        entries = get_dir_entries(fs_path)
        return (jsonify({'path': f'/{url_path}', 'entries': entries, 'total': len(entries)}), 200)
    else:
        entries_html = get_dir_entries_html(fs_path)
        display_path = url_path.rstrip('/')
        return render_template_string(DIR_TEMPLATE, path=display_path, entries=entries_html)

def handle_head(url_path: str, fs_path: Path):
    if not fs_path.exists():
        return Response(status=404)
    if fs_path.is_dir():
        return Response(status=400, headers={'X-Error': 'Путь является каталогом, не файлом'})
    stat = fs_path.stat()
    headers = {'Content-Length': str(stat.st_size), 'Last-Modified': format_datetime(stat.st_mtime), 'X-File-Path': f'/{url_path}', 'X-File-Size': str(stat.st_size), 'X-Last-Modified-ISO': format_datetime_iso(stat.st_mtime)}
    return Response(status=200, headers=headers)

def handle_delete(url_path: str, fs_path: Path):
    if fs_path == STORAGE_ROOT or url_path.strip('/') == '':
        return (jsonify({'error': 'Нельзя удалить корень хранилища'}), 403)
    if not fs_path.exists():
        return (jsonify({'error': f'Путь не найден: /{url_path}'}), 404)
    if fs_path.is_file():
        fs_path.unlink()
        return (jsonify({'message': 'Файл удалён', 'path': f'/{url_path}'}), 200)
    else:
        shutil.rmtree(fs_path)
        return (jsonify({'message': 'Каталог удалён', 'path': f'/{url_path}'}), 200)

@app.errorhandler(404)
def not_found(e):
    return (jsonify({'error': 'Ресурс не найден'}), 404)

@app.errorhandler(405)
def method_not_allowed(e):
    return (jsonify({'error': 'Метод не разрешён'}), 405)

@app.errorhandler(500)
def internal_error(e):
    return (jsonify({'error': 'Внутренняя ошибка сервера', 'detail': str(e)}), 500)
if __name__ == '__main__':
    print(f'  Хранилище: {STORAGE_ROOT}')
    print('Сервер запущен: http://localhost:5000')
    app.run(host='0.0.0.0', port=5000, debug=True)