"""
SMQ_RS — Sistema de Monitoramento de Qualidade RS
Persistência via Google Sheets (gratuito, permanente).

Secrets necessários (Streamlit Cloud → Settings → Secrets):

  [gcp]
  credentials = '''
  {
    "type": "service_account",
    "project_id": "...",
    "private_key_id": "...",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n",
    "client_email": "smq-rs@seu-projeto.iam.gserviceaccount.com",
    ...
  }
  '''
  sheet_id = "1ABC...XYZ"   # ID da planilha Google Sheets

streamlit run app.py
"""

import streamlit as st
import pandas as pd
import json, re, base64
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


# ══════════════════════════════════════════════════════════════════════════════
# GOOGLE SHEETS — persistência permanente
# ══════════════════════════════════════════════════════════════════════════════

def _gs_client():
    """Retorna cliente gspread autenticado ou None."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds_dict = json.loads(st.secrets["gcp"]["credentials"])
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds  = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception:
        return None


def _gs_sheet():
    """Retorna a primeira aba da planilha configurada ou None."""
    try:
        gc       = _gs_client()
        sheet_id = st.secrets["gcp"]["sheet_id"]
        return gc.open_by_key(sheet_id).sheet1
    except Exception:
        return None


def gs_configurado() -> bool:
    try:
        _ = st.secrets["gcp"]["credentials"]
        _ = st.secrets["gcp"]["sheet_id"]
        return True
    except Exception:
        return False


def gs_salvar(json_str: str, ts: str, n: int) -> tuple[bool, str]:
    """
    Salva dados no Google Sheets.
    Usa duas células: A1 = meta JSON, A2 = dados JSON.
    Retorna (sucesso, mensagem).
    """
    try:
        ws = _gs_sheet()
        if not ws:
            return False, "Não foi possível conectar ao Google Sheets."
        meta = json.dumps({"timestamp": ts, "n_records": n})
        ws.update("A1", [[meta]])
        ws.update("A2", [[json_str]])
        return True, f"Salvo no Google Sheets — {ts}"
    except Exception as e:
        return False, str(e)


def gs_carregar() -> tuple[str | None, str, int]:
    """
    Lê dados do Google Sheets.
    Retorna (json_str, timestamp, n) ou (None, '', 0).
    """
    try:
        ws = _gs_sheet()
        if not ws:
            return None, "", 0
        meta_str = ws.acell("A1").value
        json_str = ws.acell("A2").value
        if meta_str and json_str:
            meta = json.loads(meta_str)
            return json_str, meta.get("timestamp", "—"), int(meta.get("n_records", 0))
    except Exception:
        pass
    return None, "", 0


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTÊNCIA LOCAL (cache / fallback)
# ══════════════════════════════════════════════════════════════════════════════

def salvar_local(json_str: str, ts: str, n: int) -> None:
    LOCAL_JSON.write_text(json_str, encoding="utf-8")
    LOCAL_META.write_text(json.dumps({"timestamp": ts, "n_records": n}), encoding="utf-8")


def carregar_local() -> tuple[str | None, str, int]:
    if LOCAL_JSON.exists() and LOCAL_META.exists():
        try:
            j    = LOCAL_JSON.read_text(encoding="utf-8")
            meta = json.loads(LOCAL_META.read_text(encoding="utf-8"))
            return j, meta.get("timestamp", "—"), int(meta.get("n_records", 0))
        except Exception:
            pass
    return None, "", 0


def salvar_tudo(json_str: str, ts: str, n: int) -> tuple[str, str]:
    """
    Salva local + Google Sheets.
    Retorna (status_local, status_gs).
    """
    # Local
    try:
        salvar_local(json_str, ts, n)
        ok_local = "✅ Cache local: salvo"
    except Exception as e:
        ok_local = f"⚠️ Cache local: {e}"

    # Google Sheets
    if gs_configurado():
        ok, msg = gs_salvar(json_str, ts, n)
        ok_gs = f"{'✅' if ok else '❌'} Google Sheets: {msg}"
    else:
        ok_gs = "ℹ️ Google Sheets: não configurado"

    return ok_local, ok_gs


def carregar_tudo() -> tuple[str | None, str, int, str]:
    """
    Carrega dados: Google Sheets → local → nenhum.
    Retorna (json_str, ts, n, origem).
    """
    if gs_configurado():
        j, ts, n = gs_carregar()
        if j:
            salvar_local(j, ts, n)   # atualiza cache local
            return j, ts, n, "sheets"

    j, ts, n = carregar_local()
    if j:
        return j, ts, n, "local"

    return None, "", 0, "original"


# ══════════════════════════════════════════════════════════════════════════════
# CONVERSÃO XLSX → JSON
# ══════════════════════════════════════════════════════════════════════════════

def xlsx_para_json(file_bytes: bytes) -> tuple[str | None, int, str]:
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
            return None, 0, f"Coluna 'Código' não encontrada. Colunas: {', '.join(df.columns.tolist())}"

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

            def safe(c):
                if not c: return ""
                v = row.get(c)
                return str(v).strip() if pd.notna(v) and str(v) != "nan" else ""

            registros.append({
                "codigo": cod,            "titulo": safe(c_tit),
                "status": safe(c_st),     "situacao": safe(c_sit),
                "data": dt_str,           "ano": ano,  "mes": mes,
                "responsavel": safe(c_rsp),
                "cliente": safe(c_cli),
                "responsavel_causa": safe(c_rca),
                "motivo": safe(c_mot),    "qtd": safe(c_qtd),
                "turno": turno,
            })

        if not registros:
            return None, 0, "Nenhum registro encontrado."

        return json.dumps(registros, ensure_ascii=False), len(registros), ""
    except Exception as e:
        return None, 0, f"Erro ao ler planilha: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# HTML
# ══════════════════════════════════════════════════════════════════════════════

_RE = re.compile(r"const RAW_DATA = \[.*?\];", re.DOTALL)

def montar_html(json_str: str | None, ts: str, n: int) -> str:
    html = HTML_FILE.read_text(encoding="utf-8")
    if json_str:
        html = _RE.sub(f"const RAW_DATA = {json_str};", html)
        html = re.sub(r"\d+ registros carregados", f"{n} registros carregados", html)
        html = re.sub(
            r"(Base original[^<\"]*|Atualizado em [^<\"]*)",
            f"Atualizado em {ts}", html,
        )
    return html


def render_html(html: str, height: int = 980) -> None:
    b64    = base64.b64encode(html.encode("utf-8")).decode("ascii")
    iframe = (
        f'<iframe src="data:text/html;base64,{b64}" '
        f'width="100%" height="{height}px" frameborder="0" '
        f'style="border:none;display:block;" '
        f'sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads">'
        f'</iframe>'
    )
    st.markdown(iframe, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO — carrega uma vez por sessão
# ══════════════════════════════════════════════════════════════════════════════

if "dados" not in st.session_state:
    with st.spinner("Carregando dados..."):
        j, ts, n, origem = carregar_tudo()
    st.session_state.update({
        "dados": j, "ts": ts, "n": n,
        "origem": origem, "log": [],
    })


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🔵 SMQ_RS")
    st.caption("Sistema de Monitoramento de Qualidade")
    st.divider()

    # Status da origem dos dados
    origem = st.session_state.get("origem", "original")
    if origem == "sheets":
        st.success("☁️ **Google Sheets** — dados persistentes")
    elif origem == "local":
        st.warning("💾 **Cache local** — configure o Google Sheets para persistência permanente")
    else:
        st.info("📋 Dados originais do sistema")

    if st.session_state.get("ts"):
        st.caption(f"🕐 {st.session_state['ts']}")
        st.caption(f"📋 {st.session_state['n']:,} registros")

    st.divider()

    # Status Google Sheets
    if gs_configurado():
        st.success("☁️ **Google Sheets configurado**")
    else:
        with st.expander("⚙️ Como configurar o Google Sheets"):
            st.markdown("""
