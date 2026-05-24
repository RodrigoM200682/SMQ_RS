"""
SMQ_RS — Sistema de Monitoramento de Qualidade RS
Aplicação Streamlit que serve o dashboard interativo de RNCs.

Deploy: streamlit run app.py
GitHub: https://github.com/seu-usuario/smq_rs
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
from datetime import datetime
from pathlib import Path

# ── Configuração da página ────────────────────────────────────────────────────
st.set_page_config(
    page_title="SMQ_RS — Monitoramento de Qualidade",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Ocultar elementos padrão do Streamlit para visual limpo
st.markdown("""
<style>
  #MainMenu, footer, header { visibility: hidden; }
  .block-container { padding: 0 !important; max-width: 100% !important; }
  .stApp { background: #0f1117; }
</style>
""", unsafe_allow_html=True)

# ── Carregar HTML do dashboard ────────────────────────────────────────────────
HTML_FILE = Path(__file__).parent / "dashboard_rnc.html"

def load_dashboard_html() -> str:
    """Lê o HTML do dashboard. Suporta injeção de dados via upload."""
    return HTML_FILE.read_text(encoding="utf-8")

def excel_to_json(file_bytes: bytes) -> str | None:
    """
    Converte bytes de um .xlsx para JSON no mesmo formato
    esperado pelo dashboard (lista de dicts).
    Retorna None se houver erro.
    """
    try:
        df = pd.read_excel(file_bytes, engine="openpyxl")
        df.columns = [str(c).strip() for c in df.columns]

        # Mapear colunas pelo nome (case-insensitive, busca parcial)
        def find_col(keywords):
            for kw in keywords:
                for col in df.columns:
                    if kw.lower() in col.lower():
                        return col
            return None

        col_cod   = find_col(["código", "codigo"])
        col_tit   = find_col(["título", "titulo"])
        col_st    = find_col(["status"])
        col_sit   = find_col(["situação", "situacao"])
        col_dt    = find_col(["emissão", "emissao", "data"])
        col_rsp   = find_col(["responsável", "responsavel"])
        col_cli   = find_col(["cliente"])
        col_rca   = find_col(["análise de causa", "analise de causa"])
        col_mot   = find_col(["motivo"])
        col_qtd   = find_col(["quantidade"])
        col_trn   = find_col(["turno"])

        records = []
        for _, row in df.iterrows():
            cod = str(row.get(col_cod, "")) if col_cod else ""
            if not cod or cod == "nan":
                continue

            # Data
            dt_val = row.get(col_dt) if col_dt else None
            dt_str, ano, mes = "", None, None
            if pd.notna(dt_val):
                if isinstance(dt_val, (datetime, pd.Timestamp)):
                    dt = pd.Timestamp(dt_val)
                    dt_str = dt.strftime("%Y-%m-%d")
                    ano, mes = dt.year, dt.month
                elif isinstance(dt_val, str):
                    try:
                        dt = pd.to_datetime(dt_val)
                        dt_str = dt.strftime("%Y-%m-%d")
                        ano, mes = dt.year, dt.month
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
                v = row.get(col) if col else None
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


def inject_new_data(html: str, json_data: str, update_ts: str) -> str:
    """
    Substitui os dados embutidos no HTML pelo novo JSON
    e atualiza o texto de última atualização.
    """
    import re

    # Substituir RAW_DATA
    html = re.sub(
        r"const RAW_DATA = \[.*?\];",
        f"const RAW_DATA = {json_data};",
        html,
        flags=re.DOTALL,
    )

    # Atualizar texto de última atualização no data-update
    n = json_data.count('"codigo"')
    html = html.replace(
        "341 registros carregados",
        f"{n} registros carregados",
    )
    html = html.replace(
        "Base original · jan/2025–mai/2026",
        f"Atualizado em {update_ts}",
    )

    return html


# ── Interface ─────────────────────────────────────────────────────────────────
# Sidebar: upload de nova planilha
with st.sidebar:
    st.markdown("## SMQ_RS")
    st.markdown("Sistema de Monitoramento de Qualidade")
    st.divider()
    st.markdown("### 📂 Atualizar Dados")
    uploaded = st.file_uploader(
        "Envie uma planilha .xlsx",
        type=["xlsx", "xls"],
        help="Mesmo formato da planilha de referência (Consultas_RNC_APP.xlsx)",
    )
    if uploaded:
        with st.spinner("Processando planilha..."):
            json_data = excel_to_json(uploaded.read())
        if json_data:
            n = json_data.count('"codigo"')
            ts = datetime.now().strftime("%d/%m/%Y às %H:%M")
            st.success(f"✅ {n} registros carregados\n\n🕐 {ts}")
            st.session_state["json_data"] = json_data
            st.session_state["update_ts"] = ts
            st.session_state["n_records"] = n

    st.divider()
    st.markdown("### ℹ️ Sobre")
    st.caption("SMQ_RS v1.0 — Dashboard interativo de RNCs. Desenvolvido com Streamlit + Chart.js.")

    if "update_ts" in st.session_state:
        st.markdown(f"**Última atualização:** {st.session_state['update_ts']}")
        st.markdown(f"**Registros:** {st.session_state.get('n_records', '—')}")

# Montar HTML final
html_content = load_dashboard_html()

if "json_data" in st.session_state:
    html_content = inject_new_data(
        html_content,
        st.session_state["json_data"],
        st.session_state.get("update_ts", "—"),
    )

# Renderizar dashboard completo
components.html(html_content, height=960, scrolling=True)
