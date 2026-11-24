#!/usr/bin/env python3
"""FarmaEstoque: servidor + banco SQLite (so biblioteca padrao do Python)."""
import hashlib, json, os, re, secrets, smtplib, sqlite3, ssl, sys, threading, time, unicodedata, webbrowser
from email.message import EmailMessage
from contextlib import contextmanager
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PASTA = os.path.dirname(os.path.abspath(__file__))
BANCO = os.path.join(PASTA, "farmacia.db")
SESSOES = {}
SQL = """
CREATE TABLE IF NOT EXISTS usuarios(id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
  senha_hash TEXT NOT NULL, perfil TEXT NOT NULL DEFAULT 'operador' CHECK(perfil IN ('admin','operador')));
CREATE TABLE IF NOT EXISTS produtos(id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, codigo_barras TEXT UNIQUE,
  categoria TEXT, laboratorio TEXT, validade TEXT, receita INTEGER NOT NULL DEFAULT 0,
  preco_compra REAL NOT NULL DEFAULT 0, preco_venda REAL NOT NULL DEFAULT 0,
  estoque_atual INTEGER NOT NULL DEFAULT 0 CHECK(estoque_atual >= 0), estoque_minimo INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS vendas(id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  usuario_id INTEGER NOT NULL, total REAL NOT NULL, forma TEXT NOT NULL, pago REAL NOT NULL, troco REAL NOT NULL DEFAULT 0, txid TEXT);
CREATE TABLE IF NOT EXISTS venda_itens(venda_id INTEGER NOT NULL REFERENCES vendas(id), produto_id INTEGER NOT NULL,
  nome TEXT NOT NULL, qtd INTEGER NOT NULL, preco REAL NOT NULL, custo REAL NOT NULL);
CREATE TABLE IF NOT EXISTS config(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS recuperacao(usuario_id INTEGER PRIMARY KEY, codigo_hash TEXT NOT NULL, sal TEXT NOT NULL,
  expira REAL NOT NULL, tentativas INTEGER NOT NULL DEFAULT 0, criado REAL NOT NULL);
"""
FORMAS = ("dinheiro", "pix", "debito", "credito")
EXEMPLOS = [("Dipirona 500mg c/10 comp","7890000000011","Medicamentos","Generico Lab",0,3.2,6.9,40,10),
 ("Paracetamol 750mg c/20 comp","7890000000028","Medicamentos","Generico Lab",0,5.1,11.5,60,10),
 ("Ibuprofeno 600mg c/10 comp","7890000000035","Medicamentos","Bem Estar",0,7.8,16.9,25,8),
 ("Amoxicilina 500mg c/21 caps","7890000000042","Antibioticos","Saude Lab",1,19,39.9,18,5),
 ("Losartana 50mg c/30 comp","7890000000059","Medicamentos","Cardio Lab",1,8.5,17.5,30,8),
 ("Soro Fisiologico 500ml","7890000000066","Higiene","Vida Farma",0,2.9,6.5,50,12),
 ("Vitamina C 1g c/10 efervescentes","7890000000073","Vitaminas","Nutri+",0,9.5,21.9,22,6),
 ("Protetor Solar FPS 50 120ml","7890000000080","Dermocosmeticos","Sol & Pele",0,28,59.9,12,4),
 ("Alcool em Gel 70% 500ml","7890000000097","Higiene","Vida Farma",0,6,12.9,35,10),
 ("Fralda Infantil M c/30","7890000000103","Infantil","Baby Care",0,32,59.9,3,5),
 ("Omeprazol 20mg c/28 caps","7890000000110","Medicamentos","Generico Lab",0,6.4,14.9,45,10),
 ("Termometro Digital","7890000000127","Materiais","MedTech",0,11,24.9,9,3)]

class Erro(Exception):
    def __init__(s, cod, msg): s.cod, s.msg = cod, msg

@contextmanager
def tx():
    c = sqlite3.connect(BANCO); c.row_factory = sqlite3.Row; c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c; c.commit()
    except Exception:
        c.rollback(); raise
    finally:
        c.close()

