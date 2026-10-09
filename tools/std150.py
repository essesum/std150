#!/usr/bin/env python3
"""СТД 150 — рабочий CLI партитуры: правки сцен, версии файлов, сборка и публикация зашифрованного сайта.

Данные:   private/data/project.json   (открытый текст, в git НЕ попадает)
Медиа:    private/media/               (рефы и превью версий, открытый текст)
Шаблон:   private/app.html             (сайт; __DATA__ заменяется на JSON)
Публикуется: index.html (шифротекст страницы) + a/<id> (шифротекст каждой картинки/видео) + site.json (соль).

Пароль: env STD150_PASSWORD или файл ~/.std150_pass.

Примеры:
  std150.py list --status anim
  std150.py show 7а
  std150.py set 7а status=anim who="Елкина"
  std150.py add-version 4 ~/Downloads/troika_v2.mp4 --surface rear --by "Елкина" --note "медленный галоп"
  std150.py add-version 13 https://disk.yandex.ru/i/XXXX --surface net --by "Елкина"
  std150.py comment 8 "Луна ниже, не перекрывать балкон" --by "Катя"
  std150.py ask 20а "Нужен файл для сетки?" --topic Сетка
  std150.py answer q21 "Да, звёзды + фонарики" --by "Стародубцев"
  std150.py summary
  std150.py publish -m "Тройка v2"          # build + verify + commit + push
  std150.py publish --archive               # + обновить std150-source.zip.enc для передачи проекта
"""
import argparse, base64, datetime as dt, hashlib, io, json, os, re, shutil, subprocess, sys, tempfile, urllib.parse, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIV = ROOT / 'private'
DATA = PRIV / 'data' / 'project.json'
MEDIA = PRIV / 'media'
APP = PRIV / 'app.html'
GATE = ROOT / 'tools' / 'gate.html'
ASSETS = ROOT / 'a'
SITE = ROOT / 'site.json'
ITER = 600_000
STATUSES = ['none', 'scen', 'setup', 'anim', 'master', 'done']
NET_STATES = ['up', 'blackout', 'sheer']
EDITABLE = {'t', 'status', 'who', 'pr', 'note', 'rear', 'rsrc', 'net', 'nsrc', 'net_state', 'd', 'buf', 'anim', 'idea', 'diff', 'artists', 'loop', 'w', 'text'}
MIME = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.mp4': 'video/mp4', '.gif': 'image/gif'}


def die(msg):
    print('ошибка:', msg, file=sys.stderr); sys.exit(1)


def password():
    pw = os.environ.get('STD150_PASSWORD')
    if not pw:
        f = Path.home() / '.std150_pass'
        pw = f.read_text().strip() if f.exists() else ''
    if not pw: die('нет пароля: задай STD150_PASSWORD или ~/.std150_pass')
    return pw.encode()


def crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
    except ImportError:
        die('нужен пакет cryptography: pip install cryptography')
    return AESGCM, PBKDF2HMAC, hashes


def site_key():
    AESGCM, PBKDF2HMAC, hashes = crypto()
    if SITE.exists():
        meta = json.loads(SITE.read_text())
    else:
        meta = {'salt': base64.b64encode(os.urandom(16)).decode(), 'iter': ITER}
        SITE.write_text(json.dumps(meta) + '\n')
    salt = base64.b64decode(meta['salt'])
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=meta['iter']).derive(password())
    return AESGCM(key), meta


def load():
    return json.loads(DATA.read_text())


def save(d, by, text):
    d.setdefault('log', []).insert(0, {'date': now(), 'by': by or 'Катин Джун', 'text': text})
    d['log'] = d['log'][:200]
    tmp = DATA.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    tmp.replace(DATA)


def now():
    return dt.datetime.now().strftime('%Y-%m-%d %H:%M')


def norm_id(x):
    return x.strip().replace('C', 'С').replace('c', 'С').replace('a', 'а').replace('b', 'б').lower()


def find(d, sid):
    for s in d['scenes'] + d.get('extras', []):
        if norm_id(s['id']) == norm_id(sid): return s
    die(f'сцена «{sid}» не найдена. Есть: ' + ', '.join(s['id'] for s in d['scenes']))