**Passo 1 — Criar credencial de serviço:**
1. Acesse https://console.cloud.google.com
2. APIs → Ativar **Google Sheets API** e **Google Drive API**
3. Credenciais → Criar **Conta de serviço**
4. Baixar JSON da chave

**Passo 2 — Criar planilha:**
1. Crie uma planilha em Google Sheets
2. Compartilhe com o e-mail da conta de serviço (editar)
3. Copie o ID da URL: `docs.google.com/spreadsheets/d/**ID**/edit`

**Passo 3 — Adicionar Secrets:**
```toml
[gcp]
sheet_id = "1ABC...XYZ"
credentials = '''
{cole aqui o conteúdo do JSON da chave}
'''
```
""")

    st.divider()
    st.markdown("### 📂 Atualizar Planilha")

    arquivo = st.file_uploader("Selecione o arquivo .xlsx", type=["xlsx", "xls"])

    if arquivo:
        if st.button("⬆️ Salvar Planilha", type="primary", use_container_width=True):
            with st.spinner("Processando planilha..."):
                j, n, erro = xlsx_para_json(arquivo.read())

            if not j:
                st.error(f"❌ {erro}")
            else:
                ts = datetime.now().strftime("%d/%m/%Y às %H:%M")
                with st.spinner("Salvando..."):
                    ok_local, ok_gs = salvar_tudo(j, ts, n)

                st.session_state.update({
                    "dados": j, "ts": ts, "n": n,
                    "origem": "sheets" if "✅" in ok_gs else "local",
                    "log": [ok_local, ok_gs],
                })
                st.rerun()

    # Log da última operação
    if st.session_state.get("log"):
        for linha in st.session_state["log"]:
            if "✅" in linha: st.success(linha)
            elif "❌" in linha: st.error(linha)
            elif "⚠️" in linha: st.warning(linha)
            else: st.caption(linha)

    st.divider()

    if LOCAL_JSON.exists():
        if st.button("🗑️ Limpar dados salvos", type="secondary"):
            LOCAL_JSON.unlink(missing_ok=True)
            LOCAL_META.unlink(missing_ok=True)
            st.session_state.update({"dados": None, "ts": "", "n": 0,
                                     "origem": "original", "log": []})
            st.rerun()

    st.caption("SMQ_RS v1.6 · Google Sheets + Chart.js")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

html_final = montar_html(
    st.session_state.get("dados"),
    st.session_state.get("ts", ""),
    st.session_state.get("n", 0),
)
render_html(html_final, height=980)
