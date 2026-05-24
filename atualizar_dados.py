"""
SMQ_RS — Script de Atualização de Dados
========================================
Execute este script no seu computador sempre que tiver uma nova planilha.

Ele faz 3 coisas:
  1. Lê a planilha Excel e converte para JSON
  2. Gera um novo dashboard_rnc.html com os dados embutidos
  3. Faz commit + push automático para o GitHub (opcional)

USO:
  python atualizar_dados.py planilha.xlsx

REQUISITOS:
  pip install pandas openpyxl

CONFIGURAÇÃO DO GITHUB (opcional, para push automático):
  Crie um arquivo .env na mesma pasta com:
    GITHUB_TOKEN=ghp_...
    GITHUB_REPO=seu-usuario/smq_rs
    GITHUB_BRANCH=main
"""

import sys
import json
import re
import base64
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
except ImportError:
    print("❌ Pandas não instalado. Execute: pip install pandas openpyxl")
    sys.exit(1)

# ── Caminhos ───────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
HTML_ORIG  = BASE_DIR / "dashboard_rnc.html"      # HTML original (template)
DATA_DIR   = BASE_DIR / "data"
JSON_FILE  = DATA_DIR / "dados_salvos.json"
META_FILE  = DATA_DIR / "meta.json"

DATA_DIR.mkdir(exist_ok=True)


# ── Ler configuração do .env (se existir) ─────────────────────────────────────

def ler_env() -> dict:
    env = {}
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for linha in env_file.read_text().splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip()
    return env


# ── Converter planilha → JSON ──────────────────────────────────────────────────

def planilha_para_json(caminho_xlsx: str) -> tuple[list, str]:
    """
    Lê planilha Excel e retorna (lista_de_registros, mensagem).
    """
    path = Path(caminho_xlsx)
    if not path.exists():
        return [], f"Arquivo não encontrado: {caminho_xlsx}"

    print(f"📂 Lendo: {path.name}")
    df = pd.read_excel(path, engine="openpyxl")
    df.columns = [str(c).strip() for c in df.columns]

    print(f"   Colunas encontradas: {list(df.columns)}")

    def achar(palavras):
        for p in palavras:
            for c in df.columns:
                if p.lower() in c.lower():
                    return c
        return None

    col_cod = achar(["código","codigo"])
    col_tit = achar(["título","titulo"])
    col_st  = achar(["status"])
    col_sit = achar(["situação","situacao"])
    col_dt  = achar(["emissão","emissao","data"])
    col_rsp = achar(["responsável","responsavel"])
    col_cli = achar(["cliente"])
    col_rca = achar(["análise de causa","analise de causa"])
    col_mot = achar(["motivo"])
    col_qtd = achar(["quantidade"])
    col_trn = achar(["turno"])

    print(f"   Colunas mapeadas:")
    for nome, col in [("Código",col_cod),("Status",col_st),("Data",col_dt),
                      ("Cliente",col_cli),("Motivo",col_mot),("Turno",col_trn),
                      ("Resp. Análise",col_rca)]:
        status = f"✅ {col}" if col else "⚠️  NÃO ENCONTRADA"
        print(f"     {nome}: {status}")

    if not col_cod:
        return [], "Coluna 'Código' não encontrada. Verifique o arquivo."

    registros = []
    for _, row in df.iterrows():
        cod = str(row.get(col_cod, "")).strip()
        if not cod or cod == "nan":
            continue

        # Data
        dt_str, ano, mes = "", None, None
        dt_val = row.get(col_dt) if col_dt else None
        if pd.notna(dt_val):
            try:
                dt = pd.Timestamp(dt_val)
                dt_str = dt.strftime("%Y-%m-%d")
                ano, mes = int(dt.year), int(dt.month)
            except Exception:
                pass

        # Turno
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
            if pd.isna(v) or str(v) == "nan": return ""
            return str(v).strip()

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

    return registros, ""


# ── Salvar arquivos locais ─────────────────────────────────────────────────────

def salvar_local(registros: list, ts: str) -> None:
    n = len(registros)
    json_str = json.dumps(registros, ensure_ascii=False, indent=2)
    meta_str = json.dumps({"timestamp": ts, "n_records": n}, ensure_ascii=False, indent=2)

    JSON_FILE.write_text(json_str, encoding="utf-8")
    META_FILE.write_text(meta_str, encoding="utf-8")

    print(f"\n💾 Salvos localmente:")
    print(f"   {JSON_FILE}  ({JSON_FILE.stat().st_size/1024:.1f} KB)")
    print(f"   {META_FILE}")


# ── Atualizar dashboard_rnc.html com dados embutidos ──────────────────────────

