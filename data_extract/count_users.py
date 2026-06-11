import math
import pandas as pd
import json
from datetime import datetime, date
from collections import defaultdict

AGENT_COLUMN = 'bot_conversationtranscriptid.schemaname'


def count_distinct_users(csv_path: str, start_date: str) -> dict:
    """
    Conta usuários distintos no CSV de transcrições a partir de uma data,
    agrupados por agente.
    
    Args:
        csv_path: Caminho para o arquivo CSV
        start_date: Data inicial no formato 'YYYY-MM-DD' (ex: '2025-01-01')
    
    Returns:
        Dicionário com estatísticas dos usuários por agente e totais
    """
    df = pd.read_csv(csv_path)
    
    filter_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    if 'conversationstarttime' in df.columns:
        df['conversation_date'] = pd.to_datetime(df['conversationstarttime'], errors='coerce').dt.date
        df = df[df['conversation_date'] >= filter_date]
    
    users_by_agent = defaultdict(set)
    conversations_by_agent = defaultdict(int)
    dates_by_agent = defaultdict(set)
    all_users = set()
    all_dates = set()
    
    for _, row in df.iterrows():
        agent = row.get(AGENT_COLUMN, 'Desconhecido') if AGENT_COLUMN in df.columns else 'Desconhecido'
        if pd.isna(agent):
            agent = 'Desconhecido'
        
        conversations_by_agent[agent] += 1
        
        conv_date = row.get('conversation_date')
        if conv_date and not pd.isna(conv_date):
            dates_by_agent[agent].add(conv_date)
            all_dates.add(conv_date)
        
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
                    
        except Exception:
            continue
    
    def _weeks_in_range(dates: set) -> float:
        if not dates:
            return 1.0
        min_d = min(dates)
        max_d = max(dates)
        days = (max_d - min_d).days + 1
        return max(days / 7.0, 1.0)
    
    total_weeks = _weeks_in_range(all_dates)
    
    per_agent = {}
    for agent in sorted(set(list(users_by_agent.keys()) + list(conversations_by_agent.keys()))):
        agent_convs = conversations_by_agent.get(agent, 0)
        agent_weeks = _weeks_in_range(dates_by_agent.get(agent, set()))
        per_agent[agent] = {
            'usuarios_distintos': len(users_by_agent.get(agent, set())),
            'conversas_analisadas': agent_convs,
            'media_conversas_por_semana': round(agent_convs / agent_weeks, 1),
            'lista_ids': list(users_by_agent.get(agent, set())),
        }
    
    return {
        'total_usuarios_distintos': len(all_users),
        'data_inicial': start_date,
        'total_conversas_analisadas': len(df),
        'media_conversas_por_semana': round(len(df) / total_weeks, 1),
        'por_agente': per_agent,
    }


if __name__ == "__main__":
    # =====================================================
    # PARÂMETRO: Altere a data inicial aqui
    # =====================================================
    DATA_INICIAL = "2026-01-24"  # Formato: YYYY-MM-DD
    
    CSV_PATH = "conversationtranscripts.csv"
    
    print(f"Contando usuarios distintos desde {DATA_INICIAL}...")
    print("=" * 60)
    
    resultado = count_distinct_users(CSV_PATH, DATA_INICIAL)
    
    print(f"Data inicial: {resultado['data_inicial']}")
    print(f"Conversas analisadas (total): {resultado['total_conversas_analisadas']}")
    print(f"Usuarios distintos (total): {resultado['total_usuarios_distintos']}")
    print(f"Media de conversas por semana (total): {resultado['media_conversas_por_semana']}")
    print("=" * 60)
    
    for agent, stats in resultado['por_agente'].items():
        print(f"\n--- Agente: {agent} ---")
        print(f"  Conversas analisadas:        {stats['conversas_analisadas']}")
        print(f"  Usuarios distintos:          {stats['usuarios_distintos']}")
        print(f"  Media conversas por semana:  {stats['media_conversas_por_semana']}")
        
        # if stats['lista_ids']:
            # print(f"  Primeiros 10 IDs:")
            # for i, user_id in enumerate(stats['lista_ids'][:10], 1):
            #     print(f"    {i}. {user_id}")
            # if len(stats['lista_ids']) > 10:
            #     print(f"    ... e mais {len(stats['lista_ids']) - 10} usuarios")