def fmt(sec):
    if sec is None: return '—'
    return f'{sec // 60}:{sec % 60:02d}'


def parse_time(v):
    if v in ('', 'null', 'none', '-'): return None
    if ':' in v:
        m, s = v.split(':'); return int(m) * 60 + int(s)
    return int(v)


# ---------- команды чтения ----------

def cmd_list(a):
    d = load()
    for s in d['scenes'] + d.get('extras', []):
        if a.status and s.get('status') != a.status: continue
        if a.who and a.who.lower() not in (s.get('who') or '').lower(): continue
        v = s.get('versions') or []
        print(f"{s['id']:>4}  {s.get('status','?'):6} {d['meta']['net_states'].get(s.get('net_state'),'—'):22} {fmt(s.get('d')):>6}  {s['t'][:42]:42}  {s.get('who','')[:18]:18} v{len(v)}")


def cmd_show(a):
    d = load(); s = find(d, a.id)
    keys = ['id', 't', 'status', 'who', 'pr', 'd', 'buf', 'net_state', 'artists', 'rear', 'rsrc', 'net', 'nsrc', 'files', 'note', 'anim', 'idea', 'diff', 'words', 'text']
    for k in keys:
        if s.get(k) not in (None, '', []):
            val = fmt(s[k]) if k in ('d', 'buf') else s[k]
            print(f'{k:10} {val}')
    for v in s.get('versions', []):
        print(f"version   v{v['v']:03d} {v['surface']} {v['date']} {v.get('by','')} — {v.get('note','')} [{v.get('name','')}]")
    for c in s.get('comments', []):
        print(f"comment   {c['date']} {c.get('by','')}: {c['text']}")
    for q in d['questions']:
        if norm_id(q['scene']) == norm_id(s['id']):
            print(f"question  {q['id']} [{q['status']}] {q['text']}" + (f" → {q['answer']}" if q.get('answer') else ''))


def cmd_summary(a):
    d = load(); names = {x['k']: x['n'] for x in d['meta']['statuses']}
    sc = [s for s in d['scenes'] if s.get('status') != 'none']
    by = {}
    for s in sc: by.setdefault(s['status'], []).append(s['id'])
    concert = dt.date(2026, 10, 22); usb = dt.date(2026, 10, 19); today = dt.date.today()
    print(f"До сдачи USB (19.10): {(usb - today).days} дн. · до репетиции (20.10): {(dt.date(2026,10,20) - today).days} дн. · до концерта (22.10): {(concert - today).days} дн.")
    for k in STATUSES:
        if k in by: print(f"{names[k]:16} {len(by[k]):2}  {', '.join(by[k])}")
    oq = [q for q in d['questions'] if q['status'] == 'open']
    print(f"Открытых вопросов режиссёру: {len(oq)}")
    for l in d.get('log', [])[:5]: print(f"  {l['date']} {l['by']}: {l['text']}")


# ---------- правки ----------

def cmd_set(a):
    d = load(); s = find(d, a.id); changes = []
    for kv in a.pairs:
        if '=' not in kv: die(f'ожидаю поле=значение, получила «{kv}»')
        k, v = kv.split('=', 1)
        if k not in EDITABLE: die(f'поле «{k}» не редактируется. Можно: {", ".join(sorted(EDITABLE))}')
        if k == 'status' and v not in STATUSES: die(f'статус: {", ".join(STATUSES)}')
        if k == 'net_state' and v not in NET_STATES: die(f'net_state: {", ".join(NET_STATES)}')
        if k in ('d', 'buf'): v = parse_time(v)
        if k == 'loop': v = v.lower() in ('1', 'true', 'да', 'yes')
        s[k] = v; changes.append(f'{k}={v if k not in ("d","buf") else fmt(v)}')
    save(d, a.by, f"{s['id']}: " + ', '.join(changes)); print('ok', s['id'], *changes)


