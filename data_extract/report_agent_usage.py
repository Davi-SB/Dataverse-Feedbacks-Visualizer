import pandas as pd
import json
from collections import defaultdict
from datetime import datetime
from typing import Optional

AGENT_COLUMN = 'bot_conversationtranscriptid.schemaname'
TARGET_AGENT = 'cr61e_agenteVirtualOptMove'


def load_user_map(usuarios_path: str) -> dict:
    df = pd.read_csv(usuarios_path, sep=';', encoding='latin-1')
    return dict(zip(df['id'].dropna(), df['displayName'].dropna()))


def get_oldest_message_datetime(csv_path: str) -> Optional[datetime]:
    df = pd.read_csv(csv_path)
    oldest_ts = None

    for content in df['content'].dropna():
        try:
            data = json.loads(content)
            for activity in data.get('activities', []):
                if activity.get('type') != 'message':
                    continue
                ts_ms = activity.get('timestampMs')
                ts = activity.get('timestamp')
                if ts_ms is not None:
                    ts_val = float(ts_ms) / 1000.0
                elif ts is not None:
                    ts_val = float(ts)
                else:
                    continue
                if oldest_ts is None or ts_val < oldest_ts:
                    oldest_ts = ts_val
        except Exception:
            continue

    if oldest_ts is None:
        return None
    return datetime.fromtimestamp(oldest_ts)


def report_agent_usage(csv_path: str, usuarios_path: str, agent: str) -> list[dict]:
    user_map = load_user_map(usuarios_path)

    df = pd.read_csv(csv_path)
    agent_df = df[df[AGENT_COLUMN] == agent]

    conversations_per_user = defaultdict(int)
    messages_per_user = defaultdict(int)

    for _, row in agent_df.iterrows():
        try:
            data = json.loads(row['content'])
            activities = data.get('activities', [])
        except Exception:
            continue

        users_with_message_in_row = set()
        for activity in activities:
            from_data = activity.get('from', {})
            role = from_data.get('role')
            user_id = from_data.get('aadObjectId')

            if role == 1 and user_id and activity.get('type') == 'message':
                messages_per_user[user_id] += 1
                users_with_message_in_row.add(user_id)

        for uid in users_with_message_in_row:
            conversations_per_user[uid] += 1

    results = []
    for uid, name in user_map.items():
        results.append({
            'nome': name,
            'conversas': conversations_per_user.get(uid, 0),
            'mensagens': messages_per_user.get(uid, 0),
        })

    results.sort(key=lambda r: (r['mensagens'], r['conversas']), reverse=True)
    return results


def print_report(results: list[dict], agent: str, oldest_message_at: Optional[datetime] = None):
    sep = '=' * 70
    dash = '-' * 70
    header = f"{'#':<4} {'Nome':<40} {'Conversas':>10} {'Mensagens':>10}"

    print(sep)
    print(f"Relatorio de Uso - Agente: {agent}")
    if oldest_message_at is not None:
        print(f"Mensagem mais antiga no arquivo: {oldest_message_at.strftime('%d/%m/%Y %H:%M:%S')}")
    print(sep)
    print(header)
    print(dash)

    for i, r in enumerate(results, 1):
        print(f"{i:<4} {r['nome']:<40} {r['conversas']:>10} {r['mensagens']:>10}")

    print(sep)

    total_conv = sum(r['conversas'] for r in results)
    total_msg = sum(r['mensagens'] for r in results)
    users_active = sum(1 for r in results if r['mensagens'] > 0)
    print(f"Usuarios com uso: {users_active}/{len(results)}")
    print(f"Total de conversas: {total_conv}")
    print(f"Total de mensagens: {total_msg}")
    print(sep)


if __name__ == '__main__':
    csv_path = 'conversationtranscripts.csv'
    results = report_agent_usage(
        csv_path=csv_path,
        usuarios_path='usuarios.csv',
        agent=TARGET_AGENT,
    )
    oldest_message_at = get_oldest_message_datetime(csv_path)
    print_report(results, TARGET_AGENT, oldest_message_at)
