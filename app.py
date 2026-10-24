"""Inventário com QR codes — Flask + SQLite. Arranque: python app.py"""
import time, os, sys, sqlite3, io, socket, threading, webbrowser
from datetime import date
from functools import wraps
from flask import (Flask, g, request, redirect, session, abort, Response,
                   render_template, flash)
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

# Endereço que vai dentro dos QR codes. Por defeito, o IP detetado; para fixar, cria endereco.txt
BASE_URL = (os.environ.get("BASE_URL") or _ler("endereco.txt", f"http://{lan_ip()}:{PORT}")).rstrip("/")
ESTADOS = ["disponível", "em uso", "avariado", "em reparação", "abatido"]
COR = {"disponível": "#1a7f4b", "em uso": "#1f5eff", "avariado": "#c62828",
       "em reparação": "#d97706", "abatido": "#6b7585"}
TIPOS = ["Computador", "Portátil", "Monitor", "Projetor", "Router/Switch",
         "Impressora", "Telemóvel/Tablet", "Outro"]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "muda-esta-chave")
app.config.update(SESSION_COOKIE_SAMESITE="Lax")

SCHEMA = """
CREATE TABLE IF NOT EXISTS config(chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS utilizador(id INTEGER PRIMARY KEY, nome TEXT NOT NULL, login TEXT UNIQUE NOT NULL,
  hash TEXT NOT NULL, perfil TEXT NOT NULL DEFAULT 'tecnico', ativo INTEGER DEFAULT 1, trocar_pw INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS tentativas(chave TEXT, ts REAL);
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

NIVEL = {"consulta": 1, "tecnico": 2, "admin": 3}   # consulta só vê · técnico atualiza · admin gere tudo

def atual():
    """Utilizador com sessão iniciada (None se não houver ou se a conta foi desativada)."""
    if "u" not in g:
        g.u = q1("SELECT * FROM utilizador WHERE id=? AND ativo=1", (session["uid"],)) if session.get("uid") else None
    return g.u

@app.context_processor
def _ctx(): return {"u": atual()}

def papel(minimo):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            u = atual()
            if not u: return redirect("/login?next=" + request.path)
            if u["trocar_pw"] and request.endpoint not in ("conta", "sair"): return redirect("/conta")
            if NIVEL[u["perfil"]] < NIVEL[minimo]: abort(403)
            return f(*a, **k)
        return w
    return deco

def ip(): return (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()

def bloqueado(login):
    """5 falhas por utilizador ou 20 por IP nos últimos 10 minutos bloqueiam novas tentativas."""
    db().execute("DELETE FROM tentativas WHERE ts<?", (time.time() - 600,))
    n = lambda k: q1("SELECT COUNT(*) n FROM tentativas WHERE chave=?", (k,))["n"]
    return n("u:" + login) >= 5 or n("ip:" + ip()) >= 20

def falhou(login):
    for k in ("u:" + login, "ip:" + ip()):
        db().execute("INSERT INTO tentativas VALUES(?,?)", (k, time.time()))
    db().commit()

def n_admins(excluir=0):
    return q1("SELECT COUNT(*) n FROM utilizador WHERE perfil='admin' AND ativo=1 AND id!=?", (excluir,))["n"]

def pw_temp(): return secrets.token_urlsafe(6)

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
@papel("consulta")
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
@papel("tecnico")
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
                     (e["id"], date.today().isoformat(), atual()["nome"], f["estado"], " · ".join(partes)))
    db().commit(); flash("Guardado.")
    return redirect(f"/e/{e['codigo']}")

@app.route("/novo", methods=["GET", "POST"])
@papel("tecnico")
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
@papel("admin")
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
    ativos = sum(por_estado.get(e, 0) for e in ESTADOS[:4]); off, anel = 0, []
    for e in ESTADOS[:4]:
        n = por_estado.get(e, 0); d = 282.7 * n / ativos if ativos else 0
        anel.append((e, n, round(d, 1), round(-off, 1), EST_ICON[e][1])); off += d
    salas = q("""SELECT COALESCE(l.nome,'Sem local') nome, COALESCE(SUM(e.estado IN ('avariado','em reparação')),0) n
        FROM equipamento e LEFT JOIN localizacao l ON l.id=e.localizacao_id WHERE e.estado!='abatido' GROUP BY 1 ORDER BY n DESC, nome""")
    mx = max([x["n"] for x in salas] + [1])
    return render_template("admin.html", total=total, anel=anel, salas=salas, mx=mx, antigos=antigos,
                           atrasados=atrasados, avarias=avarias, hoje=date.today())

@app.route("/etiquetas")
@papel("tecnico")
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
        lg = request.form.get("login", "").strip().lower()
        if bloqueado(lg):
            flash("Demasiadas tentativas. Aguarda 10 minutos e tenta de novo.")
        else:
            x = q1("SELECT * FROM utilizador WHERE login=? AND ativo=1", (lg,))
            if x and check_password_hash(x["hash"], request.form.get("pw", "")):
                db().execute("DELETE FROM tentativas WHERE chave=?", ("u:" + lg,)); db().commit()
                session.clear(); session["uid"] = x["id"]; session.permanent = True
                nxt = request.args.get("next", "/")
                return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")
            falhou(lg); flash("Utilizador ou palavra-passe errados.")
    return render_template("login.html")

@app.route("/sair")
def sair(): session.clear(); return redirect("/")

@app.route("/conta", methods=["GET", "POST"])
@papel("consulta")
def conta():
    u = atual()
    if request.method == "POST":
        f = request.form
        if not check_password_hash(u["hash"], f["atual"]): flash("Palavra-passe atual errada.")
        elif len(f["nova"]) < 8: flash("A nova palavra-passe deve ter pelo menos 8 caracteres.")
        elif f["nova"] != f["confirma"]: flash("As duas palavras-passe novas não coincidem.")
        elif f["nova"] == f["atual"]: flash("Escolhe uma palavra-passe diferente da atual.")
        else:
            db().execute("UPDATE utilizador SET hash=?, trocar_pw=0 WHERE id=?", (generate_password_hash(f["nova"]), u["id"]))
            db().commit(); flash("Palavra-passe alterada."); return redirect("/")
    return render_template("conta.html")

@app.route("/utilizadores")
@papel("admin")
def utilizadores():
    return render_template("utilizadores.html", users=q("SELECT * FROM utilizador ORDER BY ativo DESC, nome"))

@app.route("/utilizadores/novo", methods=["POST"])
@papel("admin")
def utilizador_novo():
    f = request.form; lg = f["login"].strip().lower(); nome = f["nome"].strip()
    if f["perfil"] not in NIVEL or not lg or not nome: abort(400)
    if q1("SELECT 1 FROM utilizador WHERE login=?", (lg,)): flash("Esse utilizador já existe.")
    else:
        pw = pw_temp()
        db().execute("INSERT INTO utilizador(nome,login,hash,perfil) VALUES(?,?,?,?)", (nome, lg, generate_password_hash(pw), f["perfil"]))
        db().commit()
        flash(f"Conta criada. Utilizador: {lg} · Palavra-passe temporária: {pw} (só aparece agora; terá de a mudar no primeiro acesso).")
    return redirect("/utilizadores")

@app.route("/utilizadores/<int:uid>/<acao>", methods=["POST"])
@papel("admin")
def utilizador_acao(uid, acao):
    x = q1("SELECT * FROM utilizador WHERE id=?", (uid,)) or abort(404)
    ultimo = x["perfil"] == "admin" and x["ativo"] and n_admins(uid) == 0
    if acao in NIVEL:
        if ultimo and acao != "admin": flash("Tem de existir pelo menos um administrador ativo.")
        else: db().execute("UPDATE utilizador SET perfil=? WHERE id=?", (acao, uid)); flash("Perfil alterado.")
    elif acao == "ativar":
        if x["ativo"] and (uid == atual()["id"] or ultimo): flash("Não podes desativar esta conta.")
        else: db().execute("UPDATE utilizador SET ativo=? WHERE id=?", (0 if x["ativo"] else 1, uid)); flash("Estado da conta alterado.")
    elif acao == "repor":
        pw = pw_temp()
        db().execute("UPDATE utilizador SET hash=?, trocar_pw=1 WHERE id=?", (generate_password_hash(pw), uid))
        flash(f"Nova palavra-passe temporária de {x['login']}: {pw}")
    else: abort(404)
    db().commit(); return redirect("/utilizadores")

PATHS = {
 "list": '<path d="M4 6h16M4 12h16M4 18h16"/>', "plus": '<circle cx="12" cy="12" r="9"/><path d="M12 8v8M8 12h8"/>',
 "pie": '<path d="M21 12a9 9 0 1 1-9-9v9z"/>', "more": '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
 "kebab": '<circle cx="12" cy="5" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="12" cy="19" r="1.2"/>',
 "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>', "tag": '<path d="M4 7h16M4 12h16M4 17h10"/>',
 "users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
 "lock": '<rect x="4" y="10" width="16" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/>',
 "out": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/>',
 "up": '<path d="M7 14l5-5 5 5"/>', "down": '<path d="M6 9l6 6 6-6"/>', "back": '<path d="M15 5l-7 7 7 7"/>',
 "close": '<path d="M6 6l12 12M18 6L6 18"/>', "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
 "play": '<path d="M8 5.5v13l10.5-6.5z"/>', "x": '<path d="M6 6l12 12M18 6L6 18"/>',
 "arc": '<path d="M21 12a9 9 0 1 1-6.2-8.55"/>', "minus": '<path d="M6 12h12"/>',
}
EST_ICON = {"disponível": ("check", "#8fc9a6"), "em uso": ("play", "#9bb0c4"), "avariado": ("x", "#d98473"),
            "em reparação": ("arc", "#d4a95a"), "abatido": ("minus", "#8e8e93")}

def icone(n, tam=20):
    return Markup(f'<svg width="{tam}" height="{tam}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
                  f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{PATHS[n]}</svg>')

def eic(estado, tam=22):
    n, c = EST_ICON.get(estado, ("minus", "#8e8e93"))
    return Markup(f'<span class="ei" role="img" aria-label="{escape(estado)}" title="{escape(estado)}" style="color:{c}">{icone(n, tam)}</span>')

app.jinja_env.globals.update(ESTADOS=ESTADOS, icone=icone, eic=eic)

# --- Alterações futuras à base de dados ---
# Para acrescentar um campo/tabela: junta uma linha NO FIM desta lista (nunca edites nem apagues as antigas).
# Cada alteração é aplicada uma só vez, automaticamente, ao arrancar (no PC e no servidor).
MIGRACOES = [
    # "ALTER TABLE equipamento ADD COLUMN garantia_ate TEXT",
]

def migrar():
    v = db().execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRACOES[v:], start=v):
        db().execute(sql)
        db().execute(f"PRAGMA user_version={i + 1}")
    db().commit()

with app.app_context():
    db().executescript(SCHEMA)
    migrar()
    db().execute("INSERT OR IGNORE INTO config VALUES('secret',?)", (secrets.token_hex(32),))
    if not q1("SELECT 1 FROM utilizador"):   # 1.º arranque: cria o administrador (aproveita o PIN antigo, se existir)
        _h = q1("SELECT valor FROM config WHERE chave='pin'")
        _h = _h["valor"] if _h else generate_password_hash("1234")
        db().execute("INSERT INTO utilizador(nome,login,hash,perfil,trocar_pw) VALUES('Administrador','admin',?,'admin',?)",
                     (_h, int(check_password_hash(_h, "1234"))))
    # Esqueceste a palavra-passe do admin? Cria um ficheiro vazio "repor-admin.txt" ao lado do programa e reinicia: fica admin / 1234.
    _rep = os.path.join(PASTA, "repor-admin.txt")
    if os.path.exists(_rep):
        db().execute("UPDATE utilizador SET hash=?, perfil='admin', ativo=1, trocar_pw=1 WHERE login='admin'", (generate_password_hash("1234"),))
        os.remove(_rep)
    db().commit()
    app.secret_key = os.environ.get("SECRET_KEY") or q1("SELECT valor FROM config WHERE chave='secret'")["valor"]

if __name__ == "__main__":
    print(f"\n  INVENTÁRIO a correr (fecha esta janela para parar)\n"
          f"  Neste PC:    http://localhost:{PORT}\n"
          f"  Telemóveis:  {BASE_URL}   (ligados ao mesmo Wi-Fi)\n")
    threading.Timer(1.2, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    app.run(host="0.0.0.0", port=PORT)
