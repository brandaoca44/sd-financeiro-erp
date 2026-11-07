# Fluxo de caixa consolidado

A página **Financeiro → Fluxo de caixa**, também acessível pela Visão financeira, exige `payables.read` e `billing.read` na mesma empresa. Usuário, vínculo, organização, empresa e contrato devem estar ativos. Não são liberados indicadores parciais quando falta uma das autorizações.

O período padrão é o mês atual. A consulta permite até 93 dias inclusivos, com uma linha por dia, inclusive dias sem movimento.

| Indicador | Cálculo |
| --- | --- |
| Entradas registradas | Recebimentos válidos pelas datas informadas |
| Saídas registradas | Pagamentos menos estornos, pelas datas informadas nos movimentos |
| Entradas pendentes | Saldo atual das cobranças por vencimento original |
| Saídas pendentes | Saldo atual dos títulos não cancelados por vencimento original |
| Variação realizada | Entradas registradas menos saídas registradas |
| Variação projetada | Variação realizada mais entradas pendentes menos saídas pendentes |

As pendências descontam todas as baixas válidas já registradas, mesmo fora do intervalo. Assim, pagamentos e recebimentos parciais não são contados novamente como previsão. Títulos quitados têm saldo pendente zero; cancelados não entram nas pendências. Despesas são representadas por seus títulos, evitando somar a despesa novamente. Faturamentos sem vencimento não entram como cobranças.

Os acumulados partem de zero no início do período: são variações, não saldos bancários. Atrasos mantêm o vencimento original e aparecem quando essa data pertence ao intervalo. A projeção não prevê negócios futuros que ainda não foram cadastrados.

Um estorno de pagamento reduz a saída na data do estorno; a saída líquida desse dia pode ser negativa. Recebimentos estornados são excluídos da data original neste relatório. A data efetiva de estorno passou a ser registrada para o cálculo por conta; registros antigos não recebem uma data inventada. O painel mostra uma posição gerencial dos registros atuais e não reconstrói um fechamento histórico ou extrato bancário.

`GET /api/v1/organizations/{organization_id}/companies/{company_id}/cashflow?start=YYYY-MM-DD&end=YYYY-MM-DD` calcula as duas áreas no mesmo snapshot SQL, com autorização antes da agregação e valores decimais exatos. Todos os registros são considerados, independentemente dos limites das listagens. Respostas usam `no-store`. Saldos inconsistentes geram conflito.

Trocar de empresa, período ou perder autorização limpa os dados e cancela a consulta anterior no frontend. A revisão financeira atualiza a consulta após movimentações. Não há alteração de estrutura de banco nesta etapa.
