import pandas as pd
import json
from datetime import datetime


def count_distinct_users(csv_path: str, start_date: str) -> dict:
    """
    Conta usuários distintos no CSV de transcrições a partir de uma data.
    
    Args:
        csv_path: Caminho para o arquivo CSV
        start_date: Data inicial no formato 'YYYY-MM-DD' (ex: '2025-01-01')
    
    Returns:
        Dicionário com estatísticas dos usuários
    """
    df = pd.read_csv(csv_path)
    
    # Converter data de filtro
    filter_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    
    # Filtrar por data se a coluna existir
    if 'conversationstarttime' in df.columns:
        df['conversation_date'] = pd.to_datetime(df['conversationstarttime'], errors='coerce').dt.date
        df = df[df['conversation_date'] >= filter_date]
    
    # Set para armazenar IDs únicos de usuários
    distinct_users = set()
    
    # Processar cada linha do CSV
    for _, row in df.iterrows():
        try:
            data = json.loads(row['content'])
            activities = data.get('activities', [])
            
            for activity in activities:
                from_data = activity.get('from', {})
                role = from_data.get('role')
                user_id = from_data.get('aadObjectId')
                
                # Verificar se é um usuário (role == 1) e tem ID
                if role == 1 and user_id:
                    distinct_users.add(user_id)
                    
        except Exception as e:
            continue
    
    return {
        'total_usuarios_distintos': len(distinct_users),
        'data_inicial': start_date,
        'total_conversas_analisadas': len(df),
        'lista_ids': list(distinct_users)
    }


if __name__ == "__main__":
    # =====================================================
    # PARÂMETRO: Altere a data inicial aqui
    # =====================================================
    DATA_INICIAL = "2025-12-15"  # Formato: YYYY-MM-DD
    
    CSV_PATH = "conversationtranscripts.csv"
    
    print(f"🔍 Contando usuários distintos desde {DATA_INICIAL}...")
    print("-" * 50)
    
    resultado = count_distinct_users(CSV_PATH, DATA_INICIAL)
    
    print(f"📅 Data inicial: {resultado['data_inicial']}")
    print(f"📊 Conversas analisadas: {resultado['total_conversas_analisadas']}")
    print(f"👥 Usuários distintos: {resultado['total_usuarios_distintos']}")
    print("-" * 50)
    
    # Opcional: mostrar os primeiros IDs
    if resultado['lista_ids']:
        print("\n📋 Primeiros 10 IDs de usuários:")
        for i, user_id in enumerate(resultado['lista_ids'][:10], 1):
            print(f"   {i}. {user_id}")
        
        if len(resultado['lista_ids']) > 10:
            print(f"   ... e mais {len(resultado['lista_ids']) - 10} usuários")