def fetch(src, dst_dir):
    if not re.match(r'https?://', src):
        p = Path(src).expanduser()
        if not p.exists(): die(f'файл не найден: {p}')
        return p
    url = src
    if 'disk.yandex' in src or 'yadi.sk' in src:
        api = 'https://cloud-api.yandex.net/v1/disk/public/resources/download?' + urllib.parse.urlencode({'public_key': src})
        url = json.loads(urllib.request.urlopen(api, timeout=60).read())['href']
    name = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name) or 'download'
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    if 'filename' in q: name = q['filename'][0]
    out = Path(dst_dir) / re.sub(r'[^\w.\-]+', '_', name)
    print('скачиваю', name, '…')
    with urllib.request.urlopen(url, timeout=600) as r, open(out, 'wb') as f: shutil.copyfileobj(r, f)
    return out


def make_preview(src, base):
    """Видео → mp4 h264 960px ≤60 c без звука + постер jpg; картинка → jpg 1600px. Возвращает (main, poster|None)."""
    ext = src.suffix.lower()
    if ext in ('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff', '.psd', '.heic'):
        out = base.with_suffix('.jpg')
        run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-vf', "scale='min(1600,iw)':-2", '-q:v', '3', '-frames:v', '1', str(out)])
        return out, None
    out = base.with_suffix('.mp4'); poster = base.with_name(base.name + '_poster.jpg')
    run(['ffmpeg', '-v', 'error', '-y', '-i', str(src), '-t', '60', '-an', '-vf', "scale='min(960,iw)':-2,fps=25", '-c:v', 'libx264', '-preset', 'veryfast',
         '-crf', '28', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(out)])
    run(['ffmpeg', '-v', 'error', '-y', '-ss', '1', '-i', str(src), '-frames:v', '1', '-vf', "scale='min(1600,iw)':-2", '-q:v', '3', str(poster)])
    return out, poster


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode: die(f"{' '.join(cmd[:3])}…: {r.stderr.strip()[-500:]}")
    return r.stdout


def cmd_add_version(a):
    d = load(); s = find(d, a.id)
    surf = {'rear': 'rear', 'задник': 'rear', 'r': 'rear', 'net': 'net', 'сетка': 'net', 'n': 'net'}.get(a.surface.lower())
    if not surf: die('--surface rear|net')
    with tempfile.TemporaryDirectory() as tmp:
        src = fetch(a.file, tmp)
        n = 1 + max([v['v'] for v in s.get('versions', []) if v['surface'] == surf] or [0])
        (MEDIA / 'v').mkdir(parents=True, exist_ok=True)
        slug = re.sub(r'[^\w]+', '_', s['id']).strip('_') or 'x'
        base = MEDIA / 'v' / f"{slug}_{surf}_v{n:03d}"
        main, poster = make_preview(src, base)
        orig = src.name
    v = {'v': n, 'surface': surf, 'date': now(), 'by': a.by or '', 'note': a.note or '', 'name': orig,
         'media': str(main.relative_to(MEDIA)), 'poster': str(poster.relative_to(MEDIA)) if poster else None}
    s.setdefault('versions', []).append(v)
    if a.status: s['status'] = a.status
    save(d, a.by, f"{s['id']}: новая версия {surf} v{n:03d} ({orig})")
    print('ok', s['id'], surf, f'v{n:03d}', v['media'], f'{main.stat().st_size/1e6:.1f} MB')


def cmd_comment(a):
    d = load(); s = find(d, a.id)
    s.setdefault('comments', []).append({'date': now(), 'by': a.by or '', 'text': a.text})
    save(d, a.by, f"{s['id']}: комментарий"); print('ok')


def cmd_ask(a):
    d = load(); qid = f"q{1 + max(int(q['id'][1:]) for q in d['questions'])}"
    d['questions'].append({'id': qid, 'scene': a.scene, 'topic': a.topic or 'Сцена', 'text': a.text, 'status': 'open', 'answer': '', 'date': now()})
    save(d, a.by, f'новый вопрос {qid} ({a.scene})'); print('ok', qid)