def atualizar_html(registros: list, ts: str) -> None:
    """
    Substitui RAW_DATA dentro do HTML pelo novo JSON.
    Isso garante que o Streamlit sempre sirva dados atualizados,
    sem depender de nenhuma API ou leitura de arquivo em runtime.
    """
    if not HTML_ORIG.exists():
        print(f"⚠️  {HTML_ORIG} não encontrado — pulando atualização do HTML.")
        return

    n = len(registros)
    json_str = json.dumps(registros, ensure_ascii=False)

    html = HTML_ORIG.read_text(encoding="utf-8")

    # Substituir RAW_DATA
    re_data = re.compile(r"const RAW_DATA = \[.*?\];", re.DOTALL)
    if not re_data.search(html):
        print("⚠️  Padrão RAW_DATA não encontrado no HTML.")
        return

    html = re_data.sub(f"const RAW_DATA = {json_str};", html)

    # Atualizar contagem
    html = re.sub(r"\d+ registros carregados", f"{n} registros carregados", html)

    # Atualizar timestamp
    html = re.sub(
        r'(Base original[^<"]*|Atualizado em [^<"]*)',
        f"Atualizado em {ts}",
        html,
    )

    HTML_ORIG.write_text(html, encoding="utf-8")
    print(f"✅ HTML atualizado: {HTML_ORIG.name}  ({HTML_ORIG.stat().st_size/1024:.0f} KB)")


# ── Push para GitHub ───────────────────────────────────────────────────────────

def gh_put(token: str, repo: str, branch: str, path: str,
           content_bytes: bytes, commit_msg: str) -> tuple[bool, str]:
    """Cria ou atualiza um arquivo no GitHub via API."""

    url = f"https://api.github.com/repos/{repo}/contents/{path}"

    # Buscar SHA atual
    req_get = urllib.request.Request(
        f"{url}?ref={branch}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent":    "SMQ_RS-updater",
        },
    )
    sha = None
    try:
        with urllib.request.urlopen(req_get, timeout=10) as r:
            sha = json.loads(r.read()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            return False, f"GET erro {e.code}"
    except Exception as e:
        return False, f"GET erro: {e}"

    # PUT
    payload = {
        "message": commit_msg,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch":  branch,
    }
    if sha:
        payload["sha"] = sha

    req_put = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type":  "application/json",
            "User-Agent":    "SMQ_RS-updater",
        },
    )
    try:
        with urllib.request.urlopen(req_put, timeout=20) as r:
            return True, f"status {r.status}"
    except urllib.error.HTTPError as e:
        body = {}
        try: body = json.loads(e.read())
        except Exception: pass
        return False, f"PUT erro {e.code}: {body.get('message', '')}"
    except Exception as e:
        return False, f"PUT erro: {e}"


def push_github(env: dict, ts: str) -> None:
    token  = env.get("GITHUB_TOKEN", "").strip()
    repo   = env.get("GITHUB_REPO", "").strip()
    branch = env.get("GITHUB_BRANCH", "main").strip()

    if not token or not repo:
        print("\nℹ️  GitHub não configurado no .env — push ignorado.")
        print("   Para ativar, crie um arquivo .env com:")
        print("     GITHUB_TOKEN=ghp_...")
        print("     GITHUB_REPO=seu-usuario/smq_rs")
        return

    if not token.startswith("gh"):
        print(f"\n⚠️  Token inválido (deve começar com 'gh'): {token[:8]}...")
        return

    ts_fmt = datetime.now().strftime("%Y-%m-%d %H:%M")
    arquivos = [
        (JSON_FILE,  "data/dados_salvos.json", f"SMQ_RS: dados — {ts_fmt}"),
        (META_FILE,  "data/meta.json",          f"SMQ_RS: meta — {ts_fmt}"),
        (HTML_ORIG,  "dashboard_rnc.html",      f"SMQ_RS: dashboard atualizado — {ts_fmt}"),
    ]

    print(f"\n☁️  Enviando para GitHub ({repo} · {branch})...")

    for local_path, gh_path, msg in arquivos:
        if not local_path.exists():
            print(f"   ⚠️  {local_path.name}: arquivo não existe, pulando.")
            continue

        conteudo = local_path.read_bytes()
        ok, info = gh_put(token, repo, branch, gh_path, conteudo, msg)

        if ok:
            print(f"   ✅ {gh_path}  ({len(conteudo)/1024:.0f} KB)")
        else:
            print(f"   ❌ {gh_path}: {info}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  SMQ_RS — Atualização de Dados")
    print("=" * 55)

    # Verificar argumento
    if len(sys.argv) < 2:
        print("\n❌ Informe o caminho da planilha:")
        print("   python atualizar_dados.py Consultas_RNC_APP.xlsx")
        sys.exit(1)

    xlsx_path = sys.argv[1]

    # 1. Converter planilha
    registros, erro = planilha_para_json(xlsx_path)
    if erro:
        print(f"\n❌ Erro: {erro}")
        sys.exit(1)

    n  = len(registros)
    ts = datetime.now().strftime("%d/%m/%Y às %H:%M")
    print(f"\n✅ {n} registros convertidos")

    # 2. Salvar local
    salvar_local(registros, ts)

    # 3. Atualizar HTML com dados embutidos
    atualizar_html(registros, ts)

    # 4. Push GitHub
    env = ler_env()
    push_github(env, ts)

    print("\n" + "=" * 55)
    print("  ✅ Concluído!")
    print(f"  📋 {n} registros · {ts}")
    if env.get("GITHUB_TOKEN"):
        print("  ☁️  Dados sincronizados com GitHub")
        print("  🔄 O Streamlit Cloud vai atualizar em ~1 minuto")
    else:
        print("  ⚠️  Configure .env para sincronizar com GitHub")
    print("=" * 55)


if __name__ == "__main__":
    main()
