"""
SMQ_RS — Sistema de Monitoramento de Qualidade RS
Persistência via GitHub API.

Secrets (Streamlit Cloud → Settings → Secrets):
  [github]
  token  = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  repo   = "seu-usuario/smq_rs"
  branch = "main"
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json, re, base64
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
# GITHUB API
# ══════════════════════════════════════════════════════════════════════════════

def gh_cfg():
    """Retorna (token, repo, branch) ou (None, None, None)."""
    try:
        token  = str(st.secrets["github"]["token"]).strip()
        repo   = str(st.secrets["github"]["repo"]).strip()
        branch = str(st.secrets["github"].get("branch", "main")).strip()
        if token and repo:
            return token, repo, branch
    except Exception:
        pass
    return None, None, None


def gh_ler(path: str) -> tuple[str | None, str | None]:
    """
    Lê arquivo do GitHub.
    Retorna (conteudo_str, sha) ou (None, None).
    """
    token, repo, branch = gh_cfg()
    if not token:
        return None, None
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent":    "SMQ_RS",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read())
            conteudo = base64.b64decode(
                body["content"].replace("\n", "")
            ).decode("utf-8")
            return conteudo, body.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None, None   # arquivo ainda não existe
        return None, None
    except Exception:
        return None, None


def gh_salvar(path: str, conteudo: str, mensagem: str) -> bool:
    """
    Cria ou atualiza arquivo no GitHub.
    Retorna True se sucesso.
    """
    token, repo, branch = gh_cfg()
    if not token:
        return False

    _, sha = gh_ler(path)   # pega SHA para update

    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload = {
        "message": mensagem,
        "content": base64.b64encode(conteudo.encode("utf-8")).decode("ascii"),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    data = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": f"Bearer {token}",
        "Accept":        "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type":  "application/json",
        "User-Agent":    "SMQ_RS",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 201)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# PERSISTÊNCIA LOCAL
# ══════════════════════════════════════════════════════════════════════════════

def salvar_local(json_str: str, ts: str, n: int) -> None:
    LOCAL_JSON.write_text(json_str, encoding="utf-8")
    LOCAL_META.write_text(
        json.dumps({"timestamp": ts, "n_records": n}),
        encoding="utf-8",
    )


def carregar_local() -> tuple[str | None, str, int]:
    if LOCAL_JSON.exists() and LOCAL_META.exists():
        try:
            j    = LOCAL_JSON.read_text(encoding="utf-8")
            meta = json.loads(LOCAL_META.read_text(encoding="utf-8"))
            return j, meta.get("timestamp", "—"), int(meta.get("n_records", 0))
        except Exception:
            pass
    return None, "", 0


def salvar_tudo(json_str: str, ts: str, n: int) -> tuple[bool, bool]:
    """
    Salva local + GitHub.
    Retorna (ok_local, ok_github).
    """
    # Local (sempre)
    try:
        salvar_local(json_str, ts, n)
        ok_local = True
    except Exception:
        ok_local = False

    # GitHub (se configurado)
    token, _, _ = gh_cfg()
    ok_gh = False
    if token:
        ts_commit = datetime.now().strftime("%Y-%m-%d %H:%M")
        ok_gh = gh_salvar(
            "data/dados_salvos.json", json_str,
            f"SMQ_RS: {n} registros — {ts_commit}",
        )
        if ok_gh:
            meta_str = json.dumps({"timestamp": ts, "n_records": n})
            gh_salvar("data/meta.json", meta_str, f"SMQ_RS: meta — {ts_commit}")

    return ok_local, ok_gh


def carregar_tudo() -> tuple[str | None, str, int, str]:
    """
    Carrega dados: GitHub → local → nenhum.
    Retorna (json_str, ts, n, origem).
    """
    token, _, _ = gh_cfg()
    if token:
        j, _   = gh_ler("data/dados_salvos.json")
        m_str, _ = gh_ler("data/meta.json")
        if j and m_str:
            try:
                meta = json.loads(m_str)
                # atualiza cache local
                salvar_local(j, meta.get("timestamp","—"), int(meta.get("n_records",0)))
                return j, meta.get("timestamp","—"), int(meta.get("n_records",0)), "github"
            except Exception:
                pass

    j, ts, n = carregar_local()
    if j:
        return j, ts, n, "local"

    return None, "", 0, "original"


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
                "Coluna 'Código' não encontrada. "
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
                "codigo": cod,          "titulo": safe(c_tit),
                "status": safe(c_st),   "situacao": safe(c_sit),
                "data": dt_str,         "ano": ano, "mes": mes,
                "responsavel": safe(c_rsp),
                "cliente": safe(c_cli),
                "responsavel_causa": safe(c_rca),
                "motivo": safe(c_mot),  "qtd": safe(c_qtd),
                "turno": turno,
            })

        if not registros:
            return None, 0, "Nenhum registro encontrado na planilha."

        return json.dumps(registros, ensure_ascii=False), len(registros), ""

    except Exception as e:
        return None, 0, f"Erro ao ler planilha: {e}"


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
        f"Atualizado em {ts}",
        html,
    )
    return html


# ══════════════════════════════════════════════════════════════════════════════
# INICIALIZAÇÃO
# ══════════════════════════════════════════════════════════════════════════════

if "init" not in st.session_state:
    st.session_state["init"] = True
    with st.spinner("Carregando dados..."):
        j, ts, n, origem = carregar_tudo()
    st.session_state.update({
        "json": j, "ts": ts, "n": n,
        "origem": origem, "log": [],
    })


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("## 🔵 SMQ_RS")
    st.caption("Sistema de Monitoramento de Qualidade")
    st.divider()

    # Status
    origem = st.session_state.get("origem", "original")
    if origem == "github":
        st.success("☁️ **Dados sincronizados com GitHub**")
    elif origem == "local":
        st.warning("💾 **Cache local** (GitHub offline ou não configurado)")
    else:
        st.info("📋 Dados originais do sistema")

    if st.session_state.get("ts"):
        st.caption(f"🕐 {st.session_state['ts']}")
        st.caption(f"📋 {st.session_state['n']:,} registros")

    st.divider()

    # GitHub status (informativo, sem botão de teste)
    token, repo, branch = gh_cfg()
    if token:
        st.success(f"☁️ **GitHub configurado**\n\n`{repo}` · `{branch}`")
    else:
        st.warning(
            "⚠️ **GitHub não configurado**\n\n"
            "Dados persistem apenas na sessão atual.\n\n"
            "Configure em **Settings → Secrets**:\n"
            "```toml\n"
            "[github]\n"
            "token  = \"ghp_...\"\n"
            "repo   = \"usuario/smq_rs\"\n"
            "branch = \"main\"\n"
            "```"
        )

    st.divider()
    st.markdown("### 📂 Atualizar Planilha")

    arquivo = st.file_uploader(
        "Selecione o arquivo .xlsx",
        type=["xlsx", "xls"],
        help="Mesmo formato da planilha Consultas_RNC_APP.xlsx",
    )

    if arquivo:
        if st.button("⬆️ Processar e Salvar", type="primary",
                     use_container_width=True):
            log = []
            ts  = datetime.now().strftime("%d/%m/%Y às %H:%M")

            with st.spinner("Lendo planilha..."):
                j, n, erro = xlsx_para_json(arquivo.read())

            if not j:
                st.error(f"❌ {erro}")
            else:
                log.append(f"✅ {n:,} registros lidos")

                with st.spinner("Salvando..."):
                    ok_local, ok_gh = salvar_tudo(j, ts, n)

                if ok_local:
                    log.append("✅ Cache local: salvo")
                else:
                    log.append("⚠️ Cache local: falhou")

                if token:
                    if ok_gh:
                        log.append("✅ GitHub: salvo com sucesso")
                    else:
                        log.append(
                            "❌ GitHub: falha ao salvar\n"
                            "   Verifique token e nome do repositório."
                        )
                else:
                    log.append("ℹ️ GitHub: não configurado")

                st.session_state.update({
                    "json": j, "ts": ts, "n": n,
                    "origem": "github" if ok_gh else "local",
                    "log": log,
                })
                st.rerun()

    # Log
    if st.session_state.get("log"):
        st.divider()
        st.markdown("**Resultado:**")
        for linha in st.session_state["log"]:
            st.caption(linha)

    st.divider()

    if st.button("🗑️ Limpar dados salvos", type="secondary"):
        LOCAL_JSON.unlink(missing_ok=True)
        LOCAL_META.unlink(missing_ok=True)
        for k in ("json","ts","n","origem","log","init"):
            st.session_state.pop(k, None)
        st.rerun()

    st.caption("SMQ_RS v1.4 · Streamlit + Chart.js")


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
