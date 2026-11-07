# Contas a receber na visão financeira

O painel **Visão financeira → Contas a receber** exige `billing.read` na empresa selecionada. Não exige `payables.read`; consultar pagamentos continua sendo um acesso separado. Contrato, empresa, usuário e vínculo precisam estar ativos.

| Indicador | Critério |
| --- | --- |
| Recebidos no mês | Soma dos recebimentos não estornados, pela data informada, no mês selecionado |
| Saldo a receber | Valor das cobranças menos recebimentos válidos, incluindo baixas parciais |
| Vencem hoje | Saldo das cobranças com vencimento na data atual |
| Em atraso | Saldo das cobranças com vencimento anterior à data atual |
| Próximos sete dias | Saldo com vencimento de amanhã até o sétimo dia, inclusive |

O mês altera apenas os recebimentos. Os outros indicadores mostram a posição atual, usando a data de São Paulo. Cobranças quitadas não entram nas contagens de pendências. Faturamentos sem vencimento não constituem contas a receber. O botão **Ver contas a receber** abre a seção correspondente de Faturamento.

Um estorno exclui o recebimento da soma do mês de sua data original e reabre o saldo da cobrança. O indicador não reconstrói uma posição histórica de fechamento nem um fluxo de estornos por mês. Os valores representam registros informados no ERP; não comprovam movimentação bancária nem equivalem a faturamento por competência ou lucro.

`GET /api/v1/organizations/{organization_id}/companies/{company_id}/receivables-summary?month=YYYY-MM` calcula os indicadores em um único snapshot SQL autorizado. O mês padrão é o atual. A agregação considera todos os registros, sem depender do limite da lista de faturamento, e usa valores decimais exatos. Dados inconsistentes de recebimento geram conflito em vez de um saldo negativo silencioso. A resposta usa `no-store`.

A tela cancela a consulta anterior e limpa os indicadores ao trocar de empresa, mês ou permissão. Cadastros de faturamento, recebimentos e estornos atualizam a revisão financeira do frontend. Esta etapa não altera o banco e não exige migration.
