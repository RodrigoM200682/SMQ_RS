"""
SMQ_RS — Sistema de Monitoramento de Qualidade RS
streamlit run app.py
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json, re
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
# CONVERSÃO XLSX → JSON
# ══════════════════════════════════════════════════════════════════════════════

def xlsx_para_json(file_bytes: bytes) -> tuple[str | None, int, str]:
    """Retorna (json_str, n_registros, msg_erro)."""
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
            return None, 0, (
                f"Coluna 'Código' não encontrada. "
                f"Colunas detectadas: {', '.join(df.columns.tolist())}"
            )

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
            return None, 0, "Nenhum registro encontrado na planilha."

        return json.dumps(registros, ensure_ascii=False), len(registros), ""

    except Exception as e:
        return None, 0, f"Erro ao ler planilha: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTÊNCIA — salvar e carregar do disco
# ══════════════════════════════════════════════════════════════════════════════

def salvar_disco(json_str: str, ts: str, n: int) -> None:
    LOCAL_JSON.write_text(json_str, encoding="utf-8")
    LOCAL_META.write_text(
        json.dumps({"timestamp": ts, "n_records": n}),
        encoding="utf-8",
    )


def carregar_disco() -> tuple[str | None, str, int]:
    """Lê dados salvos. Retorna (json_str, timestamp, n) ou (None,'',0)."""
    if LOCAL_JSON.exists() and LOCAL_META.exists():
        try:
            j    = LOCAL_JSON.read_text(encoding="utf-8")
            meta = json.loads(LOCAL_META.read_text(encoding="utf-8"))
            return j, meta.get("timestamp", "—"), int(meta.get("n_records", 0))
        except Exception:
            pass
    return None, "", 0


# ══════════════════════════════════════════════════════════════════════════════
# INJEÇÃO NO HTML
# ══════════════════════════════════════════════════════════════════════════════

_RE = re.compile(r"const RAW_DATA = \[.*?\];", re.DOTALL)

def montar_html(json_str: str, ts: str, n: int) -> str:
    html = HTML_FILE.read_text(encoding="utf-8")
    html = _RE.sub(f"const RAW_DATA = {json_str};", html)
    html = re.sub(r"\d+ registros carregados", f"{n} registros carregados", html)
    html = re.sub(
        r"(Base original[^<\"]*|Atualizado em [^<\"]*)",
        f"Atualizado em {ts}",
        html,
    )
    return html


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO — carrega dados salvos uma única vez por sessão
# ══════════════════════════════════════════════════════════════════════════════

if "dados" not in st.session_state:
    j, ts, n = carregar_disco()
    st.session_state["dados"] = j
    st.session_state["ts"]    = ts
    st.session_state["n"]     = n


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🔵 SMQ_RS")
    st.caption("Sistema de Monitoramento de Qualidade")
    st.divider()

    # Status
    if st.session_state["dados"]:
        st.success("✅ Dados carregados")
        st.caption(f"🕐 {st.session_state['ts']}")
        st.caption(f"📋 {st.session_state['n']:,} registros")
    else:
        st.info("📋 Usando dados originais do sistema")

    st.divider()
    st.markdown("### 📂 Atualizar Planilha")

    arquivo = st.file_uploader(
        "Selecione o arquivo .xlsx",
        type=["xlsx", "xls"],
    )

    if arquivo:
        if st.button("⬆️ Salvar Planilha", type="primary",
                     use_container_width=True):
            with st.spinner("Processando..."):
                j, n, erro = xlsx_para_json(arquivo.read())

            if not j:
                st.error(f"❌ {erro}")
            else:
                ts = datetime.now().strftime("%d/%m/%Y às %H:%M")
                try:
                    salvar_disco(j, ts, n)
                    st.session_state["dados"] = j
                    st.session_state["ts"]    = ts
                    st.session_state["n"]     = n
                    st.success(f"✅ {n:,} registros salvos!\n\n🕐 {ts}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Erro ao salvar: {e}")

    st.divider()

    if LOCAL_JSON.exists():
        if st.button("🗑️ Limpar dados salvos", type="secondary"):
            LOCAL_JSON.unlink(missing_ok=True)
            LOCAL_META.unlink(missing_ok=True)
            st.session_state["dados"] = None
            st.session_state["ts"]    = ""
            st.session_state["n"]     = 0
            st.rerun()

    st.caption("SMQ_RS v1.5 · Streamlit + Chart.js")


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

if st.session_state.get("dados"):
    html = montar_html(
        st.session_state["dados"],
        st.session_state["ts"],
        st.session_state["n"],
    )
else:
    html = HTML_FILE.read_text(encoding="utf-8")

components.html(html, height=980, scrolling=True)
