# Como configurar o Google Sheets para persistência do SMQ_RS

## Por que Google Sheets?
- **Gratuito** — sem custo adicional
- **Permanente** — dados não somem quando o Streamlit Cloud reinicia
- **Simples** — sem banco de dados, sem servidor extra
- **Visível** — você pode ver e editar os dados diretamente na planilha

---

## PASSO 1 — Ativar as APIs do Google

1. Acesse https://console.cloud.google.com
2. Crie uma conta se não tiver (use sua conta Google)
3. Crie um novo projeto: clique em **Selecionar projeto → Novo projeto**
   - Nome: `SMQ-RS`
   - Clique em **Criar**
4. No menu lateral: **APIs e Serviços → Biblioteca**
5. Pesquise e ative **Google Sheets API** (clique → Ativar)
6. Pesquise e ative **Google Drive API** (clique → Ativar)

---

## PASSO 2 — Criar Conta de Serviço

1. Menu lateral: **APIs e Serviços → Credenciais**
2. Clique em **+ Criar credenciais → Conta de serviço**
3. Preencha:
   - Nome da conta: `smq-rs-app`
   - ID: preenchido automaticamente
   - Clique em **Criar e continuar**
4. Em "Conceder acesso": deixe em branco → **Continuar**
5. Clique em **Concluir**
6. Na lista de contas de serviço, clique na que acabou de criar
7. Aba **Chaves → Adicionar chave → Criar nova chave**
8. Formato: **JSON** → **Criar**
9. Um arquivo `.json` será baixado — **guarde com segurança**

O arquivo JSON se parece com isso:
```json
{
  "type": "service_account",
  "project_id": "smq-rs-123456",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n",
  "client_email": "smq-rs-app@smq-rs-123456.iam.gserviceaccount.com",
  "client_id": "123456789",
  ...
}
```

Copie o **client_email** — você precisará dele no Passo 3.

---

## PASSO 3 — Criar a Planilha Google Sheets

1. Acesse https://sheets.google.com
2. Crie uma nova planilha: **+ Nova planilha**
3. Nomeie como `SMQ_RS_Dados`
4. Compartilhe com a conta de serviço:
   - Clique em **Compartilhar** (canto superior direito)
   - Cole o **client_email** da etapa anterior
     (ex: `smq-rs-app@smq-rs-123456.iam.gserviceaccount.com`)
   - Permissão: **Editor**
   - Clique em **Enviar**
5. Copie o **ID da planilha** da URL:
   ```
   https://docs.google.com/spreadsheets/d/1ABC...XYZ/edit
                                          ^^^^^^^^^^^
                                          Este é o ID
   ```

---

## PASSO 4 — Configurar os Secrets no Streamlit Cloud

1. Acesse https://share.streamlit.io
2. No seu app SMQ_RS: clique nos **⋮** → **Settings**
3. Clique em **Secrets**
4. Cole o seguinte (substituindo pelos seus valores):

```toml
[gcp]
sheet_id = "1ABC...XYZ"

credentials = '''
{
  "type": "service_account",
  "project_id": "smq-rs-123456",
  "private_key_id": "abc123def456",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----\n",
  "client_email": "smq-rs-app@smq-rs-123456.iam.gserviceaccount.com",
  "client_id": "123456789012345678901",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/smq-rs-app%40smq-rs-123456.iam.gserviceaccount.com"
}
'''
```

> **Importante:** copie o JSON completo do arquivo baixado no Passo 2 e cole entre os `'''`.

5. Clique em **Save**
6. O app reiniciará automaticamente

---

## PASSO 5 — Testar

1. Abra o app no Streamlit Cloud
2. A sidebar deve mostrar: **☁️ Google Sheets configurado**
3. Faça upload de uma planilha e clique em **⬆️ Salvar Planilha**
4. Você deve ver: **✅ Google Sheets: Salvo**
5. Abra a planilha Google Sheets — você verá os dados nas células A1 e A2
6. **Reinicie o app** — os dados devem ser carregados automaticamente

---

## Como funciona

```
Upload da planilha .xlsx
         │
         ▼
  Converte para JSON
         │
         ├──► Salva local (cache)
         │
         └──► Salva no Google Sheets
               ├── Célula A1: metadados (data, n° registros)
               └── Célula A2: todos os dados JSON

Reinício do app
         │
         ▼
  Lê do Google Sheets (A1 + A2)
         │
         └──► Dados carregados permanentemente ✅
```

---

## Segurança

- O arquivo JSON da conta de serviço dá acesso apenas às planilhas que você compartilhar com ela
- Nunca commite o arquivo JSON no GitHub — use apenas os Secrets do Streamlit
- A conta de serviço não tem acesso a nenhum outro serviço do Google

---

## Custo

- **Google Sheets API**: gratuita até 300 requisições/minuto
- **Google Cloud**: gratuito para este uso (não usa recursos pagos)
- **Total: R$ 0,00/mês**
