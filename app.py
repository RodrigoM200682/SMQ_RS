"""
SMQ_RS — Sistema de Monitoramento de Qualidade RS

Persistência via GitHub API:
  - Ao fazer upload de uma planilha, os dados são salvos como
    data/dados_salvos.json diretamente no repositório GitHub.
  - A cada reinício, o app lê esse arquivo do GitHub — garantindo
    persistência real mesmo no Streamlit Cloud (filesystem efêmero).

Configuração necessária (Streamlit Secrets):
  [github]
  token = "ghp_xxxxxxxxxxxxxxxxxxxx"   # Personal Access Token (repo scope)
  repo  = "seu-usuario/smq_rs"         # repositório no formato usuario/repo
  branch = "main"                      # branch onde salvar (padrão: main)

Deploy local: streamlit run app.py
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

# Arquivo local (cache / uso sem GitHub)
LOCAL_DATA = DATA_DIR / "dados_salvos.json"
LOCAL_META = DATA_DIR / "meta.json"

# Caminho no repositório GitHub
GITHUB_DATA_PATH = "data/dados_salvos.json"
GITHUB_META_PATH = "data/meta.json"

# ── Configuração da página ────────────────────────────────────────────────────
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


# ── GitHub API ────────────────────────────────────────────────────────────────

def _gh_secrets() -> tuple[str, str, str] | tuple[None, None, None]:
    """Retorna (token, repo, branch) dos secrets, ou (None,None,None)."""
    try:
        token  = st.secrets["github"]["token"]
        repo   = st.secrets["github"]["repo"]
        branch = st.secrets["github"].get("branch", "main")
        if token and repo:
            return token, repo, branch
    except Exception:
        pass
    return None, None, None


def _gh_get(path: str) -> dict | None:
    """GET /repos/{repo}/contents/{path} — retorna JSON ou None."""
    token, repo, branch = _gh_secrets()
    if not token:
        return None
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SMQ_RS",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None          # arquivo ainda não existe
        raise
    except Exception:
        return None


def _gh_put(path: str, content: str, message: str) -> bool:
    """
    Cria ou atualiza um arquivo no GitHub via PUT.
    content deve ser string UTF-8 (será codificada em base64).
    Retorna True se sucesso.
    """
    token, repo, branch = _gh_secrets()
    if not token:
        return False

    url = f"https://api.github.com/repos/{repo}/contents/{path}"

    # Buscar SHA atual (necessário para atualizar arquivo existente)
    existing = _gh_get(path)
    sha = existing.get("sha") if existing else None

    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": f"token {token}",
        "Accept":        "application/vnd.github.v3+json",
        "Content-Type":  "application/json",
        "User-Agent":    "SMQ_RS",
    })
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception as e:
        st.warning(f"GitHub: não foi possível salvar ({e}). Dados salvos apenas localmente.")
        return False


def _gh_read(path: str) -> str | None:
    """Lê conteúdo de um arquivo do GitHub e retorna como string."""
    info = _gh_get(path)
    if not info:
        return None
    try:
        return base64.b64decode(info["content"]).decode("utf-8")
    except Exception:
        return None


# ── Persistência ──────────────────────────────────────────────────────────────

def save_data(json_str: str, ts: str, n: int) -> None:
    """
    Salva dados:
      1. Localmente (sempre, como cache imediato)
      2. No GitHub (se configurado) — garante persistência no Streamlit Cloud
    """
    meta_str = json.dumps({"timestamp": ts, "n_records": n}, ensure_ascii=False)

    # 1. Local
    LOCAL_DATA.write_text(json_str, encoding="utf-8")
    LOCAL_META.write_text(meta_str, encoding="utf-8")

    # 2. GitHub
    token, _, _ = _gh_secrets()
    if token:
        ts_commit = datetime.now().strftime("%Y-%m-%d %H:%M")
        ok_data = _gh_put(GITHUB_DATA_PATH, json_str,
                          f"SMQ_RS: atualização de dados ({n} registros) — {ts_commit}")
        ok_meta = _gh_put(GITHUB_META_PATH, meta_str,
                          f"SMQ_RS: meta atualização — {ts_commit}")
        if ok_data and ok_meta:
            st.toast("✅ Dados sincronizados com GitHub", icon="☁️")


def load_saved_data() -> tuple[str | None, str | None, int]:
    """
    Carrega dados persistidos.
    Prioridade: GitHub (sempre atualizado) → local → None
    """
    token, _, _ = _gh_secrets()

    if token:
        # Tentar carregar do GitHub primeiro
        json_str = _gh_read(GITHUB_DATA_PATH)
        meta_str = _gh_read(GITHUB_META_PATH)
        if json_str and meta_str:
            try:
                meta = json.loads(meta_str)
                # Atualizar cache local com dados do GitHub
                LOCAL_DATA.write_text(json_str, encoding="utf-8")
                LOCAL_META.write_text(meta_str, encoding="utf-8")
                return json_str, meta.get("timestamp", "—"), meta.get("n_records", 0)
            except Exception:
                pass

    # Fallback: arquivo local
    if LOCAL_DATA.exists() and LOCAL_META.exists():
        try:
            json_str = LOCAL_DATA.read_text(encoding="utf-8")
            meta     = json.loads(LOCAL_META.read_text(encoding="utf-8"))
            return json_str, meta.get("timestamp", "—"), meta.get("n_records", 0)
        except Exception:
            pass

    return None, None, 0


# ── Conversão de planilha ─────────────────────────────────────────────────────

def excel_to_json(file_bytes: bytes) -> str | None:
    """Converte bytes de .xlsx para JSON no formato do dashboard."""
    try:
        df = pd.read_excel(BytesIO(file_bytes), engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]

        def find_col(keywords: list) -> str | None:
            for kw in keywords:
                for col in df.columns:
                    if kw.lower() in col.lower():
                        return col
            return None

        col_cod = find_col(["código", "codigo"])
        col_tit = find_col(["título", "titulo"])
        col_st  = find_col(["status"])
        col_sit = find_col(["situação", "situacao"])
        col_dt  = find_col(["emissão", "emissao", "data"])
        col_rsp = find_col(["responsável", "responsavel"])
        col_cli = find_col(["cliente"])
        col_rca = find_col(["análise de causa", "analise de causa"])
        col_mot = find_col(["motivo"])
        col_qtd = find_col(["quantidade"])
        col_trn = find_col(["turno"])

        records = []
        for _, row in df.iterrows():
            cod = str(row.get(col_cod, "")).strip() if col_cod else ""
            if not cod or cod == "nan":
                continue

            # Data
            dt_val = row.get(col_dt) if col_dt else None
            dt_str, ano, mes = "", None, None
            if pd.notna(dt_val):
                try:
                    dt = pd.Timestamp(dt_val)
                    dt_str = dt.strftime("%Y-%m-%d")
                    ano, mes = int(dt.year), int(dt.month)
                except Exception:
                    pass

            # Turno
            trn_raw = str(row.get(col_trn, "")) if col_trn else ""
            if "1" in trn_raw and "2" in trn_raw and "3" in trn_raw:
                turno = "Múltiplos Turnos"
            elif "1" in trn_raw:
                turno = "1° Turno"
            elif "2" in trn_raw:
                turno = "2° Turno"
            elif "3" in trn_raw:
                turno = "3° Turno"
            else:
                turno = "Não Informado"

            def safe(col):
                if not col:
                    return ""
                v = row.get(col)
                return str(v).strip() if pd.notna(v) and str(v) != "nan" else ""

            records.append({
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

        return json.dumps(records, ensure_ascii=False)

    except Exception as e:
        st.error(f"Erro ao processar planilha: {e}")
        return None


# ── Injeção de dados no HTML ──────────────────────────────────────────────────

_RAW_DATA_RE = re.compile(r"const RAW_DATA = \[.*?\];", re.DOTALL)

def inject_data(html: str, json_str: str, ts: str, n: int) -> str:
    html = _RAW_DATA_RE.sub(f"const RAW_DATA = {json_str};", html)
    html = re.sub(r'\d+ registros carregados', f'{n} registros carregados', html)
    html = re.sub(
        r'(Base original[^<"]*|Atualizado em [^<"]*)',
        f'Atualizado em {ts}',
        html,
    )
    return html


def load_html() -> str:
    return HTML_FILE.read_text(encoding="utf-8")


# ── Inicialização — carregar dados persistidos ────────────────────────────────

if "initialized" not in st.session_state:
    with st.spinner("Carregando dados..."):
        json_str, ts, n = load_saved_data()
    if json_str:
        st.session_state["json_data"] = json_str
        st.session_state["update_ts"] = ts
        st.session_state["n_records"] = n
        st.session_state["from_gh"]   = bool(_gh_secrets()[0])
    st.session_state["initialized"] = True


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔵 SMQ_RS")
    st.caption("Sistema de Monitoramento de Qualidade")
    st.divider()

    # Status da base
    if "update_ts" in st.session_state:
        origem = "☁️ GitHub (sincronizado)" if st.session_state.get("from_gh") else "💾 Cache local"
        st.success(f"**Base carregada**\n\n{origem}")
        st.markdown(f"🕐 **Atualizado em:** {st.session_state['update_ts']}")
        st.markdown(f"📋 **Registros:** {st.session_state.get('n_records', 0):,}")
    else:
        st.info("Usando dados originais do sistema.")

    st.divider()

    # GitHub status
    token, repo, branch = _gh_secrets()
    if token:
        st.success(f"☁️ **GitHub conectado**\n\n`{repo}` · branch `{branch}`")
    else:
        st.warning(
            "⚠️ **GitHub não configurado**\n\n"
            "Persistência apenas local (perdida ao reiniciar no Streamlit Cloud).\n\n"
            "Configure em **Settings → Secrets**:\n"
            "```toml\n[github]\ntoken = \"ghp_...\"\nrepo  = \"usuario/smq_rs\"\nbranch = \"main\"\n```"
        )

    st.divider()
    st.markdown("### 📂 Atualizar Planilha")
    uploaded = st.file_uploader(
        "Selecione o arquivo .xlsx",
        type=["xlsx", "xls"],
        help="Mesmo formato da planilha Consultas_RNC_APP.xlsx",
    )

    if uploaded:
        with st.spinner("Processando planilha..."):
            json_str = excel_to_json(uploaded.read())

        if json_str:
            n  = json_str.count('"codigo"')
            ts = datetime.now().strftime("%d/%m/%Y às %H:%M")

            with st.spinner("Salvando dados..."):
                save_data(json_str, ts, n)

            st.session_state["json_data"] = json_str
            st.session_state["update_ts"] = ts
            st.session_state["n_records"] = n
            st.session_state["from_gh"]   = bool(token)

            st.success(f"✅ {n:,} registros salvos!\n\n🕐 {ts}")
            st.rerun()

    # Limpar dados
    st.divider()
    if LOCAL_DATA.exists() or token:
        if st.button("🗑️ Limpar dados salvos", type="secondary"):
            LOCAL_DATA.unlink(missing_ok=True)
            LOCAL_META.unlink(missing_ok=True)
            for k in ["json_data", "update_ts", "n_records", "from_gh"]:
                st.session_state.pop(k, None)
            st.session_state["initialized"] = True
            st.success("Dados removidos. Usando base original.")
            st.rerun()

    st.divider()
    st.caption("SMQ_RS v1.2 · Streamlit + Chart.js")


# ── Renderizar dashboard ──────────────────────────────────────────────────────

html = load_html()

if "json_data" in st.session_state:
    html = inject_data(
        html,
        st.session_state["json_data"],
        st.session_state["update_ts"],
        st.session_state["n_records"],
    )

components.html(html, height=980, scrolling=True)