def hash_senha(s, sal=None):
    sal = sal or secrets.token_hex(8)
    return sal + "$" + hashlib.pbkdf2_hmac("sha256", s.encode(), sal.encode(), 120000).hex()
def confere(s, g): return secrets.compare_digest(hash_senha(s, g.split("$")[0]), g)
def num(v, campo):
    try: n = float(v if v not in (None, "") else 0)
    except (TypeError, ValueError): raise Erro(400, f"{campo} invalido.")
    if n < 0: raise Erro(400, f"{campo} nao pode ser negativo.")
    return n
def sessao(uid, nome, perfil, email=""):
    t = secrets.token_hex(24); SESSOES[t] = {"id": uid, "nome": nome, "perfil": perfil, "email": email or "", "ate": time.time() + 43200}
    return {"token": t, "usuario": {"id": uid, "nome": nome, "perfil": perfil, "email": email or ""}}
def cred(b):
    nome, senha = (b.get("nome") or "").strip(), b.get("senha") or ""
    if not nome: raise Erro(400, "Informe o nome do usuario.")
    return nome, senha
def senha_ok(s):
    if len(s) < 4: raise Erro(400, "A senha precisa ter pelo menos 4 caracteres.")
def admin(me):
    if me["perfil"] != "admin": raise Erro(403, "Apenas administradores podem fazer isso.")

def dados_produto(b):
    nome = (b.get("nome") or "").strip()
    if not nome: raise Erro(400, "Informe o nome do produto.")
    val = (b.get("validade") or "").strip() or None
    if val:
        try: date.fromisoformat(val)
        except ValueError: raise Erro(400, "Validade invalida.")
    return (nome, (b.get("codigo_barras") or "").strip() or None, (b.get("categoria") or "").strip() or None,
            (b.get("laboratorio") or "").strip() or None, val, 1 if b.get("receita") in (1, "1", True, "on") else 0,
            num(b.get("preco_compra"), "Preco de compra"), num(b.get("preco_venda"), "Preco de venda"),
            int(num(b.get("estoque_atual"), "Estoque")), int(num(b.get("estoque_minimo"), "Estoque minimo")))
INS = "INSERT INTO produtos(nome,codigo_barras,categoria,laboratorio,validade,receita,preco_compra,preco_venda,estoque_atual,estoque_minimo) VALUES(?,?,?,?,?,?,?,?,?,?)"

def conferir_itens(c, itens, receita_ok=False):
    """Valida estoque/validade/receita e devolve (linhas, total) com precos do banco."""
    if not itens: raise Erro(400, "Nenhum item na venda.")
    linhas, total, hoje, juntos = [], 0.0, date.today().isoformat(), {}
    for it in itens:
        q = int(num(it.get("quantidade"), "Quantidade"))
        if q <= 0: raise Erro(400, "Quantidade invalida.")
        juntos[int(it.get("produto_id"))] = juntos.get(int(it.get("produto_id")), 0) + q
    for pid, q in juntos.items():
        p = c.execute("SELECT * FROM produtos WHERE id=?", (pid,)).fetchone()
        if not p: raise Erro(404, "Produto nao encontrado.")
        if p["validade"] and p["validade"] < hoje: raise Erro(400, f"{p['nome']} esta VENCIDO e nao pode ser vendido.")
        if q > p["estoque_atual"]: raise Erro(400, f"Estoque insuficiente de {p['nome']}: ha {p['estoque_atual']}.")
        if p["receita"] and not receita_ok: raise Erro(400, f"{p['nome']} exige receita. Confirme a conferencia da receita.")
        linhas.append((p, q)); total += round(p["preco_venda"] * q, 2)
    return linhas, round(total, 2)

def tlv(i, v): return f"{i}{len(v):02d}{v}"
def crc16(s):
    crc = 0xFFFF
    for b in s.encode():
        crc ^= b << 8
        for _ in range(8): crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"
