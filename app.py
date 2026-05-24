"""
SMQ_RS — Sistema de Monitoramento de Qualidade RS
Aplicação Streamlit que serve o dashboard interativo de RNCs.

Persistência: os dados da última planilha carregada são salvos em
data/dados_salvos.json e data/meta.json — carregados automaticamente
a cada reinício da aplicação.

Deploy: streamlit run app.py
GitHub: https://github.com/seu-usuario/smq_rs
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import re
from datetime import datetime
from pathlib import Path

# ── Caminhos ──────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
HTML_FILE  = BASE_DIR / "dashboard_rnc.html"
DATA_DIR   = BASE_DIR / "data"
DATA_FILE  = DATA_DIR / "dados_salvos.json"   # registros em JSON
META_FILE  = DATA_DIR / "meta.json"           # timestamp + contagem

DATA_DIR.mkdir(exist_ok=True)

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


# ── Persistência ──────────────────────────────────────────────────────────────

def save_data(json_str: str, ts: str, n: int) -> None:
    """Grava os dados e metadados em disco."""
    DATA_FILE.write_text(json_str, encoding="utf-8")
    META_FILE.write_text(
        json.dumps({"timestamp": ts, "n_records": n}, ensure_ascii=False),
        encoding="utf-8",
    )

def load_saved_data() -> tuple[str | None, str | None, int]:
    """
    Lê dados salvos em disco.
    Retorna (json_str, timestamp, n_records) ou (None, None, 0) se não houver.
    """
    if DATA_FILE.exists() and META_FILE.exists():
        try:
            json_str = DATA_FILE.read_text(encoding="utf-8")
            meta     = json.loads(META_FILE.read_text(encoding="utf-8"))
            return json_str, meta.get("timestamp", "—"), meta.get("n_records", 0)
        except Exception:
            pass
    return None, None, 0


# ── Conversão de planilha ─────────────────────────────────────────────────────

def excel_to_json(file_bytes: bytes) -> str | None:
    """
    Converte bytes de um .xlsx para JSON no formato esperado pelo dashboard.
    Retorna None se houver erro.
    """
    try:
        df = pd.read_excel(file_bytes, engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]

        def find_col(keywords: list[str]) -> str | None:
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
            has = lambda n: str(n) in trn_raw
            if has(1) and has(2) and has(3):
                turno = "Múltiplos Turnos"
            elif has(1):
                turno = "1° Turno"
            elif has(2):
                turno = "2° Turno"
            elif has(3):
                turno = "3° Turno"
            else:
                turno = "Não Informado"

            def safe(col: str | None) -> str:
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
    """Substitui RAW_DATA e textos de status no HTML."""
    html = _RAW_DATA_RE.sub(f"const RAW_DATA = {json_str};", html)

    # Contagem de registros — substitui qualquer número antes de " registros carregados"
    html = re.sub(
        r'\d+ registros carregados',
        f'{n} registros carregados',
        html,
    )
    # Texto de última atualização
    html = re.sub(
        r'(Base original[^<"]*|Atualizado em [^<"]*)',
        f'Atualizado em {ts}',
        html,
    )
    return html

def load_html() -> str:
    return HTML_FILE.read_text(encoding="utf-8")


# ── Inicialização — carregar dados salvos em disco ────────────────────────────

if "initialized" not in st.session_state:
    json_str, ts, n = load_saved_data()
    if json_str:
        st.session_state["json_data"]  = json_str
        st.session_state["update_ts"]  = ts
        st.session_state["n_records"]  = n
        st.session_state["from_disk"]  = True
    st.session_state["initialized"] = True


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔵 SMQ_RS")
    st.markdown("Sistema de Monitoramento de Qualidade")
    st.divider()

    # Status da base atual
    if "update_ts" in st.session_state:
        origem = "💾 Dados salvos em disco" if st.session_state.get("from_disk") else "📤 Dados do upload atual"
        st.markdown(f"**{origem}**")
        st.markdown(f"🕐 {st.session_state['update_ts']}")
        st.markdown(f"📋 {st.session_state.get('n_records', 0):,} registros")
        st.divider()
    else:
        st.info("Usando dados originais embutidos no sistema.")
        st.divider()

    st.markdown("### 📂 Atualizar Planilha")
    st.caption("Ao enviar uma nova planilha, os dados são salvos permanentemente e carregados automaticamente nos próximos acessos.")

    uploaded = st.file_uploader(
        "Selecione o arquivo .xlsx",
        type=["xlsx", "xls"],
        help="Mesmo formato da planilha Consultas_RNC_APP.xlsx",
    )

    if uploaded:
        with st.spinner("Processando e salvando planilha..."):
            json_str = excel_to_json(uploaded.read())

        if json_str:
            n  = json_str.count('"codigo"')
            ts = datetime.now().strftime("%d/%m/%Y às %H:%M")

            # Salvar em disco (persistência entre reinícios)
            save_data(json_str, ts, n)

            # Atualizar session_state
            st.session_state["json_data"] = json_str
            st.session_state["update_ts"] = ts
            st.session_state["n_records"] = n
            st.session_state["from_disk"] = False

            st.success(f"✅ {n:,} registros salvos com sucesso!\n\n🕐 {ts}")
            st.rerun()

    st.divider()

    # Opção de limpar dados salvos
    if DATA_FILE.exists():
        if st.button("🗑️ Limpar dados salvos", type="secondary",
                     help="Remove os dados persistidos e volta para a base original"):
            DATA_FILE.unlink(missing_ok=True)
            META_FILE.unlink(missing_ok=True)
            for key in ["json_data", "update_ts", "n_records", "from_disk"]:
                st.session_state.pop(key, None)
            st.success("Dados salvos removidos. Usando base original.")
            st.rerun()

    st.divider()
    st.caption("SMQ_RS v1.1 · Streamlit + Chart.js")


# ── Montar e renderizar dashboard ─────────────────────────────────────────────

html = load_html()

if "json_data" in st.session_state:
    html = inject_data(
        html,
        st.session_state["json_data"],
        st.session_state["update_ts"],
        st.session_state["n_records"],
    )

components.html(html, height=980, scrolling=True)
