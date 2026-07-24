"""
Download da tabela ConversationTranscript do Dataverse via Web API.

Autenticação: ROPC (Resource Owner Password Credentials) — usuário e senha.
IMPORTANTE: ROPC não funciona se o usuário tiver MFA habilitado.

Uso:
  python download_conversation_transcripts.py

Configuração:
  - Preencha as variáveis na seção CONFIGURAÇÃO abaixo, OU
  - Defina variáveis de ambiente (DATAVERSE_USERNAME, DATAVERSE_PASSWORD, etc.)
  - A senha também pode ser informada interativamente no terminal.
"""

import io
import os
import sys
import time
from pathlib import Path

import msal
import pandas as pd
import requests

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

SCRIPT_DIR = Path(__file__).resolve().parent

# Ambientes disponíveis — adicione novos aqui
ENVIRONMENTS = {
    "1": {
        "name": "MRS-IA-HML",
        "url": "https://mrs-ia-hml.crm2.dynamics.com",
        "output": SCRIPT_DIR.parent / "conversationtranscripts_hml.csv",
    },
    "2": {
        "name": "MRS-IA-PROD",
        "url": "https://mrs-ia-prod.crm2.dynamics.com",
        "output": SCRIPT_DIR.parent / "conversationtranscripts_prod.csv",
    },
    "3": {
        "name": "MRS-IA-SANDBOX",
        "url": "https://mrs-ia-sandbox.crm2.dynamics.com",
        "output": SCRIPT_DIR.parent / "conversationtranscripts_sandbox.csv",
    },
}

# Tenant ID do Azure AD (domínio ou GUID)
TENANT_ID = os.getenv("DATAVERSE_TENANT_ID", "mrs.com.br")

# Credenciais (mesmas para todos os ambientes)
USERNAME = os.getenv("DATAVERSE_USERNAME", "U_ADM_IA_PLTFORM@mrs.com.br")
PASSWORD = os.getenv("DATAVERSE_PASSWORD", "")

# Client ID público do Power Platform (funciona sem App Registration próprio)
CLIENT_ID = os.getenv(
    "DATAVERSE_CLIENT_ID", "51f81489-12ee-4a9e-aaae-a2591f45987d"
)

# Tamanho da página (máx 5000 no Dataverse)
PAGE_SIZE = 5000

# =============================================================================
# COLUNAS A BAIXAR
# =============================================================================

# Campos da entidade conversationtranscript (select)
# Deixe vazio [] para baixar TODAS as colunas (útil na primeira execução
# para descobrir os nomes corretos dos campos).
SELECT_FIELDS = []

# Expand para obter dados de entidades relacionadas (ex: bot).
# Deixe vazio "" para não expandir nenhuma entidade na primeira tentativa.
EXPAND = ""

# =============================================================================

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace"
    )
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, encoding="utf-8", errors="replace"
    )


def acquire_token(
    dataverse_url: str,
    tenant_id: str,
    client_id: str,
    username: str,
    password: str,
) -> str:
    """Obtém access token via ROPC (username/password)."""
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    scopes = [f"{dataverse_url}/.default"]

    app = msal.PublicClientApplication(client_id, authority=authority)

    result = app.acquire_token_by_username_password(
        username=username,
        password=password,
        scopes=scopes,
    )

    if "access_token" in result:
        return result["access_token"]

    error_description = result.get("error_description", "Erro desconhecido")
    error_code = result.get("error", "")
    raise RuntimeError(
        f"Falha na autenticação ({error_code}):\n{error_description}\n\n"
        "Possíveis causas:\n"
        "  - Usuário tem MFA habilitado (ROPC não suporta MFA)\n"
        "  - Client ID não permite public client flows\n"
        "  - Credenciais incorretas\n"
        "  - Tenant ID incorreto"
    )


def build_initial_url(dataverse_url: str) -> str:
    """Monta a URL da primeira requisição com $select, $expand e paginação."""
    base = f"{dataverse_url}/api/data/v9.2/conversationtranscripts"
    params = ["$count=true"]
    if SELECT_FIELDS:
        params.append(f"$select={','.join(SELECT_FIELDS)}")
    if EXPAND:
        params.append(f"$expand={EXPAND}")
    return f"{base}?{'&'.join(params)}"


