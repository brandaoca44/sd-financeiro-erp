# Movimentos e saldo por conta financeira

Pagamentos e recebimentos agora permitem selecionar uma conta financeira da mesma empresa. O vínculo é opcional para preservar os fluxos existentes; operações sem conta continuam identificadas como **Sem vínculo com conta** e não afetam saldos de contas específicas.

Para registrar uma nova operação vinculada, são exigidas a permissão da operação (`payables.settle` ou `billing.receive`) e `accounts.read`. A conta deve estar ativa, em BRL, e sua data inicial não pode ser posterior à data financeira do movimento. Não é necessário acesso aos números bancários.

O estorno sempre utiliza a conta original. Ele é permitido mesmo se essa conta estiver inativa, desde que o ator mantenha a permissão de estorno da área e a consulta de contas. A conta do estorno não pode ser escolhida livremente.

Em **Contas financeiras → Detalhes**, o saldo calculado exige `accounts.read`, `payables.read` e `billing.read` na mesma empresa:

`saldo inicial + recebimentos − estornos de recebimentos − pagamentos + estornos de pagamentos`

A consulta considera movimentos desde a abertura da data inicial até a data atual de São Paulo. Valores são decimais exatos, em um snapshot SQL autorizado. O resultado é um saldo calculado a partir do ERP, ainda não conciliado com um extrato bancário. O painel informa quantos pagamentos e recebimentos da empresa permanecem sem vínculo.

## Registros antigos

Nos históricos de pagamentos e recebimentos, **Vincular conta** permite atribuição explícita. São necessários `accounts.manage`, `accounts.read` e a permissão de registrar a operação da área. Não há atribuição automática ou possibilidade de transferir um movimento já vinculado para outra conta.

Vincular um pagamento antigo também vincula seus estornos existentes à mesma conta, na mesma transação. A revisão do título é conferida e incrementada. Movimentos anteriores à data inicial são rejeitados para não contar novamente posições já incorporadas ao saldo inicial.

Para recebimentos antigos já estornados, a situação esperada precisa coincidir com o registro atual. Se não existir data de estorno, é necessário informar a data financeira efetiva e possuir também `billing.reverse`. A data não é inventada a partir da data da migração. Datas existentes são preservadas.

As atribuições geram auditoria transacional. O banco também bloqueia reatribuições de conta quando o vínculo já foi definido. Dados bancários continuam criptografados e não entram nos registros de movimentos.

## API

- `POST .../payables/{id}/payments`: campo opcional `financial_account_id`.
- `POST .../billing/{id}/receipts`: campo opcional `financial_account_id`.
- `POST .../billing/{id}/receipts/{id}/reverse`: aceita `reversed_on`; sem data usa o dia atual, após validar o recebimento original.
- `POST .../payables/{id}/payments/{id}/account`: conta e `expected_revision`.
- `POST .../billing/{id}/receipts/{id}/account`: conta, `expected_reversed` e data de estorno quando necessária.
- `GET .../financial-accounts/{id}/position`: posição calculada, composição e contagem de movimentos sem conta.

A migration `d7b02f413a86` mantém registros existentes com conta nula e preserva vínculos e datas novas contra downgrade destrutivo. Os indicadores anteriores de recebimentos continuam líquidos dos estornos na data original; o cálculo por conta utiliza as datas financeiras efetivas registradas. Não há importação de extratos, transferências entre contas ou conciliação bancária nesta etapa.

A confirmação de cadastro de recebimento retorna somente seu identificador. Valores e detalhes de consulta continuam restritos às rotas de leitura, mesmo durante uma repetição idempotente.


O [extrato por conta](extrato-por-conta.md) permite conferir lançamentos e saldos de abertura e fechamento por período, com paginação e as mesmas permissões da posição calculada.