def cmd_answer(a):
    d = load()
    q = next((q for q in d['questions'] if q['id'] == a.qid), None) or die(f'нет вопроса {a.qid}')
    q.update(status='answered', answer=a.text, answered_by=a.by or '', answered=now())
    save(d, a.by, f"ответ на {a.qid}"); print('ok', a.qid)


# ---------- сборка ----------

def media_refs(d):
    refs = set(d['img'].keys())
    for s in d['scenes'] + d.get('extras', []):
        refs.update(s.get('refs', []))
        for v in s.get('versions', []):
            refs.add(v['media'])
            if v.get('poster'): refs.add(v['poster'])
    refs.update(['bt_stage2', 'bt_view_hall', 'bt_view_stage', 'stanislavsky_frame', 'stanislavsky', 'cabinet_plate', 'stanislavsky_ref.mp4', 'kv_statue', 'kv_muse_moon', 'kv_moon_doves', 'kv_muse_flag', 'poster'])
    return refs


def media_path(ref):
    p = MEDIA / ref
    if p.suffix: return p
    for ext in ('.jpg', '.png', '.mp4'):
        if (MEDIA / (ref + ext)).exists(): return MEDIA / (ref + ext)
    return MEDIA / (ref + '.jpg')


def public(d):
    """Что уходит на страницу: без внутренних полей (исполнители видны только в project.json и в CLI)."""
    d = json.loads(json.dumps(d))
    for s in d['scenes'] + d.get('extras', []):
        s.pop('who', None)
        for v in s.get('versions', []): v.pop('by', None)
    for l in d.get('log', []): l.pop('by', None)
    return d


def cmd_build(a=None, quiet=False):
    d = load(); aes, meta = site_key()
    ASSETS.mkdir(exist_ok=True)
    manifest, used = {}, set()
    for ref in sorted(media_refs(d)):
        p = media_path(ref)
        if not p.exists():
            print('  нет файла для', ref, file=sys.stderr); continue
        raw = p.read_bytes(); aid = hashlib.sha256(raw).hexdigest()[:24]
        manifest[ref] = {'id': aid, 'type': MIME.get(p.suffix.lower(), 'application/octet-stream'), 'size': len(raw)}
        used.add(aid); out = ASSETS / aid
        if not out.exists():
            iv = os.urandom(12); out.write_bytes(iv + aes.encrypt(iv, raw, None))
    for f in ASSETS.iterdir():
        if f.name not in used: f.unlink()
    d['assets'] = manifest
    d['built'] = now()
    html = APP.read_text(encoding='utf-8').replace('__DATA__', json.dumps(public(d), ensure_ascii=False).replace('</', '<\\/'))
    iv = os.urandom(12); ct = aes.encrypt(iv, html.encode(), None)
    kid = hashlib.sha256(base64.b64decode(meta['salt'])).hexdigest()[:10]
    payload = {'v': hashlib.sha256(ct).hexdigest()[:10], 'kid': kid, 'iter': meta['iter'], 'salt': meta['salt'],
               'iv': base64.b64encode(iv).decode(), 'ct': base64.b64encode(ct).decode()}
    (ROOT / 'index.html').write_text(GATE.read_text(encoding='utf-8').replace('__PAYLOAD__', json.dumps(payload)), encoding='utf-8')
    if not quiet:
        tot = sum(f.stat().st_size for f in ASSETS.iterdir())
        print(f"ok: index.html {len(ct)/1e3:.0f} KB, ассетов {len(used)} ({tot/1e6:.1f} MB)")
    return d


