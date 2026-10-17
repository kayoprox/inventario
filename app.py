"""Inventário com QR codes — Flask + SQLite. Arranque: python app.py"""
import os, sys, sqlite3, io, socket, threading, webbrowser
from datetime import date
from functools import wraps
from flask import (Flask, g, request, redirect, session, abort, Response,
                   render_template, flash)
from jinja2 import DictLoader
import segno, secrets
from werkzeug.security import generate_password_hash, check_password_hash
from markupsafe import Markup, escape

PASTA = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
DB = os.environ.get("DB_PATH", os.path.join(PASTA, "inventario.db"))  # fica ao lado do .exe
PORT = int(os.environ.get("PORT", 5000))

def _ler(nome, defeito):
    """Lê um ficheiro de texto opcional ao lado do programa (ex.: pin.txt)."""
    try:
        return open(os.path.join(PASTA, nome), encoding="utf-8").read().strip() or defeito
    except OSError:
        return defeito

def lan_ip():
    """IP deste computador na rede local (não envia dados)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1)); return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()

PIN_INICIAL = "1234"   # o PIN passa a viver na base de dados e muda-se no menu "Mudar PIN"
# Endereço que vai dentro dos QR codes. Por defeito, o IP detetado; para fixar, cria endereco.txt
BASE_URL = (os.environ.get("BASE_URL") or _ler("endereco.txt", f"http://{lan_ip()}:{PORT}")).rstrip("/")
ESTADOS = ["disponível", "em uso", "avariado", "em reparação", "abatido"]
COR = {"disponível": "#1a7f4b", "em uso": "#1f5eff", "avariado": "#c62828",
       "em reparação": "#d97706", "abatido": "#6b7585"}
TIPOS = ["Computador", "Portátil", "Monitor", "Projetor", "Router/Switch",
         "Impressora", "Telemóvel/Tablet", "Outro"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "muda-esta-chave")

SCHEMA = """
CREATE TABLE IF NOT EXISTS config(chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS localizacao(id INTEGER PRIMARY KEY, nome TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS responsavel(id INTEGER PRIMARY KEY, nome TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS equipamento(
  id INTEGER PRIMARY KEY, codigo TEXT UNIQUE NOT NULL, tipo TEXT, modelo TEXT,
  n_serie TEXT, data_aquisicao TEXT, estado TEXT DEFAULT 'disponível',
  localizacao_id INTEGER REFERENCES localizacao(id),
  responsavel_id INTEGER REFERENCES responsavel(id),
  intervalo_meses INTEGER DEFAULT 12, notas TEXT);
CREATE TABLE IF NOT EXISTS manutencao(
  id INTEGER PRIMARY KEY, equipamento_id INTEGER NOT NULL REFERENCES equipamento(id),
  data TEXT, tecnico TEXT, estado TEXT, descricao TEXT);
"""

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(_):
    d = g.pop("db", None)
    if d: d.close()

def q(sql, a=()): return db().execute(sql, a).fetchall()
def q1(sql, a=()): r = q(sql, a); return r[0] if r else None

def lookup(tabela, nome):
    nome = (nome or "").strip()
    if not nome: return None
    db().execute(f"INSERT OR IGNORE INTO {tabela}(nome) VALUES(?)", (nome,))
    return q1(f"SELECT id FROM {tabela} WHERE nome=?", (nome,))["id"]

def auth(f):
    @wraps(f)
    def w(*a, **k):
        if not session.get("ok"): return redirect("/login?next=" + request.path)
        return f(*a, **k)
    return w

def proxima(e):
    """Data da próxima manutenção = última intervenção (ou aquisição) + intervalo."""
    ult = q1("SELECT MAX(data) d FROM manutencao WHERE equipamento_id=?", (e["id"],))["d"] \
        or e["data_aquisicao"]
    if not ult: return None
    y, m, d = map(int, ult.split("-"))
    n = e["intervalo_meses"] or 12
    return date(y + (m - 1 + n) // 12, (m - 1 + n) % 12 + 1, min(d, 28))

BASE_SQL = """SELECT e.*, l.nome local, r.nome resp FROM equipamento e
  LEFT JOIN localizacao l ON l.id=e.localizacao_id
  LEFT JOIN responsavel r ON r.id=e.responsavel_id"""

@app.route("/")
def index():
    t, est = request.args.get("q", "").strip(), request.args.get("estado", "")
    sql, a = BASE_SQL + " WHERE 1=1", []
    if t:
        sql += " AND (e.codigo LIKE ? OR e.modelo LIKE ? OR e.n_serie LIKE ? OR l.nome LIKE ? OR r.nome LIKE ? OR e.tipo LIKE ?)"
        a += [f"%{t}%"] * 6
    if est: sql += " AND e.estado=?"; a.append(est)
    return render_template("lista.html", eqs=q(sql + " ORDER BY e.codigo", a), t=t, est=est)

@app.route("/e/<codigo>")
def ficha(codigo):
    e = q1(BASE_SQL + " WHERE e.codigo=?", (codigo.upper(),)) or abort(404)
    h = q("SELECT * FROM manutencao WHERE equipamento_id=? ORDER BY data DESC, id DESC", (e["id"],))
    return render_template("ficha.html", e=e, h=h, prox=proxima(e), hoje=date.today())

@app.route("/e/<codigo>/atualizar", methods=["POST"])
@auth
def atualizar(codigo):
    e = q1(BASE_SQL + " WHERE e.codigo=?", (codigo.upper(),)) or abort(404)
    f = request.form
    novo_local, nova_resp = f.get("local", "").strip(), f.get("resp", "").strip()
    partes = []
    if f["estado"] != e["estado"]: partes.append(f"Estado: {e['estado']} → {f['estado']}")
    if novo_local != (e["local"] or ""): partes.append(f"Local: {e['local'] or '—'} → {novo_local or '—'}")
    if nova_resp != (e["resp"] or ""): partes.append(f"Responsável: {e['resp'] or '—'} → {nova_resp or '—'}")
    if f.get("nota", "").strip(): partes.append(f["nota"].strip())
    db().execute("UPDATE equipamento SET estado=?, localizacao_id=?, responsavel_id=? WHERE id=?",
                 (f["estado"], lookup("localizacao", novo_local), lookup("responsavel", nova_resp), e["id"]))
    if partes:
        db().execute("INSERT INTO manutencao(equipamento_id,data,tecnico,estado,descricao) VALUES(?,?,?,?,?)",
                     (e["id"], date.today().isoformat(), f.get("tecnico", "").strip(), f["estado"], " · ".join(partes)))
    db().commit(); flash("Guardado.")
    return redirect(f"/e/{e['codigo']}")

@app.route("/novo", methods=["GET", "POST"])
@auth
def novo():
    if request.method == "POST":
        f = request.form
        n = (q1("SELECT MAX(id) m FROM equipamento")["m"] or 0) + 1
        codigo = f"EQ-{n:05d}"
        db().execute("""INSERT INTO equipamento(codigo,tipo,modelo,n_serie,data_aquisicao,estado,
            localizacao_id,responsavel_id,intervalo_meses,notas) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (codigo, f["tipo"], f["modelo"], f["n_serie"], f["data_aquisicao"] or None, f["estado"],
             lookup("localizacao", f["local"]), lookup("responsavel", f["resp"]),
             int(f["intervalo"] or 12), f["notas"]))
        db().commit()
        return redirect(f"/e/{codigo}")
    return render_template("novo.html", tipos=TIPOS,
        locais=q("SELECT nome FROM localizacao"), resps=q("SELECT nome FROM responsavel"))

@app.route("/admin")
@auth
def admin():
    por_estado = {r["estado"]: r["n"] for r in q("SELECT estado, COUNT(*) n FROM equipamento GROUP BY estado")}
    total = sum(por_estado.values())
    antigos = q(BASE_SQL + " WHERE e.data_aquisicao IS NOT NULL AND e.estado!='abatido' ORDER BY e.data_aquisicao LIMIT 10")
    todos = q(BASE_SQL + " WHERE e.estado!='abatido'")
    atrasados = sorted([(proxima(e), e) for e in todos if proxima(e) and proxima(e) <= date.today()],
                       key=lambda x: x[0])
    avarias = q("""SELECT e.codigo, e.tipo, e.modelo, COUNT(*) n FROM manutencao m JOIN equipamento e
        ON e.id=m.equipamento_id WHERE m.estado='avariado' GROUP BY e.id ORDER BY n DESC LIMIT 5""")
    por_local = q("""SELECT COALESCE(l.nome,'Sem local') nome, COUNT(*) n FROM equipamento e
        LEFT JOIN localizacao l ON l.id=e.localizacao_id GROUP BY 1 ORDER BY n DESC""")
    return render_template("admin.html", total=total, pe=por_estado, antigos=antigos,
        atrasados=atrasados, avarias=avarias, por_local=por_local, hoje=date.today())

@app.route("/etiquetas")
@auth
def etiquetas():
    return render_template("etiquetas.html", eqs=q(BASE_SQL + " ORDER BY e.codigo"))

@app.route("/qr/<codigo>.svg")
def qr(codigo):
    base = BASE_URL or request.host_url.rstrip("/")
    buf = io.BytesIO()
    segno.make(f"{base}/e/{codigo.upper()}", error="m").save(buf, kind="svg", scale=6, border=1)
    return Response(buf.getvalue(), mimetype="image/svg+xml")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if check_password_hash(q1("SELECT valor FROM config WHERE chave='pin'")["valor"], request.form["pin"]):
            session["ok"] = True; session.permanent = True
            nxt = request.args.get("next", "/")
            return redirect(nxt if nxt.startswith("/") else "/")
        flash("PIN errado.")
    return render_template("login.html")

@app.route("/pin", methods=["GET", "POST"])
@auth
def mudar_pin():
    if request.method == "POST":
        f = request.form
        if not check_password_hash(q1("SELECT valor FROM config WHERE chave='pin'")["valor"], f["atual"]):
            flash("PIN atual errado.")
        elif len(f["novo"]) < 4:
            flash("O novo PIN deve ter pelo menos 4 caracteres.")
        elif f["novo"] != f["confirma"]:
            flash("Os dois PIN novos não coincidem.")
        else:
            db().execute("UPDATE config SET valor=? WHERE chave='pin'", (generate_password_hash(f["novo"]),))
            db().commit(); flash("PIN alterado."); return redirect("/")
    return render_template("pin.html")

@app.route("/sair")
def sair(): session.clear(); return redirect("/")

# ---------- Templates (tudo num só ficheiro para ser fácil de copiar) ----------
BASE = """<!doctype html><html lang="pt"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Inventário</title>
<style>:root{--bg:#f6f7f9;--fg:#1c2330;--card:#fff;--mut:#6b7585;--ac:#1f5eff;--bd:#e2e5ea}
@media(prefers-color-scheme:dark){:root{--bg:#12151b;--fg:#e8ebf0;--card:#1b2029;--mut:#98a2b3;--ac:#6b93ff;--bd:#2a313d}}
*{box-sizing:border-box}body{margin:0;font:16px system-ui,sans-serif;background:var(--bg);color:var(--fg)}
nav{display:flex;gap:16px;padding:12px 16px;background:var(--card);border-bottom:1px solid var(--bd);flex-wrap:wrap}
nav a{color:var(--fg);text-decoration:none;font-weight:600}main{max-width:760px;margin:0 auto;padding:16px}
.c{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px;margin-bottom:12px}
a{color:var(--ac)}input,select,textarea,button{font:inherit;width:100%;padding:10px;margin:4px 0 10px;border-radius:8px;border:1px solid var(--bd);background:var(--bg);color:var(--fg)}
button{background:var(--ac);color:#fff;border:0;font-weight:600;cursor:pointer}label{font-size:13px;color:var(--mut)}
.b{display:inline-block;padding:2px 10px;border-radius:99px;font-size:13px;font-weight:600;color:#fff}
.row{display:flex;justify-content:space-between;gap:8px;align-items:center}.m{color:var(--mut);font-size:14px}
.k{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}.k b{font-size:28px;display:block}
.msg{background:#d3f5df;color:#14532d;padding:10px;border-radius:8px;margin-bottom:12px}
table{width:100%;border-collapse:collapse}td,th{padding:6px 4px;border-bottom:1px solid var(--bd);text-align:left;font-size:14px}
@media print{nav,.np{display:none}body{background:#fff}}</style>
<nav class="np"><a href="/">📦 Inventário</a><a href="/novo">+ Novo</a><a href="/admin">Painel</a>
<a href="/etiquetas">Etiquetas</a>{% if session.ok %}<a href="/pin">Mudar PIN</a><a href="/sair">Sair</a>{% else %}<a href="/login">Entrar</a>{% endif %}</nav>
<main>{% for m in get_flashed_messages() %}<div class="msg np">{{m}}</div>{% endfor %}{% block c %}{% endblock %}</main></html>"""


T = {
"base.html": BASE,
"lista.html": """{% extends 'base.html' %}{% block c %}
<form method="get" class="row" style="gap:8px"><input name="q" value="{{t}}" placeholder="Procurar código, série, sala, pessoa…">
<select name="estado" style="width:auto"><option value="">Todos</option>{% for s in ESTADOS %}<option {{'selected' if s==est}}>{{s}}</option>{% endfor %}</select>
<button style="width:auto">Ir</button></form>
{% for e in eqs %}<a href="/e/{{e.codigo}}" style="text-decoration:none;color:inherit"><div class="c"><div class="row"><b>{{e.codigo}} · {{e.tipo}}</b>{{badge(e.estado)}}</div>
<div class="m">{{e.modelo}} · {{e.local or 'Sem local'}} · {{e.resp or 'Sem responsável'}}</div></div></a>
{% else %}<p class="m">Sem resultados.</p>{% endfor %}{% endblock %}""",
"ficha.html": """{% extends 'base.html' %}{% block c %}
<div class="c"><div class="row"><h2 style="margin:0">{{e.codigo}}</h2>{{badge(e.estado)}}</div>
<p><b>{{e.tipo}}</b> — {{e.modelo}}<br>Nº série: {{e.n_serie or '—'}}<br>Adquirido: {{e.data_aquisicao or '—'}}<br>
📍 {{e.local or '—'}}<br>👤 {{e.resp or '—'}}<br>
🔧 Próxima manutenção: {% if prox %}<b style="color:{{'#c62828' if prox<=hoje}}">{{prox}}</b>{% else %}—{% endif %}</p>
{% if e.notas %}<p class="m">{{e.notas}}</p>{% endif %}</div>
{% if session.ok %}<form method="post" action="/e/{{e.codigo}}/atualizar" class="c"><h3 style="margin-top:0">Atualizar</h3>
<label>Estado</label><select name="estado">{% for s in ESTADOS %}<option {{'selected' if s==e.estado}}>{{s}}</option>{% endfor %}</select>
<label>Localização</label><input name="local" value="{{e.local or ''}}"><label>Responsável</label><input name="resp" value="{{e.resp or ''}}">
<label>O que foi feito / observações</label><textarea name="nota" rows="3"></textarea>
<label>Técnico</label><input name="tecnico"><button>Guardar</button></form>
{% else %}<a class="c" style="display:block" href="/login?next=/e/{{e.codigo}}">🔒 Entrar como técnico para atualizar</a>{% endif %}
<h3>Histórico</h3>{% for x in h %}<div class="c"><div class="row"><b>{{x.data}}</b><span class="m">{{x.tecnico}}</span></div>{{x.descricao}}</div>
{% else %}<p class="m">Sem histórico.</p>{% endfor %}{% endblock %}""",
"novo.html": """{% extends 'base.html' %}{% block c %}<h2>Novo equipamento</h2>
<form method="post" class="c"><label>Tipo</label><select name="tipo">{% for t in tipos %}<option>{{t}}</option>{% endfor %}</select>
<label>Marca / modelo</label><input name="modelo" required><label>Nº de série</label><input name="n_serie">
<label>Data de aquisição</label><input type="date" name="data_aquisicao"><label>Estado</label><select name="estado">{% for s in ESTADOS %}<option>{{s}}</option>{% endfor %}</select>
<label>Localização</label><input name="local" list="ls"><datalist id="ls">{% for l in locais %}<option>{{l.nome}}</option>{% endfor %}</datalist>
<label>Responsável</label><input name="resp" list="rs"><datalist id="rs">{% for r in resps %}<option>{{r.nome}}</option>{% endfor %}</datalist>
<label>Manutenção de X em X meses</label><input type="number" name="intervalo" value="12"><label>Notas</label><textarea name="notas"></textarea>
<button>Criar e gerar QR</button></form>{% endblock %}""",
"admin.html": """{% extends 'base.html' %}{% block c %}<h2>Painel</h2>
<div class="k"><div class="c"><b>{{total}}</b>total</div>{% for s in ESTADOS %}<div class="c"><b style="color:{{COR[s]}}">{{pe.get(s,0)}}</b>{{s}}</div>{% endfor %}</div>
<div class="c"><h3 style="margin-top:0">🔧 Manutenção em atraso ({{atrasados|length}})</h3><table>{% for d,e in atrasados %}<tr><td><a href="/e/{{e.codigo}}">{{e.codigo}}</a></td><td>{{e.tipo}} {{e.modelo}}</td><td>{{d}}</td></tr>{% else %}<tr><td>Tudo em dia ✅</td></tr>{% endfor %}</table></div>
<div class="c"><h3 style="margin-top:0">⏳ Mais antigos (a substituir)</h3><table>{% for e in antigos %}<tr><td><a href="/e/{{e.codigo}}">{{e.codigo}}</a></td><td>{{e.tipo}} {{e.modelo}}</td><td>{{e.data_aquisicao}} ({{hoje.year-e.data_aquisicao[:4]|int}} anos)</td></tr>{% endfor %}</table></div>
<div class="c"><h3 style="margin-top:0">🚨 Mais avarias</h3><table>{% for e in avarias %}<tr><td><a href="/e/{{e.codigo}}">{{e.codigo}}</a></td><td>{{e.tipo}} {{e.modelo}}</td><td>{{e.n}}×</td></tr>{% else %}<tr><td>Sem avarias registadas.</td></tr>{% endfor %}</table></div>
<div class="c"><h3 style="margin-top:0">📍 Por localização</h3><table>{% for l in por_local %}<tr><td>{{l.nome}}</td><td>{{l.n}}</td></tr>{% endfor %}</table></div>{% endblock %}""",
"etiquetas.html": """{% extends 'base.html' %}{% block c %}<p class="np m">Imprime esta página (Ctrl+P) em etiquetas autocolantes ou papel normal e recorta.</p>
<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px">{% for e in eqs %}
<div style="border:1px dashed #888;padding:8px;text-align:center;background:#fff;color:#000;break-inside:avoid"><img src="/qr/{{e.codigo}}.svg" width="120"><br><b>{{e.codigo}}</b><br><small>{{e.tipo}}</small></div>{% endfor %}</div>{% endblock %}""",
"pin.html": """{% extends 'base.html' %}{% block c %}<form method="post" class="c"><h3 style="margin-top:0">Mudar PIN</h3>
<label>PIN atual</label><input type="password" name="atual" required><label>Novo PIN (mínimo 4 caracteres)</label><input type="password" name="novo" required>
<label>Repetir novo PIN</label><input type="password" name="confirma" required><button>Guardar</button></form>{% endblock %}""",
"login.html": """{% extends 'base.html' %}{% block c %}<form method="post" class="c"><h3 style="margin-top:0">Entrar (técnicos)</h3>
<input type="password" name="pin" placeholder="PIN" inputmode="numeric" autofocus><button>Entrar</button></form>{% endblock %}""",
}
app.jinja_loader = DictLoader(T)
def badge(s):
    return Markup(f'<span class="b" style="background:{COR.get(s, "#6b7585")}">{escape(s)}</span>')

app.jinja_env.globals.update(ESTADOS=ESTADOS, COR=COR, badge=badge)

with app.app_context():
    db().executescript(SCHEMA)
    db().execute("INSERT OR IGNORE INTO config VALUES('pin',?)", (generate_password_hash(PIN_INICIAL),))
    db().execute("INSERT OR IGNORE INTO config VALUES('secret',?)", (secrets.token_hex(32),))
    # Esqueceste o PIN? Cria um ficheiro vazio "repor-pin.txt" ao lado do programa e reinicia: o PIN volta a 1234.
    _rep = os.path.join(PASTA, "repor-pin.txt")
    if os.path.exists(_rep):
        db().execute("UPDATE config SET valor=? WHERE chave='pin'", (generate_password_hash(PIN_INICIAL),))
        os.remove(_rep)
    db().commit()
    app.secret_key = os.environ.get("SECRET_KEY") or q1("SELECT valor FROM config WHERE chave='secret'")["valor"]

if __name__ == "__main__":
    print(f"\n  INVENTÁRIO a correr (fecha esta janela para parar)\n"
          f"  Neste PC:    http://localhost:{PORT}\n"
          f"  Telemóveis:  {BASE_URL}   (ligados ao mesmo Wi-Fi)\n")
    threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="0.0.0.0", port=PORT)
