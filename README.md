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
*   **CustomTkinter/Tkinter** para a interface desktop.
*   **SQLite** para histórico financeiro, auditoria, dados locais e backups.
*   **pystray/Pillow** para bandeja opcional do Windows.
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
    git clone https://github.com/tiolusystems/dca-desktop-monitor.git
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
    Na primeira execução, o aplicativo cria um SQLite local e oferece escolher o CSV antigo, declarar saldos existentes ou iniciar vazio. Não cria operações fictícias nem regrava o CSV original.

### 🖥️ Recursos Windows — ainda sem distribuição

O painel **Aplicativo / Configurações** prepara os seguintes recursos: verificar versões estáveis pelo canal oficial, criar atalho da versão **instalada** (não preview), optar por manter o monitor na bandeja do Windows e verificar/preparar uma restauração SQLite.

**O instalador e o atualizador de executáveis não estão publicados nem habilitados.** O botão **Atualizar agora** permanece desabilitado até que um pacote autêntico, assinado ou validado por uma cadeia de confiança aprovada, esteja disponível e a homologação tenha ocorrido.

Scripts de desenvolvimento (`config/install.py`) não substituem a instalação Windows gerenciada. Não se deve distribuir um atalho que aponte para um checkout temporário ou pasta de testes.

## 📚 Gates de pré-homologação

- [Migração e primeiro uso](docs/PRIMEIRO_USO_E_MIGRACAO.md)
- [Conciliação, custódia e recuperação](docs/PRE01_CONCILIACAO_RECUPERACAO.md)
- [Controles desktop](docs/DESK01_CONTROLES_WINDOWS.md)
- [Contrato financeiro e prioridades](docs/DCA-00_CONTRATO_E_PRIORIDADES.md) — documento de referência na PR #3
- [Teste pré-CSV em andamento](docs/QA02_PRE_HOMOLOGACAO.md)

**Não importar o único CSV real nem disponibilizar executável antes de concluir a homologação em uma cópia.**

## 📜 Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.

---

*Feito com ❤️ por [Bruno Machado](https://github.com/BRUNO1993-CIBER)*