def cmd_verify(a=None):
    """Расшифровывает опубликованное обратно и сверяет с исходниками."""
    aes, meta = site_key()
    g = (ROOT / 'index.html').read_text(encoding='utf-8')
    m = re.search(r'<script type="application/json" id="payload">(.*?)</script>', g, re.S) or die('payload не найден')
    p = json.loads(m.group(1))
    html = aes.decrypt(base64.b64decode(p['iv']), base64.b64decode(p['ct']), None).decode()
    dm = re.search(r'<script type="application/json" id="data">(.*?)</script>', html, re.S) or die('data не найден в странице')
    d = json.loads(dm.group(1).replace('<\\/', '</'))
    bad = 0
    for ref, info in d['assets'].items():
        blob = (ASSETS / info['id']).read_bytes()
        raw = aes.decrypt(blob[:12], blob[12:], None)
        if raw != media_path(ref).read_bytes(): bad += 1; print('  не совпадает', ref)
    src = public(load()); src.pop('assets', None); src.pop('built', None)
    d2 = dict(d); d2.pop('assets', None); d2.pop('built', None)
    if d2 != src: bad += 1; print('  данные в странице отличаются от project.json (пересобери)')
    tot = sum(s['d'] or 0 for s in d['scenes'])
    print(f"verify: {len(d['scenes'])} сцен, хронометраж {fmt(tot)}, ассетов {len(d['assets'])}, ошибок {bad}")
    if bad: sys.exit(2)


def cmd_archive(a=None):
    AESGCM, PBKDF2HMAC, hashes = crypto()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in sorted(PRIV.rglob('*')):
            if f.is_file() and f.name != '.DS_Store': z.write(f, f.relative_to(PRIV))
    salt, iv = os.urandom(16), os.urandom(12)
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITER).derive(password())
    (ROOT / 'std150-source.zip.enc').write_bytes(b'STD1' + salt + iv + AESGCM(key).encrypt(iv, buf.getvalue(), None))
    print(f'ok: std150-source.zip.enc ({buf.tell()/1e6:.1f} MB до шифрования)')


def cmd_publish(a):
    cmd_build(); cmd_verify()
    if a.archive: cmd_archive()
    git = lambda *x: run(['git', '-C', str(ROOT), *x])
    git('add', '-A', 'index.html', 'a', 'site.json', 'tools', 'README.md', '.gitignore', *(['std150-source.zip.enc'] if a.archive else []))
    if not git('status', '--porcelain', '--untracked-files=no').strip():
        print('изменений нет'); return
    msg = a.message or (load().get('log') or [{}])[0].get('text', 'обновление партитуры')
    git('commit', '-q', '-m', f'std150: {msg}')
    git('pull', '-q', '--rebase')
    git('push', '-q')
    print('опубликовано: https://essesum.github.io/std150/ (GitHub Pages обновится за 1–2 минуты)')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('list'); p.add_argument('--status', choices=STATUSES); p.add_argument('--who'); p.set_defaults(f=cmd_list)
    p = sp.add_parser('show'); p.add_argument('id'); p.set_defaults(f=cmd_show)
    p = sp.add_parser('summary'); p.set_defaults(f=cmd_summary)
    p = sp.add_parser('set'); p.add_argument('id'); p.add_argument('pairs', nargs='+'); p.add_argument('--by'); p.set_defaults(f=cmd_set)
    p = sp.add_parser('add-version'); p.add_argument('id'); p.add_argument('file'); p.add_argument('--surface', required=True)
    p.add_argument('--by'); p.add_argument('--note'); p.add_argument('--status', choices=STATUSES); p.set_defaults(f=cmd_add_version)
    p = sp.add_parser('comment'); p.add_argument('id'); p.add_argument('text'); p.add_argument('--by'); p.set_defaults(f=cmd_comment)
    p = sp.add_parser('ask'); p.add_argument('scene'); p.add_argument('text'); p.add_argument('--topic'); p.add_argument('--by'); p.set_defaults(f=cmd_ask)
    p = sp.add_parser('answer'); p.add_argument('qid'); p.add_argument('text'); p.add_argument('--by'); p.set_defaults(f=cmd_answer)
    p = sp.add_parser('build'); p.set_defaults(f=cmd_build)
    p = sp.add_parser('verify'); p.set_defaults(f=cmd_verify)
    p = sp.add_parser('archive'); p.set_defaults(f=cmd_archive)
    p = sp.add_parser('publish'); p.add_argument('-m', '--message'); p.add_argument('--archive', action='store_true'); p.set_defaults(f=cmd_publish)
    a = ap.parse_args(); a.f(a)


if __name__ == '__main__':
    main()
