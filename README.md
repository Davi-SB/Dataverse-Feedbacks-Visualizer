# 📊 Visualizador de Transcrições de Chat com Análise de Feedbacks

Um sistema web desenvolvido em Streamlit para visualização e análise de transcrições de conversas de chat, com foco na análise de feedbacks positivos e negativos dos usuários.

## 🎯 Funcionalidades

### 📈 Análise de Feedbacks
- **Visualização de feedbacks**: Classifica e exibe feedbacks como positivos (✅) ou negativos (❌)
- **Estatísticas em tempo real**: Métricas de total de conversas, feedbacks positivos/negativos e percentuais
- **Identificação inteligente**: Sistema que associa feedbacks às mensagens correspondentes usando:
  - Busca global por ID (em todas as linhas do CSV)
  - Busca temporal heurística para casos não identificados por ID
  - Suporte a feedbacks cruzados entre diferentes linhas

### 💬 Visualização de Conversas
- **Interface intuitiva**: Exibição clara de mensagens de usuários (👤) e bots (🤖)
- **Timestamps formatados**: Horários de cada mensagem no formato HH:MM:SS
- **Suporte a múltiplos tipos de conteúdo**:
  - Mensagens de texto tradicionais
  - Traces/GeneratedAnswer (respostas geradas)
  - Cards visuais e attachments
  - Mensagens vazias com feedbacks associados

### 🔍 Funcionalidades de Análise
- **Filtros avançados**:
  - Por data (conversas a partir de uma data específica)
  - Apenas conversas com feedbacks
  - Seleção de colunas visíveis
- **Navegação eficiente**: Lista paginada de conversas com visualização individual
- **Cache inteligente**: Sistema otimizado para processamento rápido de grandes datasets

### 👥 Contagem de Usuários
- **Análise demográfica**: Script auxiliar para contagem de usuários distintos
- **Filtragem temporal**: Contagem a partir de datas específicas
- **Identificação única**: Baseada em `aadObjectId` dos usuários

## 🚀 Como Usar

### Pré-requisitos
```bash
pip install streamlit pandas
```

### Execução
1. **Prepare seus dados**: Certifique-se de ter um arquivo `conversationtranscripts.csv` no diretório raiz
2. **Execute o aplicativo**:
   ```bash
   streamlit run app.py
   ```
3. **Acesse**: O app será aberto automaticamente no navegador (geralmente `http://localhost:8501`)

### Análise de Usuários
Para contar usuários distintos:
```python
from count_users import count_distinct_users

# Conta usuários a partir de 1º de janeiro de 2025
resultado = count_distinct_users('conversationtranscripts.csv', '2025-01-01')
print(resultado)
```

## 📋 Formato dos Dados

O sistema espera um arquivo CSV com as seguintes colunas principais:

### Estrutura do CSV
- **content**: JSON contendo as atividades da conversa
- **conversationstarttime**: Timestamp do início da conversa (opcional)
- Outras colunas são preservadas e podem ser visualizadas conforme seleção

### Estrutura do JSON (campo 'content')
```json
{
  "activities": [
    {
      "id": "id_da_mensagem",
      "type": "message|trace|invoke",
      "text": "conteúdo da mensagem",
      "from": {
        "role": 0, // 0 = bot, 1 = usuário
        "aadObjectId": "id_do_usuario"
      },
      "timestamp": "2025-01-01T12:00:00.000Z",
      "replyToId": "id_da_mensagem_original"
    }
  ]
}
```

### Tipos de Atividades Suportadas
- **message**: Mensagens tradicionais de texto
- **trace** (GeneratedAnswer): Respostas geradas pelo sistema
- **invoke** (feedback): Ações de feedback dos usuários

## 🎨 Interface

### Layout Principal
- **Coluna Esquerda**: Lista de conversas com filtros e estatísticas
- **Coluna Direita**: Visualização detalhada da conversa selecionada

### Estilos Visuais
- **Mensagens do usuário**: Fundo branco com borda cinza
- **Mensagens do bot**: Fundo azul claro com borda azul
- **Feedbacks positivos**: Fundo verde claro
- **Feedbacks negativos**: Fundo vermelho claro

### Indicadores de Método
- **🔗 ID**: Feedback associado por ID direto
- **🔗 ID (outra linha)**: Feedback encontrado em linha diferente
- **⏱️ TEMPO**: Feedback associado por proximidade temporal

## ⚡ Performance

### Otimizações Implementadas
- **Cache em múltiplas camadas**: Todas as operações pesadas são cacheadas
- **Processamento em lote**: JSONs parseados uma única vez
- **Índices globais**: Mapeamento de IDs para busca rápida
- **Carregamento progressivo**: Interface responsiva durante processamento

### Capacidade
- Testado com datasets de milhares de conversas
- Processamento eficiente de JSONs complexos
- Memória otimizada para visualização em tempo real

## 🛠️ Arquitetura Técnica

### Componentes Principais
1. **Carregadores de Dados**: Funções cacheadas para CSV e JSON
2. **Processadores de Feedback**: Sistema de associação inteligente
3. **Renderizadores**: Componentes de visualização HTML/CSS
4. **Filtros e Estatísticas**: Processamento em tempo real

### Dependências
- **Streamlit**: Interface web interativa
- **Pandas**: Manipulação eficiente de dados
- **JSON**: Processamento de dados estruturados
- **DateTime**: Formatação de timestamps

## 📊 Casos de Uso

### Análise de Satisfação
- Monitoramento de feedbacks positivos vs negativos
- Identificação de padrões temporais de satisfação
- Análise de conversas problemáticas

### Auditoria de Conversas
- Revisão completa de interações usuário-bot
- Verificação de qualidade das respostas
- Identificação de falhas de comunicação

### Pesquisa e Desenvolvimento
- Análise de comportamento do usuário
- Avaliação de melhorias no sistema
- Dados para treinamento de modelos

## 🔧 Personalização

### Modificando Filtros
Edite as funções de filtro em [app.py](app.py) para adicionar novos critérios.

### Customizando Estilos
Modifique o CSS no bloco `st.markdown` para alterar a aparência das mensagens.

### Adicionando Métricas
Implemente novas funções de estatística seguindo o padrão das existentes com cache.

## 📝 Contribuição

### Estrutura do Código
- **app.py**: Aplicação principal Streamlit
- **count_users.py**: Utilitário para análise demográfica
- **.streamlit/config.toml**: Configurações do Streamlit

### Boas Práticas
- Mantenha funções com cache (`@st.cache_data`)
- Documente novas funcionalidades
- Teste com datasets de diferentes tamanhos
- Preserve compatibilidade com formato JSON existente

## 📄 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 🆘 Suporte

### Problemas Comuns
1. **Arquivo CSV não encontrado**: Verifique se `conversationtranscripts.csv` está no diretório correto
2. **Erro de JSON**: Valide o formato do campo 'content' no CSV
3. **Performance lenta**: Para datasets muito grandes, considere usar filtros de data

### Solução de Problemas
- Ative o modo debug alterando `debug = True` em [app.py](app.py)
- Verifique os logs do terminal para detalhes de erro
- Confirme a estrutura do CSV com os dados de exemplo

---

**Desenvolvido para análise eficiente de conversas e feedbacks em sistemas de chat** 🚀