"""
SMQ_RS v1.4 — Diagnóstico completo de persistência
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json, re, base64, time
import urllib.request, urllib.error
from datetime import datetime
from pathlib import Path
from io import BytesIO

# ── Caminhos ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
HTML_FILE  = BASE_DIR / "dashboard_rnc.html"
DATA_DIR   = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
LOCAL_JSON = DATA_DIR / "dados_salvos.json"
LOCAL_META = DATA_DIR / "meta.json"

# ── Página ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SMQ_RS",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown("""
<style>
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  .stApp { background: #0f1117; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# GITHUB
# ══════════════════════════════════════════════════════════════════════════════

def get_cfg():
    """Lê token/repo/branch dos secrets. Retorna (token,repo,branch) ou erros."""
    erros = []
    token = repo = branch = None
    try:
        token  = str(st.secrets["github"]["token"]).strip()
        repo   = str(st.secrets["github"]["repo"]).strip()
        branch = str(st.secrets["github"].get("branch", "main")).strip()
    except KeyError as e:
        erros.append(f"Secret ausente: {e}")
    except Exception as e:
        erros.append(f"Erro ao ler secrets: {e}")

    if token and not token.startswith(("ghp_", "github_pat_", "gho_", "ghu_")):
        erros.append(f"Token parece inválido (não começa com ghp_ etc): '{token[:10]}...'")
    if repo and "/" not in repo:
        erros.append(f"Repo deve ser 'usuario/repositorio', recebido: '{repo}'")

    return token, repo, branch, erros


def api_call(method: str, url: str, token: str,
             payload: dict | None = None) -> tuple[int, dict, str]:
    """
    Faz chamada HTTP à API do GitHub.
    Retorna (status, body_dict, erro_str).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":    "SMQ_RS/1.4",
        "Content-Type":  "application/json",
    }
    data = json.dumps(payload).encode() if payload else None
    req  = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or "{}"), ""
    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read())
        except Exception:
            pass
        return e.code, body, body.get("message", "")
    except Exception as e:
        return 0, {}, str(e)


def gh_ler(path: str, token: str, repo: str,
           branch: str) -> tuple[str | None, str | None, str]:
    """
    Lê arquivo do GitHub.
    Retorna (conteúdo, sha, erro).
    """
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    status, body, erro = api_call("GET", url, token)
    if status == 200:
        try:
            conteudo = base64.b64decode(
                body["content"].replace("\n", "")
            ).decode("utf-8")
            return conteudo, body.get("sha"), ""
        except Exception as e:
            return None, None, f"Erro ao decodificar: {e}"
    elif status == 404:
        return None, None, "404 — arquivo não existe ainda"
    else:
        return None, None, f"HTTP {status}: {erro or body}"


def gh_salvar(path: str, conteudo: str, mensagem: str,
              token: str, repo: str, branch: str) -> tuple[bool, str]:
    """
    Cria ou atualiza arquivo no GitHub.
    Retorna (sucesso, detalhe).
    """
    # Buscar SHA atual
    _, sha, _ = gh_ler(path, token, repo, branch)

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": mensagem,
        "content": base64.b64encode(conteudo.encode("utf-8")).decode("ascii"),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha   # necessário para UPDATE

    status, body, erro = api_call("PUT", url, token, payload)
    if status in (200, 201):
        commit = body.get("commit", {}).get("sha", "")[:7]
        return True, f"Salvo — commit {commit}"
    else:
        return False, f"HTTP {status}: {erro or body.get('message', str(body))}"


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSÃO XLSX
# ══════════════════════════════════════════════════════════════════════════════

def xlsx_para_json(file_bytes: bytes) -> tuple[str | None, int, str]:
    """
    Converte planilha para JSON.
    Retorna (json_str, n_registros, erro).
    """
    try:
        df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]

        def col(palavras):
            for p in palavras:
                for c in df.columns:
                    if p.lower() in c.lower():
                        return c
            return None

        c_cod = col(["código","codigo"])
        c_tit = col(["título","titulo"])
        c_st  = col(["status"])
        c_sit = col(["situação","situacao"])
        c_dt  = col(["emissão","emissao","data"])
        c_rsp = col(["responsável","responsavel"])
        c_cli = col(["cliente"])
        c_rca = col(["análise de causa","analise de causa"])
        c_mot = col(["motivo"])
        c_qtd = col(["quantidade"])
        c_trn = col(["turno"])

        if not c_cod:
            cols_encontradas = ", ".join(df.columns.tolist())
            return None, 0, (
                f"Coluna 'Código' não encontrada. "
                f"Colunas detectadas: {cols_encontradas}"
            )

        def safe(c):
            if not c: return ""
            v = row.get(c)
            return str(v).strip() if pd.notna(v) and str(v) != "nan" else ""

        registros = []
        for _, row in df.iterrows():
            cod = str(row.get(c_cod, "")).strip()
            if not cod or cod == "nan":
                continue

            dt_str, ano, mes = "", None, None
            dv = row.get(c_dt) if c_dt else None
            if pd.notna(dv):
                try:
                    dt = pd.Timestamp(dv)
                    dt_str = dt.strftime("%Y-%m-%d")
                    ano, mes = int(dt.year), int(dt.month)
                except Exception:
                    pass

            trn = str(row.get(c_trn, "")) if c_trn else ""
            if "1" in trn and "2" in trn and "3" in trn:
                turno = "Múltiplos Turnos"
            elif "1" in trn: turno = "1° Turno"
            elif "2" in trn: turno = "2° Turno"
            elif "3" in trn: turno = "3° Turno"
            else:            turno = "Não Informado"

            registros.append({
                "codigo": cod, "titulo": safe(c_tit),
                "status": safe(c_st), "situacao": safe(c_sit),
                "data": dt_str, "ano": ano, "mes": mes,
                "responsavel": safe(c_rsp), "cliente": safe(c_cli),
                "responsavel_causa": safe(c_rca),
                "motivo": safe(c_mot), "qtd": safe(c_qtd), "turno": turno,
            })

        if not registros:
            return None, 0, "Nenhum registro encontrado na planilha."

        return json.dumps(registros, ensure_ascii=False), len(registros), ""

    except Exception as e:
        return None, 0, f"Erro ao ler planilha: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTÊNCIA LOCAL
# ══════════════════════════════════════════════════════════════════════════════

def salvar_local(json_str: str, ts: str, n: int) -> tuple[bool, str]:
    try:
        LOCAL_JSON.write_text(json_str, encoding="utf-8")
        LOCAL_META.write_text(
            json.dumps({"timestamp": ts, "n_records": n}),
            encoding="utf-8"
        )
        return True, f"Salvo em {LOCAL_JSON}"
    except Exception as e:
        return False, str(e)


def carregar_local() -> tuple[str | None, str, int]:
    if LOCAL_JSON.exists() and LOCAL_META.exists():
        try:
            j    = LOCAL_JSON.read_text(encoding="utf-8")
            meta = json.loads(LOCAL_META.read_text(encoding="utf-8"))
            return j, meta.get("timestamp","—"), int(meta.get("n_records",0))
        except Exception:
            pass
    return None, "", 0


# ══════════════════════════════════════════════════════════════════════════════
# HTML
# ══════════════════════════════════════════════════════════════════════════════

_RE = re.compile(r"const RAW_DATA = \[.*?\];", re.DOTALL)

def montar_html(json_str: str, ts: str, n: int) -> str:
    html = HTML_FILE.read_text(encoding="utf-8")
    html = _RE.sub(f"const RAW_DATA = {json_str};", html)
    html = re.sub(r"\d+ registros carregados", f"{n} registros carregados", html)
    html = re.sub(
        r"(Base original[^<\"]*|Atualizado em [^<\"]*)",
        f"Atualizado em {ts}", html,
    )
    return html


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO — carrega dados ao iniciar
# ══════════════════════════════════════════════════════════════════════════════

if "init" not in st.session_state:
    st.session_state.update({
        "init": True, "json": None, "ts": None,
        "n": 0, "origem": "original", "ops_log": [],
    })

    token, repo, branch, erros_cfg = get_cfg()

    # 1. Tentar GitHub
    if token and not erros_cfg:
        j, _, erro = gh_ler("data/dados_salvos.json", token, repo, branch)
        m, _, _    = gh_ler("data/meta.json",         token, repo, branch)
        if j and m:
            try:
                meta = json.loads(m)
                st.session_state.update({
                    "json": j, "ts": meta.get("timestamp","—"),
                    "n": int(meta.get("n_records", 0)), "origem": "github",
                })
                salvar_local(j, meta.get("timestamp","—"),
                             int(meta.get("n_records",0)))
            except Exception:
                pass

    # 2. Fallback local
    if not st.session_state["json"]:
        j, ts, n = carregar_local()
        if j:
            st.session_state.update({
                "json": j, "ts": ts, "n": n, "origem": "local"
            })


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🔵 SMQ_RS")
    st.caption("Sistema de Monitoramento de Qualidade")
    st.divider()

    # ── Status atual ──────────────────────────────────────────────────────────
    origem = st.session_state.get("origem", "original")
    icons  = {"github": "☁️", "local": "💾", "original": "📋"}
    labels = {
        "github":   "Dados do GitHub ✅",
        "local":    "Cache local (GitHub offline ou não configurado)",
        "original": "Dados originais do sistema",
    }
    st.info(f"{icons.get(origem,'📋')} **{labels.get(origem,'')}**")
    if st.session_state.get("ts"):
        st.caption(f"🕐 {st.session_state['ts']}  ·  📋 {st.session_state['n']:,} registros")

    st.divider()

    # ── Diagnóstico GitHub ────────────────────────────────────────────────────
    st.markdown("### 🔍 Diagnóstico GitHub")
    token, repo, branch, erros_cfg = get_cfg()

    if erros_cfg:
        for e in erros_cfg:
            st.error(f"❌ {e}")
        with st.expander("Como configurar os secrets"):
            st.code("""
[github]
token  = "ghp_SEU_TOKEN_AQUI"
repo   = "seu-usuario/smq_rs"
branch = "main"
""", language="toml")
            st.caption("Cole isso em: Streamlit Cloud → seu app → Settings → Secrets")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Repo", repo.split("/")[-1] if repo else "—")
        with col2:
            st.metric("Branch", branch or "—")

        if st.button("🔌 Testar conexão", use_container_width=True):
            with st.spinner("Testando..."):
                url = f"https://api.github.com/repos/{repo}"
                status, body, erro = api_call("GET", url, token)
            if status == 200:
                st.success(f"✅ Repositório acessível: `{body.get('full_name')}`")
                priv = "privado" if body.get("private") else "público"
                st.caption(f"Tipo: {priv} · Default branch: {body.get('default_branch')}")
            elif status == 404:
                st.error("❌ Repositório não encontrado. Verifique o nome e se o token tem acesso.")
            elif status == 401:
                st.error("❌ Token inválido ou expirado. Gere um novo em github.com/settings/tokens")
            else:
                st.error(f"❌ Erro {status}: {erro}")

    st.divider()

    # ── Upload de planilha ────────────────────────────────────────────────────
    st.markdown("### 📂 Atualizar Planilha")
    arquivo = st.file_uploader("Selecione o .xlsx", type=["xlsx","xls"])

    if arquivo:
        st.caption(f"Arquivo: **{arquivo.name}** ({arquivo.size:,} bytes)")

        if st.button("⬆️ SALVAR PLANILHA", type="primary", use_container_width=True):
            log = []
            ts  = datetime.now().strftime("%d/%m/%Y às %H:%M")

            # Passo 1 — Ler planilha
            with st.spinner("Lendo planilha..."):
                j, n, erro = xlsx_para_json(arquivo.read())

            if not j:
                st.error(f"❌ {erro}")
                st.stop()

            log.append(f"✅ Planilha lida: {n} registros")
            st.toast(f"Planilha lida: {n} registros")

            # Passo 2 — Salvar local
            ok_local, det_local = salvar_local(j, ts, n)
            log.append(
                f"{'✅' if ok_local else '❌'} Local: {det_local}"
            )

            # Passo 3 — Salvar GitHub
            if token and not erros_cfg:
                with st.spinner("Salvando no GitHub..."):
                    ok_gh, det_gh = gh_salvar(
                        "data/dados_salvos.json", j,
                        f"SMQ_RS: {n} registros — {ts}",
                        token, repo, branch,
                    )
                log.append(f"{'✅' if ok_gh else '❌'} GitHub dados: {det_gh}")

                with st.spinner("Salvando meta no GitHub..."):
                    meta_str = json.dumps({"timestamp": ts, "n_records": n})
                    ok_m, det_m = gh_salvar(
                        "data/meta.json", meta_str,
                        f"SMQ_RS: meta — {ts}",
                        token, repo, branch,
                    )
                log.append(f"{'✅' if ok_m else '❌'} GitHub meta: {det_m}")

                if ok_gh:
                    st.balloons()
            else:
                log.append("ℹ️ GitHub: não configurado — apenas local")

            # Atualizar estado
            st.session_state.update({
                "json": j, "ts": ts, "n": n,
                "origem": "github" if (token and not erros_cfg and ok_gh) else "local",
                "ops_log": log,
            })
            st.rerun()

    # Log
    if st.session_state.get("ops_log"):
        st.divider()
        st.markdown("**Log da última operação:**")
        for linha in st.session_state["ops_log"]:
            if linha.startswith("✅"):
                st.success(linha, icon=None)
            elif linha.startswith("❌"):
                st.error(linha, icon=None)
            elif linha.startswith("⚠️"):
                st.warning(linha, icon=None)
            else:
                st.caption(linha)

    st.divider()

    # Limpar dados
    if st.button("🗑️ Limpar dados salvos", type="secondary",
                 help="Volta para os dados originais"):
        LOCAL_JSON.unlink(missing_ok=True)
        LOCAL_META.unlink(missing_ok=True)
        for k in ("json","ts","n","origem","ops_log","init"):
            st.session_state.pop(k, None)
        st.rerun()

    st.caption("SMQ_RS v1.4")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.get("json"):
    html = montar_html(
        st.session_state["json"],
        st.session_state["ts"],
        st.session_state["n"],
    )
else:
    html = HTML_FILE.read_text(encoding="utf-8")

components.html(html, height=980, scrolling=True)
