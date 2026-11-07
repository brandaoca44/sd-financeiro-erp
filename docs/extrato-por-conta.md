# Extrato por conta financeira

Abra **Financeiro → Contas financeiras → Detalhes → Extrato da conta**. A consulta exige `accounts.read`, `payables.read` e `billing.read` na empresa selecionada. Contas inativas continuam disponíveis para consulta; não é necessário acesso aos dados bancários protegidos.

O extrato permite períodos de até 93 dias inclusivos, desde a data inicial da conta até a data atual de São Paulo. O período padrão vai do início do mês à data atual, respeitando a data inicial da conta.

| Informação | Critério |
| --- | --- |
| Saldo de abertura | Posição inicial mais movimentos vinculados anteriores ao primeiro dia do filtro |
| Entradas | Recebimentos e estornos de pagamentos ocorridos no período |
| Saídas | Pagamentos e estornos de recebimentos ocorridos no período |
| Saldo após lançamento | Saldo inicial mais todos os movimentos até aquela linha |
| Saldo de fechamento | Saldo de abertura mais entradas menos saídas do período |

Estornos usam sua data financeira registrada. Um recebimento estornado gera duas linhas: entrada original e saída na data efetiva do estorno. Movimentos sem conta e lançamentos de outras contas não são incluídos. Os saldos consideram todas as páginas, mesmo quando apenas parte das linhas está carregada.

A ordenação é por data, origem, identificador e referência. Dentro do mesmo dia, essa ordem técnica é determinística e não representa um horário intradiário que o ERP não registrou. Os lançamentos mostram operação, descrição, referência, entrada/saída e saldo acumulado. Pagamentos permitem abrir o título de origem. Números bancários, chaves Pix e conteúdo criptografado não integram a resposta.

`GET /api/v1/organizations/{organization_id}/companies/{company_id}/financial-accounts/{account_id}/statement` aceita `start`, `end`, `cursor` e `limit` (até 100 itens). Saldos, totais, autorização e linhas são calculados em um único snapshot SQL por requisição. A paginação usa data, origem, identificador e referência; o cursor não substitui a autorização. Respostas são `no-store`.

O resultado reflete os registros atuais do ERP. Atribuições e lançamentos retroativos feitos entre consultas podem modificar a posição: use **Consultar extrato** para recarregar o período após alterações. O extrato ainda não comprova conciliação com o banco e não equivale a um fechamento contábil imutável. Esta etapa não exige migration.