def limpa(s, n):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    return "".join(ch for ch in s if ch.isalnum() or ch == " ").strip()[:n]
def pix_payload(chave, nome, cidade, valor, txid):
    p = (tlv("00", "01") + tlv("01", "11") + tlv("26", tlv("00", "br.gov.bcb.pix") + tlv("01", chave)) + tlv("52", "0000")
         + tlv("53", "986") + tlv("54", f"{valor:.2f}") + tlv("58", "BR") + tlv("59", limpa(nome, 25) or "FARMACIA")
         + tlv("60", limpa(cidade, 15) or "BRASIL") + tlv("62", tlv("05", txid)) + "6304")
    return p + crc16(p)

def cfg(c): return {r["k"]: r["v"] for r in c.execute("SELECT * FROM config")}


# ---------- configuracoes: o que cada perfil pode ver/alterar ----------
# PUB: aparece ate na tela de login (sem senha). PRIV: so administrador.
PUB = ("loja", "logo", "login_fundo", "login_cor_fundo", "login_escurecer", "login_desfoque", "login_logo", "login_logo_tam",
       "login_titulo", "login_subtitulo", "login_rotulo_usuario", "login_rotulo_senha", "login_botao", "login_cor_botao",
       "login_cor_cartao", "login_cor_texto", "login_raio", "login_largura", "login_posicao", "login_mostrar_recuperar",
       "login_texto_recuperar", "login_rodape", "login_cor_rodape")
PRIV = ("pix_chave", "pix_nome", "pix_cidade", "smtp_host", "smtp_porta", "smtp_seguranca", "smtp_usuario", "smtp_senha", "smtp_remetente")
COR = {"login_cor_fundo", "login_cor_botao", "login_cor_cartao", "login_cor_texto", "login_cor_rodape"}
IMG = {"logo", "login_logo", "login_fundo"}
NUM = {"login_escurecer": (0, 90), "login_desfoque": (0, 20), "login_logo_tam": (20, 160), "login_raio": (0, 40),
       "login_largura": (300, 600), "smtp_porta": (1, 65535)}
ENUM = {"login_posicao": ("centro", "esquerda", "direita"), "login_mostrar_recuperar": ("0", "1"), "smtp_seguranca": ("ssl", "starttls", "nenhuma")}

def valida_cfg(k, v):
    if v == "": return v
    if k in COR and not re.fullmatch(r"#[0-9a-fA-F]{6}", v): raise Erro(400, "Cor invalida.")
    if k in IMG:
        if len(v) > 3_000_000 or not re.fullmatch(r"data:image/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/=]+", v): raise Erro(400, "Imagem invalida ou grande demais.")
        return v
    if k in NUM:
        try: n = int(float(v))
        except ValueError: raise Erro(400, "Numero invalido.")
        lo, hi = NUM[k]; return str(min(hi, max(lo, n)))
    if k in ENUM and v not in ENUM[k]: raise Erro(400, "Opcao invalida.")
    return "".join(ch for ch in v if ch.isprintable())[:200]

def email_ok(v, obrigatorio=False):
    v = (v or "").strip().lower()
    if not v:
        if obrigatorio: raise Erro(400, "Informe um e-mail valido (usado na recuperacao de senha).")
        return None
    if len(v) > 120 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v): raise Erro(400, "E-mail invalido.")
    return v
def email_livre(c, email, ignorar=0):
    if email and c.execute("SELECT 1 FROM usuarios WHERE email=? AND id<>?", (email, ignorar)).fetchone(): raise Erro(409, "Este e-mail ja esta em uso.")

def smtp_ok(k): return bool(k.get("smtp_host") and (k.get("smtp_remetente") or k.get("smtp_usuario")))
def enviar_email(k, para, assunto, corpo):
    seg = k.get("smtp_seguranca") or "ssl"; porta = int(k.get("smtp_porta") or (465 if seg == "ssl" else 587))
    m = EmailMessage(); m["Subject"] = assunto; m["From"] = k.get("smtp_remetente") or k.get("smtp_usuario"); m["To"] = para; m.set_content(corpo)
    ctx = ssl.create_default_context()
    s = smtplib.SMTP_SSL(k["smtp_host"], porta, timeout=15, context=ctx) if seg == "ssl" else smtplib.SMTP(k["smtp_host"], porta, timeout=15)
    try:
        if seg == "starttls": s.starttls(context=ctx)
        if k.get("smtp_usuario"): s.login(k["smtp_usuario"], k.get("smtp_senha", ""))
        s.send_message(m)
    finally:
        try: s.quit()
        except Exception: pass

