# Histórico de operações

O Master consulta **Configurações → Histórico de operações** na empresa selecionada. A API revalida o proprietário vigente, usuário, vínculo e organização ativos; o contexto enviado pelo frontend não concede autoridade. Outros usuários recebem a mesma resposta de indisponibilidade, sem acesso aos eventos.

A consulta reúne os históricos existentes de despesas e contas a pagar com os novos eventos de Faturamento e Colaboradores:

| Área | Operações |
| --- | --- |
| Despesas | Cadastro, alteração e cancelamento |
| Contas a pagar | Cadastro, alteração, cancelamento, pagamento e estorno |
| Faturamento | Cadastro de cliente e faturamento, recebimento e estorno |
| Colaboradores | Cadastro, salvamento de edição e desligamento |

Cada item informa responsável, horário, área, ação, tipo e identificador do registro. O nome do responsável é o nome atual da conta; o identificador permanece estável. Uma despesa com título pode gerar registros nas duas áreas, pois representa duas alterações vinculadas.

A tela e a tabela `operation_events` não copiam corpos de requisição, nomes de colaboradores/clientes, documentos, valores de salários, dados bancários, senhas ou tokens. Os históricos antigos continuam nas tabelas de origem; sua consulta unificada projeta apenas os metadados autorizados, sem os snapshots internos.

Os novos eventos são gravados na mesma transação da operação. Repetir um cadastro com a mesma chave de idempotência, um desligamento já confirmado ou um estorno já realizado não duplica esses eventos. Cada salvamento aceito da edição de colaborador é registrado, mesmo quando os valores são equivalentes. O banco bloqueia UPDATE e DELETE na nova tabela. Isso não substitui controle de privilégios administrativos, backups ou armazenamento externo de auditoria.

`GET /api/v1/organizations/{organization_id}/companies/{company_id}/audit` aceita `start`, `end`, `domain`, `action`, `actor_id`, `cursor` e `limit`. O período padrão inclui os últimos 30 dias, com máximo de 93 dias por consulta e 100 itens por página. As datas dos filtros usam UTC; a tela apresenta o horário no fuso do navegador. A paginação é estável por horário, origem e identificador, com os filtros aplicados antes do limite. As respostas são `no-store`.

Não há reconstrução de autores ou datas para operações antigas que não tenham histórico. Faturamento e Colaboradores começam a gerar os novos eventos nesta atualização. A migration `b57329d81c04` cria a estrutura e os índices de consulta; seu downgrade é bloqueado quando existem novos eventos, para preservar os registros.
