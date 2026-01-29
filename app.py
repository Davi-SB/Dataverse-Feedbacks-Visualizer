import streamlit as st
import pandas as pd
import json
from datetime import datetime

debug = True

# Configuração da página
st.set_page_config(page_title="Visualizador de Transcrições", layout="wide", page_icon="💬")


# ============================================================================
# FUNÇÕES DE CACHE E OTIMIZAÇÃO
# ============================================================================

@st.cache_data(show_spinner=False)
def load_csv_data(csv_path):
    """Carrega o CSV uma única vez e cacheia."""
    if debug: print("Carregando CSV...")
    return pd.read_csv(csv_path)


@st.cache_data(show_spinner=False)
def parse_all_json_content(df_content_series):
    """
    Parseia todos os JSONs do CSV uma única vez.
    Retorna um dicionário {índice: dados_parseados}.
    """
    if debug: print("Parseando todos os JSONs do CSV...")
    parsed_data = {}
    for idx, content in enumerate(df_content_series):
        try:
            if pd.notna(content):
                parsed_data[idx] = json.loads(content)
            else:
                parsed_data[idx] = None
        except json.JSONDecodeError:
            parsed_data[idx] = None
    return parsed_data


@st.cache_data(show_spinner=False)
def build_global_id_map(df_content_series):
    """
    Constrói um mapa global de TODOS os IDs de mensagens do CSV inteiro.
    Retorna: {message_id: {'rows': [lista de índices], 'type': tipo, 'text': texto}}
    
    Isso permite buscar mensagens que estão em OUTRAS linhas do CSV.
    """
    if debug: print("Construindo mapa global de IDs...")
    global_id_map = {}
    
    for idx, content in enumerate(df_content_series):
        try:
            if pd.isna(content):
                continue
            data = json.loads(content)
            activities = data.get('activities', [])
            
            for activity in activities:
                activity_id = activity.get('id')
                if not activity_id:
                    continue
                
                if activity_id not in global_id_map:
                    global_id_map[activity_id] = {
                        'rows': [],
                        'type': activity.get('type'),
                        'text': activity.get('text', '')[:200] if activity.get('text') else '',
                        'from_role': activity.get('from', {}).get('role')
                    }
                global_id_map[activity_id]['rows'].append(idx)
        except Exception:
            continue
    
    return global_id_map


@st.cache_data(show_spinner=False)
def compute_feedback_column(df_content_series, _all_feedbacks_map):
    """
    Calcula a coluna 'feedback' para todas as linhas de uma vez (cacheado).
    Retorna uma lista de valores ('POSITIVO', 'NEGATIVO', ou '').
    """
    if debug: print("Calculando coluna de feedback...")
    feedback_values = []
    
    for content in df_content_series:
        try:
            if pd.isna(content):
                feedback_values.append('')
                continue
                
            data = json.loads(content)
            activities = data.get('activities', [])
            
            # Coletar IDs de mensagens desta linha
            message_ids = set()
            for activity in activities:
                msg_id = activity.get('id')
                if not msg_id:
                    continue
                if activity.get('type') == 'message':
                    message_ids.add(msg_id)
                elif (activity.get('type') == 'trace' and
                      activity.get('valueType') == 'VariableAssignment' and
                      activity.get('value', {}).get('name') == 'GeneratedAnswer'):
                    message_ids.add(msg_id)
            
            # Verificar feedbacks
            has_positive = False
            has_negative = False
            for msg_id in message_ids:
                feedbacks = _all_feedbacks_map.get(msg_id, [])
                for feedback in feedbacks:
                    reaction = feedback.get('reaction', '')
                    if reaction == 'like':
                        has_positive = True
                    elif reaction == 'dislike':
                        has_negative = True
            
            if has_negative:
                feedback_values.append('NEGATIVO')
            elif has_positive:
                feedback_values.append('POSITIVO')
            else:
                feedback_values.append('')
        except Exception:
            feedback_values.append('')
    
    return feedback_values


