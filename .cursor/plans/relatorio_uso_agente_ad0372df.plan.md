---
name: Relatorio uso agente
overview: Criar um script Python que gera um relatorio de uso do agente "cr61e_agenteVirtualOptMove" por usuario, mapeando IDs para nomes via usuarios.csv, ordenado do maior para o menor uso.
todos:
  - id: create-report-script
    content: Criar novo arquivo report_agent_usage.py com toda a logica de relatorio (carregar usuarios, filtrar agente, contar uso, imprimir)
    status: completed
isProject: false
---

# Relatorio de Uso do Agente cr61e_agenteVirtualOptMove

## Contexto

O arquivo [conversationtranscripts.csv](conversationtranscripts.csv) contem transcrições de conversas com agentes. Cada linha possui uma coluna `content` com JSON contendo `activities`, onde cada atividade de usuario (role == 1) possui o campo `from.aadObjectId` com o ID do usuario.

O arquivo [usuarios.csv](usuarios.csv) (separador `;`) contem a coluna `id` (AAD Object ID) e `displayName` para mapeamento.

O arquivo [count_users.py](count_users.py) ja implementa a logica base de:
- Ler o CSV com pandas
- Filtrar por agente usando a coluna `bot_conversationtranscriptid.schemaname`
- Parsear o JSON de `content` e extrair `aadObjectId` de atividades com `role == 1`

## Abordagem

Criar um **novo arquivo** `report_agent_usage.py` (o [count_users.py](count_users.py) permanece inalterado). O script:

1. **Carrega o mapeamento de usuarios** a partir de `usuarios.csv` (separador `;`, encoding `latin-1`), criando um dicionario `{id: displayName}`
2. **Filtra as conversas** do CSV para o agente `cr61e_agenteVirtualOptMove` (coluna `bot_conversationtranscriptid.schemaname`)
3. **Conta o uso por usuario**, iterando as activities de cada conversa filtrada:
   - Conversas: quantas linhas (conversas distintas) o usuario participou
   - Mensagens: quantas mensagens (activities com `type == "message"` e `role == 1`) o usuario enviou
4. **Monta a tabela final** com todos os usuarios de `usuarios.csv`, incluindo os que tiveram 0 uso
5. **Ordena** do maior para o menor uso (por mensagens enviadas)
6. **Imprime o relatorio** formatado no console

## Metricas por usuario

- **Nome** (de `usuarios.csv`)
- **Conversas** (quantidade de conversas distintas em que participou)
- **Mensagens enviadas** (quantidade total de mensagens type=message com role=1)

## Codigo-chave (de [count_users.py](count_users.py))

A logica de extracao de usuario ja existe e sera reutilizada:

```48:59:count_users.py
        try:
            data = json.loads(row['content'])
            activities = data.get('activities', [])
            
            for activity in activities:
                from_data = activity.get('from', {})
                role = from_data.get('role')
                user_id = from_data.get('aadObjectId')
                
                if role == 1 and user_id:
                    users_by_agent[agent].add(user_id)
                    all_users.add(user_id)
```

A logica sera reutilizada no novo arquivo `report_agent_usage.py`, mas em vez de apenas coletar IDs unicos, contaremos conversas e mensagens por usuario. O `count_users.py` **nao sera modificado**.

## Saida esperada

```
============================================================
Relatorio de Uso - Agente: cr61e_agenteVirtualOptMove
============================================================
#   Nome                                Conversas  Mensagens
------------------------------------------------------------
1   Fulano de Tal                             15        42
2   Ciclano Silva                              8        23
...
30  Beltrano Costa                             0         0
============================================================
```
