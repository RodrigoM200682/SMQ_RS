"""
SMQ_RS — Sistema de Monitoramento de Qualidade RS
Persistência via GitHub API — salva dados_salvos.json no repositório.

Secrets necessários (Settings → Secrets no Streamlit Cloud):
  [github]
  token  = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  repo   = "seu-usuario/smq_rs"
  branch = "main"
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import re
import base64
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from io import BytesIO

# ── Caminhos ──────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent
HTML_FILE = BASE_DIR / "dashboard_rnc.html"
DATA_DIR  = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
LOCAL_DATA = DATA_DIR / "dados_salvos.json"
LOCAL_META = DATA_DIR / "meta.json"
GH_DATA    = "data/dados_salvos.json"
GH_META    = "data/meta.json"

# ── Página ────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SMQ_RS — Monitoramento de Qualidade",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.markdown("""
<style>
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  .stApp { background: #0f1117; }
</style>
""", unsafe_allow_html=True)


# ── Helpers GitHub ─────────────────────────────────────────────────────────────

def gh_cfg():
    """Retorna (token, repo, branch) ou (None, None, None)."""
    try:
        t = st.secrets["github"]["token"].strip()
        r = st.secrets["github"]["repo"].strip()
        b = st.secrets["github"].get("branch", "main").strip()
        if t and r and t.startswith("gh"):
            return t, r, b
    except Exception:
        pass
    return None, None, None


def gh_request(method: str, path: str, token: str, repo: str,
               branch: str, payload: dict | None = None):
    """
    Faz uma requisição à GitHub Contents API.
    Retorna (status_code, response_dict).
    """
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    if method == "GET":
        url += f"?ref={branch}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":    "SMQ_RS/1.3",
    }

    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = {}
        try:
            body = json.loads(e.read())
        except Exception:
            pass
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)}


def gh_read(path: str) -> tuple[str | None, str | None]:
    """
    Lê arquivo do GitHub.
    Retorna (conteúdo_str, sha) ou (None, None).
    """
    token, repo, branch = gh_cfg()
    if not token:
        return None, None

    status, body = gh_request("GET", path, token, repo, branch)

    if status == 200:
        try:
            content = base64.b64decode(
                body["content"].replace("\n", "")
            ).decode("utf-8")
            return content, body.get("sha")
        except Exception as e:
            return None, None
    elif status == 404:
        return None, None   # arquivo não existe ainda
    else:
        return None, None


def gh_write(path: str, content_str: str, commit_msg: str) -> tuple[bool, str]:
    """
    Cria ou atualiza arquivo no GitHub.
    Retorna (sucesso, mensagem_diagnóstico).
    """
    token, repo, branch = gh_cfg()
    if not token:
        return False, "Token GitHub não configurado."

    # Buscar SHA atual (obrigatório para update)
    _, sha = gh_read(path)

    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
    payload = {
        "message": commit_msg,
        "content": content_b64,
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    status, body = gh_request("PUT", path, token, repo, branch, payload)

    if status in (200, 201):
        return True, f"OK (status {status})"
    else:
        msg = body.get("message", str(body))
        return False, f"Erro {status}: {msg}"


# ── Persistência ───────────────────────────────────────────────────────────────

def salvar_dados(json_str: str, ts: str, n: int) -> dict:
    """
    Salva dados localmente e no GitHub.
    Retorna dict com resultado detalhado de cada etapa.
    """
    meta_str = json.dumps({"timestamp": ts, "n_records": n}, ensure_ascii=False)
    resultado = {"local": False, "github_data": False, "github_meta": False, "erros": []}

    # 1. Local
    try:
        LOCAL_DATA.write_text(json_str, encoding="utf-8")
        LOCAL_META.write_text(meta_str, encoding="utf-8")
        resultado["local"] = True
    except Exception as e:
        resultado["erros"].append(f"Local: {e}")

    # 2. GitHub — dados
    token, _, _ = gh_cfg()
    if token:
        ts_fmt = datetime.now().strftime("%Y-%m-%d %H:%M")
        ok, msg = gh_write(
            GH_DATA, json_str,
            f"SMQ_RS: dados atualizados — {n} registros — {ts_fmt}"
        )
        resultado["github_data"] = ok
        if not ok:
            resultado["erros"].append(f"GitHub dados: {msg}")

        # 3. GitHub — meta
        ok2, msg2 = gh_write(
            GH_META, meta_str,
            f"SMQ_RS: meta — {ts_fmt}"
        )
        resultado["github_meta"] = ok2
        if not ok2:
            resultado["erros"].append(f"GitHub meta: {msg2}")

    return resultado


def carregar_dados() -> tuple[str | None, str | None, int, str]:
    """
    Carrega dados persistidos.
    Ordem: GitHub → arquivo local → None.
    Retorna (json_str, timestamp, n_records, origem).
    """
    token, _, _ = gh_cfg()

    # 1. Tentar GitHub
    if token:
        json_str, _ = gh_read(GH_DATA)
        meta_str, _ = gh_read(GH_META)
        if json_str and meta_str:
            try:
                meta = json.loads(meta_str)
                # Atualizar cache local
                LOCAL_DATA.write_text(json_str, encoding="utf-8")
                LOCAL_META.write_text(meta_str, encoding="utf-8")
                return (json_str,
                        meta.get("timestamp", "—"),
                        int(meta.get("n_records", 0)),
                        "github")
            except Exception:
                pass

    # 2. Fallback local
    if LOCAL_DATA.exists() and LOCAL_META.exists():
        try:
            json_str = LOCAL_DATA.read_text(encoding="utf-8")
            meta     = json.loads(LOCAL_META.read_text(encoding="utf-8"))
            return (json_str,
                    meta.get("timestamp", "—"),
                    int(meta.get("n_records", 0)),
                    "local")
        except Exception:
            pass

    return None, None, 0, "nenhum"


# ── Conversão XLSX → JSON ──────────────────────────────────────────────────────

def xlsx_para_json(file_bytes: bytes) -> tuple[str | None, str]:
    """
    Converte bytes de planilha para JSON.
    Retorna (json_str, mensagem_erro).
    """
    try:
        df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]

        def achar_col(palavras):
            for p in palavras:
                for c in df.columns:
                    if p.lower() in c.lower():
                        return c
            return None

        col_cod = achar_col(["código","codigo"])
        col_tit = achar_col(["título","titulo"])
        col_st  = achar_col(["status"])
        col_sit = achar_col(["situação","situacao"])
        col_dt  = achar_col(["emissão","emissao","data"])
        col_rsp = achar_col(["responsável","responsavel"])
        col_cli = achar_col(["cliente"])
        col_rca = achar_col(["análise de causa","analise de causa"])
        col_mot = achar_col(["motivo"])
        col_qtd = achar_col(["quantidade"])
        col_trn = achar_col(["turno"])

        if not col_cod:
            return None, "Coluna 'Código' não encontrada. Verifique o formato da planilha."

        registros = []
        for _, row in df.iterrows():
            cod = str(row.get(col_cod, "")).strip()
            if not cod or cod == "nan":
                continue

            dt_str, ano, mes = "", None, None
            dt_val = row.get(col_dt) if col_dt else None
            if pd.notna(dt_val):
                try:
                    dt = pd.Timestamp(dt_val)
                    dt_str = dt.strftime("%Y-%m-%d")
                    ano, mes = int(dt.year), int(dt.month)
                except Exception:
                    pass

            trn = str(row.get(col_trn, "")) if col_trn else ""
            if "1" in trn and "2" in trn and "3" in trn:
                turno = "Múltiplos Turnos"
            elif "1" in trn:
                turno = "1° Turno"
            elif "2" in trn:
                turno = "2° Turno"
            elif "3" in trn:
                turno = "3° Turno"
            else:
                turno = "Não Informado"

            def safe(col):
                if not col: return ""
                v = row.get(col)
                return str(v).strip() if pd.notna(v) and str(v) != "nan" else ""

            registros.append({
                "codigo":            cod,
                "titulo":            safe(col_tit),
                "status":            safe(col_st),
                "situacao":          safe(col_sit),
                "data":              dt_str,
                "ano":               ano,
                "mes":               mes,
                "responsavel":       safe(col_rsp),
                "cliente":           safe(col_cli),
                "responsavel_causa": safe(col_rca),
                "motivo":            safe(col_mot),
                "qtd":               safe(col_qtd),
                "turno":             turno,
            })

        if not registros:
            return None, "Nenhum registro encontrado. Verifique se a planilha tem dados."

        return json.dumps(registros, ensure_ascii=False), ""

    except Exception as e:
        return None, f"Erro ao processar planilha: {e}"


# ── Injeção no HTML ────────────────────────────────────────────────────────────

_RE_DATA = re.compile(r"const RAW_DATA = \[.*?\];", re.DOTALL)

def montar_html(json_str: str, ts: str, n: int) -> str:
    html = HTML_FILE.read_text(encoding="utf-8")
    html = _RE_DATA.sub(f"const RAW_DATA = {json_str};", html)
    html = re.sub(r"\d+ registros carregados", f"{n} registros carregados", html)
    html = re.sub(
        r"(Base original[^<\"]*|Atualizado em [^<\"]*)",
        f"Atualizado em {ts}",
        html,
    )
    return html


# ── Inicialização ──────────────────────────────────────────────────────────────

if "init" not in st.session_state:
    st.session_state["init"]      = True
    st.session_state["dados"]     = None
    st.session_state["ts"]        = None
    st.session_state["n"]         = 0
    st.session_state["origem"]    = "nenhum"
    st.session_state["log"]       = []

    with st.spinner("Carregando dados..."):
        j, ts, n, origem = carregar_dados()

    if j:
        st.session_state["dados"]  = j
        st.session_state["ts"]     = ts
        st.session_state["n"]      = n
        st.session_state["origem"] = origem


# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔵 SMQ_RS")
    st.caption("Sistema de Monitoramento de Qualidade")
    st.divider()

    # Status dos dados
    origem = st.session_state.get("origem", "nenhum")
    if origem == "github":
        st.success("☁️ **Dados carregados do GitHub**")
    elif origem == "local":
        st.warning("💾 **Dados do cache local**\n\n(GitHub não respondeu ou não configurado)")
    else:
        st.info("📋 Usando dados originais do sistema.")

    if st.session_state.get("ts"):
        st.markdown(f"🕐 {st.session_state['ts']}")
        st.markdown(f"📋 {st.session_state['n']:,} registros")

    st.divider()

    # Status GitHub
    token, repo, branch = gh_cfg()
    if token:
        st.success(f"☁️ **GitHub configurado**\n\n`{repo}` · `{branch}`")
    else:
        with st.expander("⚠️ GitHub não configurado — clique para ver como configurar"):
            st.markdown("""
**Sem GitHub**, os dados só persistem enquanto o servidor não reiniciar.

**Para configurar:**
1. Crie um token em: github.com/settings/tokens
   - Tipo: **Classic**
   - Escopo: marque **`repo`**
2. No Streamlit Cloud, vá em **Settings → Secrets** e cole:

```toml
[github]
token  = "ghp_..."
repo   = "usuario/smq_rs"
branch = "main"
```
""")

    st.divider()
    st.markdown("### 📂 Atualizar Planilha")

    uploaded = st.file_uploader(
        "Arquivo .xlsx",
        type=["xlsx", "xls"],
        help="Mesmo formato da planilha Consultas_RNC_APP.xlsx",
    )

    if uploaded and st.button("⬆️ Processar e Salvar", type="primary"):
        log = []

        with st.spinner("Lendo planilha..."):
            j, erro = xlsx_para_json(uploaded.read())

        if not j:
            st.error(f"❌ {erro}")
        else:
            n   = j.count('"codigo"')
            ts  = datetime.now().strftime("%d/%m/%Y às %H:%M")
            log.append(f"✅ Planilha lida: {n} registros")

            with st.spinner("Salvando..."):
                res = salvar_dados(j, ts, n)

            if res["local"]:
                log.append("✅ Cache local: salvo")
            else:
                log.append("⚠️ Cache local: falhou")

            if token:
                if res["github_data"] and res["github_meta"]:
                    log.append("✅ GitHub: dados e meta salvos")
                elif res["github_data"]:
                    log.append("⚠️ GitHub: dados OK, meta falhou")
                    for e in res["erros"]:
                        if "meta" in e.lower():
                            log.append(f"   Detalhe: {e}")
                else:
                    log.append("❌ GitHub: falha ao salvar")
                    for e in res["erros"]:
                        log.append(f"   Detalhe: {e}")
            else:
                log.append("ℹ️ GitHub: não configurado (salvo só local)")

            st.session_state["dados"]  = j
            st.session_state["ts"]     = ts
            st.session_state["n"]      = n
            st.session_state["origem"] = "github" if (token and res["github_data"]) else "local"
            st.session_state["log"]    = log

            st.rerun()

    # Log da última operação
    if st.session_state.get("log"):
        st.divider()
        st.markdown("**Log da última atualização:**")
        for linha in st.session_state["log"]:
            st.caption(linha)

    st.divider()

    # Botão testar conexão GitHub
    if token and st.button("🔍 Testar conexão GitHub"):
        with st.spinner("Testando..."):
            status, body = gh_request("GET", "", token, repo, branch)
        if status == 200:
            st.success(f"✅ Conexão OK — repositório `{repo}` acessível.")
        else:
            st.error(f"❌ Erro {status}: {body.get('message', body)}")

    # Limpar dados
    if LOCAL_DATA.exists() or token:
        if st.button("🗑️ Limpar dados salvos", type="secondary"):
            LOCAL_DATA.unlink(missing_ok=True)
            LOCAL_META.unlink(missing_ok=True)
            for k in ["dados","ts","n","origem","log"]:
                st.session_state[k] = None if k not in ("n",) else 0
            st.session_state["origem"] = "nenhum"
            st.session_state["log"]    = []
            st.rerun()

    st.divider()
    st.caption("SMQ_RS v1.3 · Streamlit + Chart.js")


# ── Renderizar dashboard ───────────────────────────────────────────────────────

if st.session_state.get("dados"):
    html = montar_html(
        st.session_state["dados"],
        st.session_state["ts"],
        st.session_state["n"],
    )
else:
    html = HTML_FILE.read_text(encoding="utf-8")

components.html(html, height=980, scrolling=True)