@st.cache_data(show_spinner=False)
def compute_statistics(df_content_series, _all_feedbacks_map):
    """
    Calcula estatísticas de feedbacks uma única vez (cacheado).
    Retorna: (total_positive, total_negative)
    
    IMPORTANTE: Conta TODOS os feedbacks do mapa, não apenas os associados
    a mensagens encontradas nas linhas filtradas.
    """
    if debug: print("Calculando estatísticas de feedback...")
    total_positive = 0
    total_negative = 0
    
    # Coletar IDs de mensagens E traces das linhas filtradas
    all_message_ids = set()
    for content in df_content_series:
        try:
            if pd.isna(content):
                continue
            data = json.loads(content)
            activities = data.get('activities', [])
            for activity in activities:
                msg_id = activity.get('id')
                if not msg_id:
                    continue
                # Mensagem tradicional
                if activity.get('type') == 'message':
                    all_message_ids.add(msg_id)
                # Trace/GeneratedAnswer (também pode receber feedback)
                elif (activity.get('type') == 'trace' and
                      activity.get('valueType') == 'VariableAssignment' and
                      activity.get('value', {}).get('name') == 'GeneratedAnswer'):
                    all_message_ids.add(msg_id)
        except:
            continue
    
    # Contar feedbacks para os IDs encontrados
    for msg_id in all_message_ids:
        feedbacks = _all_feedbacks_map.get(msg_id, [])
        for feedback in feedbacks:
            reaction = feedback.get('reaction', '')
            if reaction == 'like':
                total_positive += 1
            elif reaction == 'dislike':
                total_negative += 1
    
    return total_positive, total_negative

