# market-data

Recolha automática de mercados e indicadores financeiros. Os 25 tickers de
`config/tickers.json` e os ficheiros `prices.json`, `session.json` e
`technical.json` mantêm o funcionamento existente.

## Taxas e obrigações oficiais

O workflow **Update official rates and bonds** corre em dias úteis às 07:15 e
22:15 UTC, em cada alteração aos seus scripts/testes e por execução manual.
A recolha da manhã fornece os dados publicados na véspera; a recolha da noite
inclui normalmente o fecho americano. Não são cotações intradiárias.

| JSON em `data/` | Indicadores | Fonte estruturada |
| --- | --- | --- |
| `interest_rates.json` | Limites inferior/superior Fed e taxa efetiva; depósito, refinanciamento principal e cedência marginal BCE | [Fed Nova Iorque JSON](https://markets.newyorkfed.org/static/docs/markets-api.html), [BCE SDMX CSV](https://data.ecb.europa.eu/data/publications/KIR01_01) |
| `euribor.json` | Euribor 1, 3, 6 e 12 meses, ACT/360 | [Banco da Finlândia XML / EMMI](https://www.suomenpankki.fi/en/statistics/interest-rates-and-exchange-rates/euribor-rates/), atraso de 24 horas |
| `sovereign_bonds.json` | Treasury 2/10 anos, curva 2s10s, Alemanha 2/10 anos, Portugal 10 anos e spread face à Alemanha | [Treasury XML](https://home.treasury.gov/treasury-daily-interest-rate-xml-feed), [Bundesbank CSV](https://www.bundesbank.de/en/statistics/money-and-capital-markets/interest-rates-and-yields/daily-yields-of-current-federal-securities-772220), [BPstat JSON](https://bpstat.bportugal.pt/serie/12099459) |

Cada ficheiro identifica a recolha UTC, a data efetiva da observação, unidades,
origem e série, estado de frescura, erros e se cada registo pode ser utilizado.
São publicados também snapshots de cada recolha em `data/history/YYYY-MM-DD/`.

* `kind=observed`: valor publicado por uma fonte; `kind=derived`: cálculo entre
  observações. Não há previsões nestes três JSONs.
* Taxas e yields estão em percentagem anual. Spreads estão em pontos base:
  `100 × (yield longa − yield curta)` e `100 × (Portugal 10y − Alemanha 10y)`.
* O spread Portugal–Alemanha usa a data comum mais recente dos últimos 35 dias,
  sujeita à mesma validação de frescura, com valores e datas dos dois inputs
  guardados. As yields individuais podem ter datas mais recentes que o spread.
* Observações diárias têm tolerância máxima de três dias de semana, sem contar
  sábados e domingos. É uma tolerância explícita para atrasos/feriados; não é um
  calendário de feriados de cada mercado. Dados mais antigos ficam `stale` e
  `usable=false`, mesmo que tenham sido descarregados hoje.
* As séries BCE são eventos de alteração: `effective_date` pode ser antiga sem
  a taxa ter caducado. A frescura exige uma consulta bem-sucedida ao histórico
  oficial atual; taxas anunciadas com entrada em vigor futura são excluídas.
  O consumidor deve ainda verificar que a recolha tem menos de 36 horas.
* Falha de fonte: `value=null`, `status=unavailable`, `usable=false`, com erro.
  Não há preenchimento com zero nem reutilização silenciosa de dados antigos.
* O workflow publica os erros e só depois assinala falha de saúde se algum
  indicador estiver indisponível/antigo. Assim, um consumidor vê o problema atual.
  A recolha dos 25 tickers tem um workflow independente e não depende destas APIs.
* HTTPS é validado, com timeout e três tentativas. Não há scraping de páginas.

A Euribor é propriedade da EMMI. A página do Banco da Finlândia permite consulta
com 24 horas de atraso e apresenta condições de utilização; a redistribuição
comercial exige acordo com a EMMI. Este projeto destina-se a consulta pessoal,
não concede direitos comerciais sobre dados de terceiros.

## Consumir os dados nas automações

Instruções adicionais para as duas tarefas existentes, preservando os respetivos
horários e restantes instruções: [contrato e instruções](docs/task-data-contract.md).
Os combustíveis são consultados **nas notícias pela Task 2 às sextas-feiras**,
por decisão do utilizador; não são recolhidos neste workflow.

## Validação local

```sh
pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/fetch_macro.py
python scripts/validate_macro.py --health
```

`MARKET_DATA_DIR` permite escolher outra pasta de saída para testes. Os testes
unitários não necessitam de rede e cobrem ausência de dados, respostas inválidas,
unidades, frescura, taxas BCE futuras, falhas parciais e alinhamento dos spreads.
Automated financial market data collection using Python and yfinance