def fetch_all_records(dataverse_url: str, token: str) -> list:
    """Busca todos os registros com paginação automática."""
    headers = {
        "Authorization": f"Bearer {token}",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
        "Accept": "application/json",
        "Prefer": f"odata.maxpagesize={PAGE_SIZE},odata.include-annotations=*",
    }

    url = build_initial_url(dataverse_url)
    all_records = []
    page = 1
    total_count = None

    while url:
        print(f"  Buscando página {page}...", end=" ", flush=True)
        start = time.time()

        response = requests.get(url, headers=headers, timeout=300)
        if not response.ok:
            print(f"\n\n  ERRO HTTP {response.status_code}")
            print(f"  URL: {url[:200]}...")
            try:
                err_body = response.json()
                err_msg = err_body.get("error", {}).get("message", response.text[:500])
                print(f"  Mensagem: {err_msg}")
            except Exception:
                print(f"  Resposta: {response.text[:500]}")
            response.raise_for_status()
        data = response.json()

        if total_count is None:
            total_count = data.get("@odata.count")

        records = data.get("value", [])
        all_records.extend(records)

        elapsed = time.time() - start
        print(
            f"{len(records)} registros ({elapsed:.1f}s) "
            f"[total parcial: {len(all_records)}"
            f"{f'/{total_count}' if total_count else ''}]"
        )

        url = data.get("@odata.nextLink")
        page += 1

    return all_records


def records_to_dataframe(records: list) -> pd.DataFrame:
    """Converte os registros da API para DataFrame.

    Quando SELECT_FIELDS está vazio, inclui todos os campos retornados
    (exceto metadados OData que começam com '@').
    """
    rows = []
    for rec in records:
        row = {k: v for k, v in rec.items() if not k.startswith("@")}

        # Se houver dados expandidos do bot, extrair schemaname
        bot_data = rec.get("bot_conversationtranscriptid")
        if isinstance(bot_data, dict):
            row["bot_conversationtranscriptid.schemaname"] = bot_data.get("schemaname")

        rows.append(row)

    return pd.DataFrame(rows)


def select_environment() -> dict:
    """Menu interativo para escolher o ambiente."""
    print("\nAmbientes disponíveis:")
    for key, env in ENVIRONMENTS.items():
        print(f"  [{key}] {env['name']}  ({env['url']})")

    choice = input("\nEscolha o ambiente (número): ").strip()
    if choice not in ENVIRONMENTS:
        print(f"Opção inválida: '{choice}'. Use: {', '.join(ENVIRONMENTS.keys())}")
        sys.exit(1)

    return ENVIRONMENTS[choice]


def main():
    print("=" * 60)
    print("Download de ConversationTranscripts — Dataverse Web API")
    print("=" * 60)

    env = select_environment()
    dataverse_url = env["url"]
    output_path = env["output"]

    password = PASSWORD
    if not password:
        password = input(f"\nSenha para {USERNAME}: ")

    print(f"\n  Ambiente:   {env['name']}")
    print(f"  URL:        {dataverse_url}")
    print(f"  Usuário:    {USERNAME}")
    print(f"  Saída:      {output_path}")
    print()

    # --- Autenticação ---
    print("[1/3] Autenticando...")
    token = acquire_token(dataverse_url, TENANT_ID, CLIENT_ID, USERNAME, password)
    print("  OK — Token obtido com sucesso.\n")

    # --- Download ---
    print("[2/3] Baixando registros...")
    records = fetch_all_records(dataverse_url, token)
    print(f"\n  Total de registros baixados: {len(records)}\n")

    if not records:
        print("Nenhum registro encontrado. Verifique permissões e filtros.")
        return

    # --- Salvar CSV ---
    print("[3/3] Salvando CSV...")
    df = records_to_dataframe(records)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"  Salvo em: {output_path}")
    print(f"  Linhas: {len(df)}")
    print(f"  Colunas: {list(df.columns)}")
    print("\n" + "=" * 60)
    print("Concluído!")
    print("=" * 60)


if __name__ == "__main__":
    main()