def entregar_codigo(k, email, nome, cod):
    corpo = f"Ola, {nome}.\n\nSeu codigo para redefinir a senha do FarmaEstoque: {cod}\nEle vale por 15 minutos. Se voce nao pediu, ignore este e-mail."
    if smtp_ok(k):
        try: enviar_email(k, email, "Codigo de recuperacao de senha", corpo); return
        except Exception as e: print(f"[recuperacao] Falha ao enviar e-mail: {e}")
    print(f"\n==== RECUPERACAO DE SENHA ====\nUsuario: {nome} ({email})\nCodigo: {cod}  (vale 15 minutos)\n==============================\n", flush=True)

def recuperar(acao, b):
    email = (b.get("email") or "").strip().lower(); falha = False
    with tx() as c:
        k = cfg(c)
        u = c.execute("SELECT id, nome FROM usuarios WHERE email=? AND perfil='admin'", (email,)).fetchone() if email else None
        if acao == "solicitar":
            if u:
                ant = c.execute("SELECT criado FROM recuperacao WHERE usuario_id=?", (u["id"],)).fetchone()
                if not ant or time.time() - ant["criado"] > 60:
                    cod, sal = f"{secrets.randbelow(10**6):06d}", secrets.token_hex(8)
                    c.execute("INSERT INTO recuperacao VALUES(?,?,?,?,0,?) ON CONFLICT(usuario_id) DO UPDATE SET codigo_hash=excluded.codigo_hash, sal=excluded.sal, expira=excluded.expira, tentativas=0, criado=excluded.criado",
                              (u["id"], hashlib.sha256((sal + cod).encode()).hexdigest(), sal, time.time() + 900, time.time()))
                    threading.Thread(target=entregar_codigo, args=(dict(k), email, u["nome"], cod), daemon=True).start()
            return {"ok": True, "console": not smtp_ok(k)}   # resposta igual exista o e-mail ou nao
        if acao != "confirmar": raise Erro(404, "Rota nao encontrada.")
        senha, cod = b.get("senha") or "", (b.get("codigo") or "").strip(); senha_ok(senha)
        row = c.execute("SELECT * FROM recuperacao WHERE usuario_id=?", (u["id"],)).fetchone() if u else None
        if not row or row["expira"] < time.time() or row["tentativas"] >= 5:
            if row: c.execute("DELETE FROM recuperacao WHERE usuario_id=?", (u["id"],))
            falha = True
        elif not secrets.compare_digest(hashlib.sha256((row["sal"] + cod).encode()).hexdigest(), row["codigo_hash"]):
            c.execute("UPDATE recuperacao SET tentativas=tentativas+1 WHERE usuario_id=?", (u["id"],)); falha = True
        else:
            c.execute("UPDATE usuarios SET senha_hash=? WHERE id=?", (hash_senha(senha), u["id"]))
            c.execute("DELETE FROM recuperacao WHERE usuario_id=?", (u["id"],))
            for t in [t for t, s in SESSOES.items() if s["id"] == u["id"]]: del SESSOES[t]
    if falha: raise Erro(400, "Codigo invalido ou expirado.")   # fora do with: assim a contagem de tentativas e gravada
    return {"ok": True}

