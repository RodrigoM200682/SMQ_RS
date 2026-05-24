# SMQ_RS — Sistema de Monitoramento de Qualidade RS

Dashboard interativo para monitoramento de RNCs (Registros de Não Conformidade) e reclamações de clientes.

---

## 📦 Estrutura do projeto

```
smq_rs/
├── app.py                  # Aplicação Streamlit principal
├── dashboard_rnc.html      # Dashboard interativo (Chart.js + lógica JS)
├── requirements.txt        # Dependências Python
└── README.md
```

---

## 🚀 Executar localmente

### 1. Clone o repositório
```bash
git clone https://github.com/seu-usuario/smq_rs.git
cd smq_rs
```

### 2. Crie um ambiente virtual (recomendado)
```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
```

### 3. Instale as dependências
```bash
pip install -r requirements.txt
```

### 4. Execute
```bash
streamlit run app.py
```

Acesse em: `http://localhost:8501`

---

## ☁️ Deploy no Streamlit Cloud

1. Faça fork/push do repositório para o GitHub
2. Acesse [share.streamlit.io](https://share.streamlit.io)
3. Clique em **New app**
4. Selecione o repositório e o arquivo `app.py`
5. Clique em **Deploy**

> O Streamlit Cloud instala automaticamente as dependências do `requirements.txt`.

---

## 📊 Funcionalidades

| Aba | Descrição |
|-----|-----------|
| **Visão Geral** | Totais da base completa · RNCs em atraso · Pizzas por status e turno |
| **Por Período** | KPIs + gráficos filtrados por período, status, cliente, motivo, turno e responsável |
| **Comparação** | Dois intervalos de meses lado a lado — motivos, turnos e evolução mensal |
| **Por Responsável** | Ranking de analistas · Top motivos por responsável |
| **Registros** | Tabela completa com múltipla seleção de filtros |

### Filtros globais
- Período (de/até)
- Status (múltipla seleção)
- Turno (múltipla seleção)
- Cliente (múltipla seleção)
- Motivo (múltipla seleção)
- Responsável de análise

### Outras funcionalidades
- **Recolher filtro** — expande/colapsa a barra de filtros
- **Baixar Relatório PDF** — exporta o painel ativo com data da consulta
- **Atualizar Planilha** — via sidebar (Streamlit) ou botão no dashboard

---

## 📋 Formato da planilha

O sistema lê arquivos `.xlsx` com as seguintes colunas (nome aproximado):

| Coluna | Descrição |
|--------|-----------|
| Código | Identificador único da RNC |
| Título | Descrição resumida |
| Status | Aberta / Concluída / Reprovada / Associada / Cancelada |
| Situação | No prazo / Atrasada / Fechada no prazo / Fechada atrasada |
| Data de emissão | Data de abertura da RNC |
| Responsável | Responsável pelo registro |
| Cliente | Nome do cliente |
| Responsável da análise de causa | Analista responsável |
| Motivo Reclamação | Tipo de defeito/motivo |
| Quantidade não conforme | Quantidade afetada |
| Turno/Horário | 1° / 2° / 3° Turno |

---

## 🔧 Tecnologias

- **Python** — Streamlit, Pandas, OpenPyXL
- **JavaScript** — Chart.js 4.4.1, XLSX.js
- **Fontes** — IBM Plex Sans / IBM Plex Mono

---

## 📄 Licença

MIT — uso livre para fins internos e comerciais.

---

## 💾 Persistência de dados

Ao enviar uma nova planilha via sidebar, o sistema salva automaticamente:

```
data/
├── dados_salvos.json   ← registros convertidos da última planilha
└── meta.json           ← timestamp e contagem de registros
```

**A cada reinício**, o app carrega automaticamente esses arquivos — sem necessidade de reenviar a planilha.

Para voltar à base original, use o botão **"Limpar dados salvos"** na sidebar.

> **Nota Streamlit Cloud:** o sistema de arquivos do Streamlit Cloud é efêmero (reinicia ao fazer novo deploy). Para persistência permanente em produção, recomenda-se substituir `DATA_FILE` por um bucket S3, Google Cloud Storage ou banco de dados externo. Localmente e em servidores próprios, a persistência em arquivo funciona normalmente.