# CSS customizado para mensagens e feedbacks
st.markdown("""
<style>
    .message-user {
        background-color: #FFFFFF;
        border-left: 4px solid #666666;
        padding: 15px;
        margin: 10px 0;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .message-bot {
        background-color: #E3F2FD;
        border-left: 4px solid #2196F3;
        padding: 15px;
        margin: 10px 0;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .message-feedback-positive {
        background-color: #C8E6C9;
        border-left: 4px solid #4CAF50;
        padding: 15px;
        margin: 10px 0 10px 30px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .message-feedback-negative {
        background-color: #FFCDD2;
        border-left: 4px solid #F44336;
        padding: 15px;
        margin: 10px 0 10px 30px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    
    .header {
        font-weight: bold;
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        color: #333;
    }
    
    .header span {
        font-weight: normal;
        font-size: 0.85em;
        color: #666;
    }
    
    .text {
        color: #000;
        line-height: 1.5;
    }
    
    .feedback-counter {
        color: #666;
        font-size: 0.85em;
        margin-bottom: 4px;
    }
    
    .row-number {
        background-color: #FFF3E0;
        border: 2px solid #FF9800;
        padding: 10px;
        border-radius: 8px;
        margin-bottom: 15px;
        text-align: center;
        font-weight: bold;
        color: #E65100;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def load_all_feedbacks(df_content_series, _global_id_map):
    """
    Carrega TODOS os feedbacks de TODAS as linhas do CSV.
    Retorna um dicionário mapeando message_id -> lista de feedbacks.
    
    LÓGICA DE BUSCA (em ordem de prioridade):
    1. BUSCA GLOBAL POR ID: Usa o mapa global para encontrar o ID em QUALQUER linha
    2. BUSCA TEMPORAL (Heurística): Para IDs não encontrados, busca a mensagem de BOT 
       mais próxima ANTES do feedback NA MESMA LINHA
    
    TIPOS DE FEEDBACK CAPTURADOS:
    - invoke com actionName='feedback' (feedback com texto e reação like/dislike)
    
    NOTA: messageReaction não é capturado porque no dataset atual não contém 
    informação sobre o tipo de reação (like/dislike), apenas que houve interação.
    """
    if debug: print("Carregando todos os feedbacks...")
    all_feedbacks = {}  # {message_id: [lista de feedbacks]}
    
    for idx, content in enumerate(df_content_series):
        try:
            if pd.isna(content):
                continue
            data = json.loads(content)
            activities = data.get('activities', [])
            
            # Ordenar atividades cronologicamente (essencial para heurística temporal)
            activities.sort(key=lambda x: x.get('timestamp', 0))
            
            # ================================================================
            # Feedbacks invoke (actionName='feedback')
            # ================================================================
            for i, activity in enumerate(activities):
                if (activity.get('type') == 'invoke' and 
                    activity.get('name') == 'message/submitAction'):
                    
                    value = activity.get('value', {})
                    if value.get('actionName') == 'feedback':
                        target_msg_id = activity.get('replyToId')
                        found_msg_id = None
                        metodo = None
                        
                        # TENTATIVA 1: Busca GLOBAL por ID (em TODAS as linhas)
                        if target_msg_id and target_msg_id in _global_id_map:
                            found_msg_id = target_msg_id
                            # Verificar se está na mesma linha ou em outra
                            rows_with_id = _global_id_map[target_msg_id]['rows']
                            if idx in rows_with_id:
                                metodo = 'ID'
                            else:
                                metodo = 'ID_CROSS'  # ID encontrado em outra linha
                        
                        # TENTATIVA 2: Busca temporal (Heurística) - fallback
                        # Procura a mensagem de BOT mais próxima ANTES deste feedback
                        if not found_msg_id:
                            for j in range(i - 1, -1, -1):
                                cand = activities[j]
                                role = cand.get('from', {}).get('role')
                                cand_id = cand.get('id')
                                
                                # Verifica se é mensagem tradicional do Bot (role 0)
                                is_bot_message = cand.get('type') == 'message' and role == 0
                                
                                # Verifica se é trace/GeneratedAnswer do Bot
                                is_generated_answer = (
                                    cand.get('type') == 'trace' and
                                    cand.get('valueType') == 'VariableAssignment' and
                                    cand.get('value', {}).get('name') == 'GeneratedAnswer' and
                                    role == 0
                                )
                                
                                if (is_bot_message or is_generated_answer) and cand_id:
                                    found_msg_id = cand_id
                                    metodo = 'TEMPO'
                                    break
                        
                        # Se encontrou a mensagem alvo, associar o feedback
                        if found_msg_id:
                            if found_msg_id not in all_feedbacks:
                                all_feedbacks[found_msg_id] = []
                            
                            feedback_data = value.get('actionValue', {}).copy()
                            feedback_data['_metodo_identificacao'] = metodo
                            all_feedbacks[found_msg_id].append(feedback_data)
                        
        except Exception:
            continue
    
    return all_feedbacks


def extract_feedback_column(json_string, all_feedbacks_map, _global_id_map):
    """
    Retorna POSITIVO, NEGATIVO ou vazio para a coluna feedback.
    
    Esta função verifica se as MENSAGENS desta linha receberam feedbacks,
    independentemente de em qual linha do CSV o feedback está.
    
    REGRA: A coluna 'feedback' indica se alguma mensagem DESTA linha
    recebeu feedback, não se esta linha contém atividades de feedback.
    """
    if debug: print("Extraindo coluna de feedback...")
    try:
        data = json.loads(json_string)
        activities = data.get('activities', [])
        
        # Coletar IDs de mensagens desta linha
        message_ids = set()
        for activity in activities:
            msg_id = activity.get('id')
            if not msg_id:
                continue
                
            # Mensagem tradicional
            if activity.get('type') == 'message':
                message_ids.add(msg_id)
            
            # Trace/GeneratedAnswer do Bot
            elif (activity.get('type') == 'trace' and
                  activity.get('valueType') == 'VariableAssignment' and
                  activity.get('value', {}).get('name') == 'GeneratedAnswer'):
                message_ids.add(msg_id)
        
        # Verificar se alguma mensagem desta linha recebeu feedback
        has_positive = False
        has_negative = False
        
        for msg_id in message_ids:
            feedbacks = all_feedbacks_map.get(msg_id, [])
            for feedback in feedbacks:
                reaction = feedback.get('reaction', '')
                if reaction == 'like':
                    has_positive = True
                elif reaction == 'dislike':
                    has_negative = True
        
        # Priorizar negativo se houver ambos
        if has_negative:
            return 'NEGATIVO'
        elif has_positive:
            return 'POSITIVO'
        else:
            return ''
    except Exception:
        return ''


def format_timestamp(timestamp_str):
    """
    Formata timestamp para formato legível: HH:MM:SS
    """
    try:
        # Tentar como ISO string
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%H:%M:%S')
    except:
        try:
            # Tentar como timestamp Unix (segundos desde epoch)
            if isinstance(timestamp_str, (int, float)) or (isinstance(timestamp_str, str) and timestamp_str.isdigit()):
                dt = datetime.fromtimestamp(int(timestamp_str))
                return dt.strftime('%H:%M:%S')
        except:
            pass
        return str(timestamp_str)


def extract_chat_content(parsed_data, all_feedbacks_map):
    """
    Extrai mensagens de UMA linha do CSV (já parseada) e associa feedbacks de TODAS as linhas.
    
    Args:
        parsed_data: Dados JSON já parseados da linha atual
        all_feedbacks_map: Dicionário com TODOS os feedbacks do CSV inteiro
    
    Returns:
        Lista de mensagens com seus feedbacks associados
    """
    if debug: print("Extraindo conteúdo do chat...")
    try:
        if parsed_data is None:
            return []
            
        activities = parsed_data.get('activities', [])
        
        # Ordenar atividades cronologicamente para exibição correta
        activities.sort(key=lambda x: x.get('timestamp', 0))
        
        # Extrair mensagens desta linha
        messages = []
        for activity in activities:
            msg_id = activity.get('id')
            text = None
            is_user = False
            should_include = False
            
            # Mensagem tradicional
            if activity.get('type') == 'message':
                text = activity.get('text', '').strip()
                is_user = activity.get('from', {}).get('role') == 1
                
                # Verificar se tem attachments (cards visuais)
                if not text:
                    if activity.get('attachments'):
                        text = "[Conteúdo Visual/Card]"
                        should_include = True
                    else:
                        # Verificar se tem feedback associado (mensagem vazia com feedback)
                        if msg_id and msg_id in all_feedbacks_map:
                            text = "[Mensagem sem texto]"
                            should_include = True
                else:
                    should_include = True
            
            # Trace/GeneratedAnswer do Bot (nova estrutura)
            elif (activity.get('type') == 'trace' and
                  activity.get('valueType') == 'VariableAssignment' and
                  activity.get('value', {}).get('name') == 'GeneratedAnswer'):
                text = activity.get('value', {}).get('newValue', '').strip()
                is_user = False  # GeneratedAnswer é sempre do bot
                
                if text:
                    should_include = True
                elif msg_id and msg_id in all_feedbacks_map:
                    # Trace vazio mas com feedback
                    text = "[Resposta gerada vazia]"
                    should_include = True
            
            # Se encontrou uma mensagem válida ou com feedback, adicionar à lista
            if should_include and msg_id:
                # Buscar feedbacks para esta mensagem em TODAS as linhas do CSV
                feedbacks_for_this_message = all_feedbacks_map.get(msg_id, [])
                
                messages.append({
                    'id': msg_id,
                    'time': format_timestamp(activity.get('timestamp', '')),
                    'is_user': is_user,
                    'text': text,
                    'feedbacks': feedbacks_for_this_message
                })
        
        return messages
    except Exception as e:
        st.error(f"Erro ao processar chat: {str(e)}")
        return []


def extract_feedback_text(feedback_value):
    """
    Extrai o texto do feedback do campo 'feedback' que é uma string JSON.
    """
    try:
        feedback_str = feedback_value.get('feedback', '{}')
        if isinstance(feedback_str, str):
            feedback_data = json.loads(feedback_str)
            return feedback_data.get('feedbackText', '[Sem comentário]')
        return '[Sem comentário]'
    except:
        return '[Sem comentário]'


def render_chat_message(msg):
    """
    Renderiza uma mensagem do chat com seus feedbacks (se houver).
    """
    # Determinar classe CSS baseado no tipo de mensagem
    msg_class = "message-user" if msg['is_user'] else "message-bot"
    emoji = "👤" if msg['is_user'] else "🤖"
    role = "USUÁRIO" if msg['is_user'] else "BOT"
    
    # Construir HTML da mensagem
    html = f"""
    <div class="{msg_class}">
        <div class="header">{emoji} {role} <span>{msg['time']}</span></div>
        <div class="text">{msg['text']}</div>
    </div>
    """
    
    # Renderizar a mensagem principal
    st.markdown(html, unsafe_allow_html=True)
    
    # Renderizar feedbacks como mensagens separadas (se existirem)
    feedbacks = msg.get('feedbacks', [])
    if feedbacks:
        for idx, feedback in enumerate(feedbacks, 1):
            reaction = feedback.get('reaction', '')
            feedback_text = extract_feedback_text(feedback)
            
            # Determinar estilo do feedback
            if reaction == 'like':
                feedback_class = "message-feedback-positive"
                emoji_fb = "✅"
                label = "FEEDBACK POSITIVO"
            else:
                feedback_class = "message-feedback-negative"
                emoji_fb = "❌"
                label = "FEEDBACK NEGATIVO"
            
            # Adicionar contador se houver múltiplos feedbacks
            counter_text = ""
            if len(feedbacks) > 1:
                counter_text = f" #{idx}"
            
            # Obter método de identificação
            metodo = feedback.get('_metodo_identificacao', 'ID')
            if metodo == 'ID':
                metodo_badge = '<span style="background-color: #1976D2; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin-left: 8px;">🔗 ID</span>'
            elif metodo == 'ID_CROSS':
                metodo_badge = '<span style="background-color: #9C27B0; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin-left: 8px;">🔗 ID (outra linha)</span>'
            else:
                metodo_badge = '<span style="background-color: #FF9800; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin-left: 8px;">⏱️ TEMPO</span>'
            
            # Renderizar feedback como uma mensagem separada
            feedback_html = f"""
            <div class="{feedback_class}">
                <div class="header">{emoji_fb} {label}{counter_text} {metodo_badge}</div>
                <div class="text">{feedback_text}</div>
            </div>
            """
            
            st.markdown(feedback_html, unsafe_allow_html=True)


def format_datetime(datetime_str):
    """
    Formata datetime para AAAA/MM/DD
    """
    try:
        dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        return dt.strftime('%Y/%m/%d')
    except:
        return datetime_str


# ============================================================================
# APLICAÇÃO PRINCIPAL
# ============================================================================

st.title("📊 Visualizador de Transcrições de Chat")

# Carregar CSV
try:
    # Carregar dados com cache (executa só uma vez)
    df = load_csv_data('conversationtranscripts.csv')
    
    # Construir mapa global de IDs (com cache)
    with st.spinner("Construindo índice de mensagens..."):
        global_id_map = build_global_id_map(tuple(df['content'].tolist()))
    
    # Carregar TODOS os feedbacks do CSV (com cache)
    with st.spinner("Carregando feedbacks..."):
        all_feedbacks_global = load_all_feedbacks(
            tuple(df['content'].tolist()), 
            global_id_map
        )
    
    # Parsear todos os JSONs (com cache) para visualização rápida
    with st.spinner("Preparando dados..."):
        parsed_json_cache = parse_all_json_content(tuple(df['content'].tolist()))
    
    # Adicionar coluna de feedback (CACHEADO)
    content_tuple = tuple(df['content'].tolist())
    df['feedback'] = compute_feedback_column(content_tuple, all_feedbacks_global)
    
    # Formatar conversationstarttime se existir
    if 'conversationstarttime' in df.columns:
        df['conversationstarttime_formatted'] = df['conversationstarttime'].apply(format_datetime)
        # Criar coluna de data (sem hora) para filtro
        df['conversation_date'] = pd.to_datetime(df['conversationstarttime'], errors='coerce').dt.date
    
    # ========================================================================
    # SIDEBAR - CONTROLES
    # ========================================================================
    
    st.sidebar.header("⚙️ Configurações")
    
    # Seleção de colunas visíveis
    st.sidebar.subheader("Colunas Visíveis")
    all_columns = [col for col in df.columns if col != 'conversationstarttime']
    
    # Colunas padrão visíveis
    default_visible = ['feedback', 'content']
    if 'conversationstarttime_formatted' in df.columns:
        default_visible.insert(1, 'conversationstarttime_formatted')
    
    visible_columns = st.sidebar.multiselect(
        "Selecione as colunas:",
        options=all_columns,
        default=[col for col in default_visible if col in all_columns]
    )
    
    # Filtro de feedback
    st.sidebar.subheader("Filtros")
    only_with_feedback = st.sidebar.checkbox("Mostrar apenas conversas com feedback")
    
    # Filtro de data
    if 'conversation_date' in df.columns:
        min_date = df['conversation_date'].min()
        max_date = df['conversation_date'].max()
        
        if pd.notna(min_date) and pd.notna(max_date):
            selected_date = st.sidebar.date_input(
                "Data inicial:",
                value=min_date,
                min_value=min_date,
                max_value=max_date,
                help="Mostra conversas desta data em diante"
            )
    
    # Painel de estatísticas (CACHEADO)
    st.sidebar.subheader("📈 Estatísticas")
    
    # Aplicar filtro de data para estatísticas
    df_stats = df.copy()
    if 'conversation_date' in df.columns and pd.notna(min_date) and pd.notna(max_date):
        df_stats = df_stats[df_stats['conversation_date'] >= selected_date]
    
    # Usar função cacheada para calcular estatísticas
    stats_content_tuple = tuple(df_stats['content'].tolist())
    total_positive, total_negative = compute_statistics(stats_content_tuple, all_feedbacks_global)
    
    total_conversations = len(df_stats)
    
    st.sidebar.metric("Total de Conversas", total_conversations)
    st.sidebar.metric("✅ Feedbacks Positivos", total_positive)
    st.sidebar.metric("❌ Feedbacks Negativos", total_negative)
    st.sidebar.metric("📈 Total de Feedbacks", total_positive + total_negative)
    
    if total_positive + total_negative > 0:
        percentual_positivo = (total_positive / (total_positive + total_negative)) * 100
        st.sidebar.metric("Percentual Positivo", f"{percentual_positivo:.1f}%")
    
    # ========================================================================
    # LAYOUT PRINCIPAL - 2 COLUNAS
    # ========================================================================
    
    col_left, col_right = st.columns([1, 1])
    
    with col_left:
        st.header("📋 Lista de Conversas")
        
        # Aplicar filtro
        df_display = df.copy()
        if only_with_feedback:
            df_display = df_display[df_display['feedback'] != '']
        
        # Aplicar filtro de data
        if 'conversation_date' in df.columns and pd.notna(min_date) and pd.notna(max_date):
            df_display = df_display[df_display['conversation_date'] >= selected_date]
        
        # Garantir que 'feedback' esteja nas colunas visíveis
        if 'feedback' not in visible_columns and len(visible_columns) > 0:
            visible_columns = ['feedback'] + visible_columns
        
        # Mostrar dataframe
        if len(visible_columns) > 0:
            # Adicionar coluna de índice original para referência
            df_display['#'] = df_display.index
            display_cols = ['#'] + visible_columns
            
            st.dataframe(
                df_display[display_cols],
                use_container_width=True,
                hide_index=True
            )
            
            # Seletor de linha
            st.subheader("Selecione uma conversa para visualizar")
            
            col_input, col_spacer = st.columns([1, 2])
            
            with col_input:
                selected_index = st.number_input(
                    "Digite o número da linha (#):",
                    min_value=0,
                    max_value=len(df)-1,
                    value=0,
                    step=1
                )
            
            if st.button("🔍 Visualizar Conversa", type="primary"):
                st.session_state['selected_row'] = selected_index
        else:
            st.warning("Selecione pelo menos uma coluna para visualizar.")
    
    with col_right:
        st.header("💬 Visualização do Chat")
        
        if 'selected_row' in st.session_state:
            row_idx = st.session_state['selected_row']
            
            # Mostrar número da linha
            st.markdown(
                f'<div class="row-number">📍 LINHA #{row_idx}</div>',
                unsafe_allow_html=True
            )
            
            # Extrair mensagens usando o cache de JSON parseado
            parsed_data = parsed_json_cache.get(row_idx)
            messages = extract_chat_content(parsed_data, all_feedbacks_global)
            
            if messages:
                st.info(f"**Total de mensagens:** {len(messages)}")
                
                # Renderizar cada mensagem
                for msg in messages:
                    render_chat_message(msg)
            else:
                st.warning("Nenhuma mensagem encontrada nesta conversa.")
        else:
            st.info("👈 Selecione uma conversa na lista à esquerda e clique em 'Visualizar Conversa'")

except FileNotFoundError:
    st.error("❌ Arquivo 'conversationtranscripts.csv' não encontrado!")
    st.info("Certifique-se de que o arquivo está no mesmo diretório que app.py")
except Exception as e:
    st.error(f"❌ Erro ao carregar dados: {str(e)}")
    st.exception(e)