def api(m, p, q, b, token):
    pt = p.strip("/").split("/"); r = pt[0]
    if r == "status" and m == "GET":
        with tx() as c: return {"primeiro_acesso": c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0}
    if r == "primeiro-usuario" and m == "POST":
        with tx() as c:
            if c.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]: raise Erro(403, "Ja existe um usuario cadastrado.")
            nome, senha = cred(b); senha_ok(senha); email = email_ok(b.get("email"), True)
            cur = c.execute("INSERT INTO usuarios(nome,senha_hash,perfil,email) VALUES(?,?,'admin',?)", (nome, hash_senha(senha), email))
            return sessao(cur.lastrowid, nome, "admin", email)
    if r == "login" and m == "POST":
        nome, senha = cred(b)
        with tx() as c: u = c.execute("SELECT * FROM usuarios WHERE nome=? OR email=lower(?) ORDER BY nome=? COLLATE NOCASE DESC", (nome, nome, nome)).fetchone()
        if not u or not confere(senha, u["senha_hash"]):
            time.sleep(0.6); raise Erro(401, "Nome ou senha incorretos.")
        return sessao(u["id"], u["nome"], u["perfil"], u["email"])
    if r == "recuperar" and m == "POST" and len(pt) > 1: return recuperar(pt[1], b)
    me = SESSOES.get(token)
    valida = bool(me) and me["ate"] >= time.time()
    if r == "config" and m == "GET" and not valida:
        # tela de login precisa do visual ANTES do login: so campos publicos (PIX e e-mail nunca saem daqui)
        with tx() as c:
            k = cfg(c)
            return {x: k[x] for x in PUB if x in k}
    if not valida: raise Erro(401, "Sessao expirada. Entre novamente.")
    if r == "me": return {k: me[k] for k in ("id", "nome", "perfil", "email")}
    if r == "config" and len(pt) > 1 and pt[1] == "testar-email" and m == "POST":
        admin(me)
        with tx() as c: k = cfg(c)
        para = email_ok(b.get("para"), True)
        if not smtp_ok(k): raise Erro(400, "Preencha e salve servidor SMTP e remetente primeiro.")
        try: enviar_email(k, para, "Teste FarmaEstoque", "Se voce recebeu este e-mail, o envio esta funcionando.")
        except Exception as e: raise Erro(400, f"Falha ao enviar: {e}")
        return {"ok": True}
    with tx() as c:
        if r == "produtos":
            if len(pt) == 1 and m == "GET": return [dict(x) for x in c.execute("SELECT * FROM produtos ORDER BY nome COLLATE NOCASE")]
            if len(pt) == 1 and m == "POST": return {"id": c.execute(INS, dados_produto(b)).lastrowid}
            if pt[1] == "exemplo" and m == "POST":
                admin(me)
                for e in EXEMPLOS:
                    v = (date.today() + timedelta(days=400 if e[0].startswith("Soro") is False else 25)).isoformat()
                    c.execute("INSERT OR IGNORE INTO produtos(nome,codigo_barras,categoria,laboratorio,validade,receita,preco_compra,preco_venda,estoque_atual,estoque_minimo) VALUES(?,?,?,?,?,?,?,?,?,?)", (e[0], e[1], e[2], e[3], v, e[4], e[5], e[6], e[7], e[8]))
                return {"ok": True}
            pid = int(pt[1])
            if m == "PUT":
                c.execute("UPDATE produtos SET nome=?,codigo_barras=?,categoria=?,laboratorio=?,validade=?,receita=?,preco_compra=?,preco_venda=?,estoque_atual=?,estoque_minimo=? WHERE id=?", dados_produto(b) + (pid,)); return {"ok": True}
            if m == "DELETE":
                admin(me)
                if c.execute("SELECT 1 FROM venda_itens WHERE produto_id=?", (pid,)).fetchone(): raise Erro(409, "Produto com vendas registradas nao pode ser excluido.")
                c.execute("DELETE FROM produtos WHERE id=?", (pid,)); return {"ok": True}
        if r == "pix" and m == "POST":
            k = cfg(c)
            if not k.get("pix_chave"): raise Erro(400, "Cadastre a chave PIX em Configuracoes (administrador).")
            _, total = conferir_itens(c, b.get("itens", []), True)
            txid = "FARMA" + secrets.token_hex(8).upper()
            return {"payload": pix_payload(k["pix_chave"], k.get("pix_nome", ""), k.get("pix_cidade", ""), total, txid), "txid": txid, "total": total}
        if r == "venda" and m == "POST":
            forma = b.get("forma")
            if forma not in FORMAS: raise Erro(400, "Forma de pagamento invalida.")
            linhas, total = conferir_itens(c, b.get("itens", []), bool(b.get("receita_ok")))
            pago = total if forma != "dinheiro" else round(num(b.get("pago"), "Valor pago"), 2)
            if pago < total: raise Erro(400, "Valor pago menor que o total.")
            troco = round(pago - total, 2)
            vid = c.execute("INSERT INTO vendas(usuario_id,total,forma,pago,troco,txid) VALUES(?,?,?,?,?,?)", (me["id"], total, forma, pago, troco, b.get("txid") if forma == "pix" else None)).lastrowid
            for p, qn in linhas:
                c.execute("UPDATE produtos SET estoque_atual=estoque_atual-? WHERE id=?", (qn, p["id"]))
                c.execute("INSERT INTO venda_itens VALUES(?,?,?,?,?,?)", (vid, p["id"], p["nome"], qn, p["preco_venda"], p["preco_compra"]))
            return {"id": vid, "total": total, "troco": troco}
        if r == "venda" and m == "GET" and len(pt) > 1:
            vid = int(pt[1])
            v = c.execute("SELECT v.*, u.nome operador FROM vendas v JOIN usuarios u ON u.id=v.usuario_id WHERE v.id=?", (vid,)).fetchone()
            if not v: raise Erro(404, "Venda nao encontrada.")
            itens = [dict(x) for x in c.execute("SELECT * FROM venda_itens WHERE venda_id=?", (vid,))]
            return {"venda": dict(v), "itens": itens}
        if r == "vendas" and m == "GET":
            ini, fim = (q.get("ini") or [""])[0], (q.get("fim") or [""])[0]
            v = [dict(x) for x in c.execute("""SELECT v.*, u.nome operador, (SELECT COALESCE(SUM(qtd*custo),0) FROM venda_itens WHERE venda_id=v.id) custo
              FROM vendas v JOIN usuarios u ON u.id=v.usuario_id WHERE date(v.data)>=? AND date(v.data)<=? ORDER BY v.id DESC LIMIT 500""", (ini or "2000-01-01", fim or "2999-12-31"))]
            por = {f: sum(x["total"] for x in v if x["forma"] == f) for f in FORMAS}
            tot = sum(x["total"] for x in v); custo = sum(x["custo"] for x in v)
            return {"vendas": v, "por_forma": por, "total": tot, "lucro": tot - custo, "n": len(v)}
        if r == "resumo" and m == "GET":
            hoje = date.today(); lim = (hoje + timedelta(days=90)).isoformat()
            t = c.execute("SELECT COUNT(*) n, COALESCE(SUM(estoque_atual*preco_compra),0) custo FROM produtos").fetchone()
            vh = c.execute("SELECT COALESCE(SUM(total),0) t, COUNT(*) n FROM vendas WHERE date(data)=date('now','localtime')").fetchone()
            return {"produtos": t["n"], "custo": t["custo"], "vendas_hoje": vh["t"], "n_hoje": vh["n"],
                    "baixos": [dict(x) for x in c.execute("SELECT * FROM produtos WHERE estoque_atual<=estoque_minimo ORDER BY estoque_atual LIMIT 8")],
                    "vencendo": [dict(x) for x in c.execute("SELECT * FROM produtos WHERE validade IS NOT NULL AND validade<=? ORDER BY validade LIMIT 8", (lim,))], "hoje": hoje.isoformat()}
        if r == "config":
            if m == "GET":
                k = cfg(c)
                if me["perfil"] != "admin": return {x: k[x] for x in PUB if x in k}   # operador: so loja/logo/visual
                k["smtp_senha_definida"] = "1" if k.get("smtp_senha") else ""; k.pop("smtp_senha", None)
                return k
            admin(me)
            for k in PUB + PRIV:
                if k not in b: continue
                v = "" if b[k] is None else str(b[k]).strip()
                if k == "smtp_senha" and not v: continue          # em branco = manter a senha atual
                c.execute("INSERT INTO config VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, valida_cfg(k, v)))
            return {"ok": True}
        if r == "usuarios":
            if m == "GET":
                ad = me["perfil"] == "admin"
                return [{"id": x["id"], "nome": x["nome"], "perfil": x["perfil"], **({"email": x["email"] or ""} if ad else {})} for x in c.execute("SELECT * FROM usuarios ORDER BY nome")]
            admin(me)
            if m == "POST":
                nome, senha = cred(b); senha_ok(senha); perfil = "admin" if b.get("perfil") == "admin" else "operador"
                email = email_ok(b.get("email"), perfil == "admin"); email_livre(c, email)
                c.execute("INSERT INTO usuarios(nome,senha_hash,perfil,email) VALUES(?,?,?,?)", (nome, hash_senha(senha), perfil, email)); return {"ok": True}
            if m == "PUT":
                uid = int(pt[1]); u = c.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
                if not u: raise Erro(404, "Usuario nao encontrado.")
                if "email" in b:
                    email = email_ok(b.get("email"), u["perfil"] == "admin"); email_livre(c, email, uid)
                    c.execute("UPDATE usuarios SET email=? WHERE id=?", (email, uid))
                    for s_ in SESSOES.values():
                        if s_["id"] == uid: s_["email"] = email or ""
                if b.get("senha"):
                    senha_ok(b["senha"]); c.execute("UPDATE usuarios SET senha_hash=? WHERE id=?", (hash_senha(b["senha"]), uid))
                    for t in [t for t, s_ in SESSOES.items() if s_["id"] == uid and t != token]: del SESSOES[t]
                return {"ok": True}
            if m == "DELETE":
                uid = int(pt[1])
                if uid == me["id"]: raise Erro(400, "Voce nao pode remover o proprio usuario.")
                if c.execute("SELECT 1 FROM vendas WHERE usuario_id=?", (uid,)).fetchone(): raise Erro(409, "Usuario com vendas registradas nao pode ser removido.")
                c.execute("DELETE FROM usuarios WHERE id=?", (uid,)); return {"ok": True}
    raise Erro(404, "Rota nao encontrada.")

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def enviar(self, cod, corpo, tipo="application/json"):
        if not isinstance(corpo, bytes): corpo = json.dumps(corpo, ensure_ascii=False).encode()
        self.send_response(cod); self.send_header("Content-Type", tipo + "; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo))); self.end_headers(); self.wfile.write(corpo)
    
    def tratar(self, m):
        u = urlparse(self.path)
        if m == "GET" and u.path in ("/", "/index.html"):
            with open(os.path.join(getattr(sys, "_MEIPASS", PASTA), "index.html"), "rb") as f: return self.enviar(200, f.read(), "text/html")
        if not u.path.startswith("/api/"): return self.enviar(404, {"erro": "Nao encontrado."})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            try: b = json.loads(self.rfile.read(n) or b"{}")
            except ValueError: b = {}
            
            # --- INÍCIO DA PROTEÇÃO CONTRA ERRO DE CONEXÃO ---
            try:
                self.enviar(200, api(m, u.path[5:], parse_qs(u.query), b if isinstance(b, dict) else {}, self.headers.get("Authorization", "")[7:]))
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                # Ignora silenciosamente se o navegador fechou a conexão (ex: apertou F5 ou fechou a aba)
                pass
            # --- FIM DA PROTEÇÃO ---
            
        except Erro as e: self.enviar(e.cod, {"erro": e.msg})
        except sqlite3.IntegrityError: self.enviar(409, {"erro": "Ja existe um registro com esse codigo de barras ou nome."})
        except (ValueError, IndexError, TypeError): self.enviar(400, {"erro": "Requisicao invalida."})
        except Exception as e: self.enviar(500, {"erro": f"Erro interno: {e}"})
    def do_GET(self): self.tratar("GET")
    def do_POST(self): self.tratar("POST")
    def do_PUT(self): self.tratar("PUT")
    def do_DELETE(self): self.tratar("DELETE")

if __name__ == "__main__":
    with tx() as c:
        c.executescript(SQL)
        if "email" not in [x[1] for x in c.execute("PRAGMA table_info(usuarios)")]: c.execute("ALTER TABLE usuarios ADD COLUMN email TEXT")
    host, porta = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORTA", 8000))
    url = f"http://{'127.0.0.1' if host == '0.0.0.0' else host}:{porta}"
    print(f"FarmaEstoque rodando em {url}  (Ctrl+C para parar)\nBanco de dados: {BANCO}")
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try: ThreadingHTTPServer((host, porta), H).serve_forever()
    except KeyboardInterrupt: print("\nServidor encerrado.")