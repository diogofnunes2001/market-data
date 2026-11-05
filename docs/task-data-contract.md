# Integração nas duas automações existentes

Estes blocos são adendas às instruções existentes. Não substituem o objetivo,
horário, seleção editorial, formato ou outras fontes já configuradas nas tarefas.
Este ficheiro documenta a configuração pretendida; um commit não altera por si
só as automações do ChatGPT.

## Task 1 — seleção e preparação

Preservar os 25 tickers atuais e o limite de 25 de `config/tickers.json`, incluindo
os 10 símbolos permanentes definidos em `scripts/watchlist.py`. Manter os outputs
e comportamento atuais. As fontes oficiais de taxas, Euribor e obrigações são
recolhidas pelo GitHub Actions; a Task 1 não deve voltar a recolher esses valores
nem substituí-los por estimativas. Encaminhar a Task 2 para os JSONs oficiais e
para as regras de frescura abaixo. As previsões de combustíveis são obtidas pela
Task 2 em notícias à sexta-feira, sem acrescentar scraping ao GitHub Actions.

## Task 2 — consumo e redação

Continuar a consumir os ficheiros de preços, sessão e dados técnicos existentes.
Para os novos indicadores, abrir nesta execução os três ficheiros publicados:

* [Taxas Fed e BCE](https://raw.githubusercontent.com/diogofnunes2001/market-data/main/data/interest_rates.json)
* [Euribor](https://raw.githubusercontent.com/diogofnunes2001/market-data/main/data/euribor.json)
* [Treasuries, obrigações europeias e spreads](https://raw.githubusercontent.com/diogofnunes2001/market-data/main/data/sovereign_bonds.json)

Verificar `schema_version=1`, `generated_at_utc`, `errors` e cada registo de
`records`. A recolha deve ter no máximo 36 horas, e cada indicador usado deve ter
`usable=true` e `status=fresh`. Verificar novamente a idade à hora do relatório:
as observações diárias devem ter no máximo três dias de semana de atraso. Não
confiar apenas num `fresh` calculado numa recolha antiga. Para as taxas BCE,
usar o campo `effective_date` como início de vigência; a verificação de frescura
baseia-se na consulta recente do histórico atual, não na idade dessa alteração.
Nunca apresentar a data de download como data da observação ou da decisão.

Apresentar os limites inferior/superior da Fed como intervalo oficial de objetivo,
separado da taxa efetiva. Para o BCE, identificar depósito, refinanciamento e
cedência marginal. A Euribor é um fixing observado ACT/360 com publicação
atrasada 24 horas, não uma previsão ou média mensal. Mostrar a data de referência.

As yields estão em percentagem anual e os spreads em pontos base. A curva 2s10s
é Treasury 10 anos menos Treasury 2 anos. O spread português é Portugal 10 anos
menos Alemanha 10 anos. Usar o cálculo publicado e a data dos seus inputs, sem
recalcular com yields de datas diferentes. A data do spread pode ser anterior à
das yields individuais. Distinguir explicitamente `observed` de `derived`.

Se um ficheiro não abrir, a recolha estiver antiga, o valor for nulo ou o registo
não for utilizável, indicar «indisponível» ou «último dado de [data], desatualizado»
e mencionar o motivo. Não inventar, interpolar, trocar a fonte silenciosamente,
usar zero como substituto ou apresentar um valor antigo como atual. Citar a fonte
original identificada no registo e a respetiva data.

Às sextas-feiras, no fuso Europe/Lisbon, consultar notícias recentes de fontes
fiáveis (por exemplo ECO, RTP ou ACP) sobre a variação prevista para a segunda-feira
seguinte em Portugal. Identificar separadamente gasolina simples 95 e gasóleo
simples, com variação em cêntimos por litro, data de publicação, segunda-feira a
que se aplica, fonte e link. São previsões de mercado, não preços observados nem
garantia do preço de cada posto. Se as fontes divergirem, mostrar a divergência;
se só derem direção ou intervalo, conservar essa precisão. Não inferir uma
variação numérica a partir do Brent ou de notícias antigas. Sem notícia recente
aplicável, declarar «previsão ainda não disponível» e não reutilizar a semana
anterior. Não executar esta secção como se fosse uma nova previsão nos outros dias.
