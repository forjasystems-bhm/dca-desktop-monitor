# 📊 Portfolio DCA Monitor

**Uma aplicação de desktop elegante e poderosa para acompanhar seu portfólio de criptomoedas, focada na estratégia DCA (Dollar-Cost Averaging), com cálculos precisos de preço médio, lucros e perdas.**

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Status](https://img.shields.io/badge/status-ativo-brightgreen.svg)

---

## Visão Geral

Este aplicativo foi criado para investidores de criptomoedas que desejam acompanhar posições e operações localmente. A arquitetura em desenvolvimento mantém o banco operacional **SQLite**, preserva o CSV anterior como origem auditável e oferece um primeiro acesso explícito para importar operações ou declarar saldos já existentes em custódia.

Ele busca preços em tempo real da Binance para fornecer uma análise precisa e atualizada do desempenho do seu portfólio.

## ✨ Funcionalidades Principais

*   **✍️ Registro de Transações:** Adicione operações de compra e venda de forma intuitiva.
*   **📊 Análise Detalhada:** Visualize seu preço médio (PMC), custo total da posição, valor de mercado atual, e lucros/perdas realizados e não realizados para cada ativo.
*   **💵 Conversão de Moeda:** Consulte patrimônio de mercado em USDT ou BRL quando houver câmbio atual; custos e lucros históricos **não** são convertidos retroativamente pelo câmbio do dia.
*   **📉 Taxa de corretagem:** Campo opcional em USDT, sempre documentado; o sistema não presume 0,1% nem inventa taxas antigas.
*   **🥧 Distribuição de Portfólio:** Entenda a alocação dos seus ativos com um resumo claro e uma representação visual em texto.
*   **📋 Histórico Completo:** Todas as suas transações são listadas e podem ser facilmente consultadas.
*   **✏️ Edição e Exclusão:** Corrija ou remova transações existentes diretamente pela interface.
*   **🔄 Preços em Tempo Real:** Conecta-se à API da Binance para buscar as cotações mais recentes das moedas e do par USDT/BRL.

## 🚀 Demonstração

Visão geral da interface, mostrando o DASHBOARD >>
![Demonstração do App](img/demo.png)

## 🛠️ Tecnologias Utilizadas

*   **Python 3**
*   **Tkinter** para a interface gráfica (GUI).
*   **ttkthemes** para modernizar o visual da aplicação.
*   **CCXT** para integração com a API da Binance e busca de preços.

## 📁 Estrutura do Projeto

```
dca-desktop-monitor/
├── main.pyw                        # Ponto de entrada da aplicação
├── requirements.txt
├── run_portfolio.sh                # Script de execução (Linux)
├── backend/
│   ├── backend.py                  # DataManager, PriceManager, AnalysisEngine
│   └── tipo_operacao.py            # Enum de tipos de operação
├── config/
│   ├── config.json                 # Moedas rastreadas, intervalo de atualização
│   ├── cards_lateral.py            # Componente de cards laterais
│   ├── carregar_json.py            # Loader do config.json
│   ├── conexao_badge.py            # Badge de status de conexão
│   ├── donut_chart.py              # Widget de gráfico donut (canvas)
│   ├── fontes.py                   # Fontes com DPI scaling (Windows/Linux)
│   ├── install.py                  # Criação de atalho no sistema
│   └── tema_cripto.py              # Constantes de cores e estilos ttk
├── db/
│   ├── conversao_usdt_brl.py       # Lógica de conversão de moeda
│   └── meu_diario_operacoes.csv    # Base de dados local (criado na 1ª execução)
├── gui/
│   ├── janela_caixa.py             # Aba: posição USDT e P/L em BRL
│   ├── janela_distribuicao.py      # Aba: dashboard com donut chart e tabela
│   ├── janela_edicao.py            # Aba: histórico com edição/exclusão
│   ├── janela_moedas.py            # Aba: gerenciar moedas rastreadas
│   ├── janela_registro_logica.py   # Lógica de registro de operações
│   ├── janela_registro_ui.py       # Layout de registro de operações
│   └── janela_splash.py            # Tela de splash de carregamento
├── img/
│   ├── demo.png
│   ├── favicon.ico
│   └── favicon.png
└── widgets/
    ├── brl_toggle.py               # Toggle USD/BRL
    └── combo_custom.py             # Combobox customizado
```

## ⚙️ Ambiente de desenvolvimento (NÃO é instalador homologado)

> **A versão integrada ainda não foi publicada para primeiro download.** Não instale um preview como versão operacional nem migre o único CSV real. Leia [Primeiro uso e migração](docs/PRIMEIRO_USO_E_MIGRACAO.md) antes de testar dados reais em cópias.

## ⚙️ Instalação e Execução

Siga os passos abaixo para executar o projeto em sua máquina local.

### Pré-requisitos

*   [Python 3.10](https://www.python.org/downloads/) ou superior.

### Passos

1.  **Clone o repositório:**
    ```bash
    git clone https://github.com/BRUNO1993-CIBER/dca-desktop-monitor.git
    cd dca-desktop-monitor
    ```

2.  **Crie e ative um ambiente virtual (recomendado):**
    *   **Windows:**
        ```bash
        python -m venv venv
        .\venv\Scripts\activate
        ```
    *   **macOS / Linux:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

3.  **Instale as dependências:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Execute a aplicação:**
    ```bash
    python main.pyw
    ```
    Na primeira execução, um arquivo chamado `meu_diario_operacoes.csv` será criado automaticamente para armazenar suas transações.

### 🖥️ Criar Atalho no Sistema (Opcional)

Após instalar as dependências, você pode criar um atalho clicável no seu sistema operacional para abrir o app sem precisar do terminal.

Com o ambiente virtual **ativado**, execute:

```bash
python config/install.py
```

**Windows** — cria um atalho `.lnk` na Área de Trabalho com o ícone do app:
- Clique duplo no atalho para abrir
- Para fixar na barra de tarefas: clique direito no atalho → **Fixar na barra de tarefas**

**Linux** — cria uma entrada `.desktop` no menu de aplicativos (`~/.local/share/applications/`):
- Procure por **Portfolio DCA Monitor** no menu de aplicativos
- Para fixar no dock: clique direito → **Adicionar aos favoritos** (GNOME/KDE)

> **Importante:** execute o script com o ambiente virtual ativado para que o atalho aponte para o Python correto com todas as dependências instaladas.

## 📜 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

*Feito com ❤️ por [Bruno Machado](https://github.com/BRUNO1993-CIBER)*
