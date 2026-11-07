# Contas financeiras da empresa

Em **Financeiro → Contas financeiras**, cadastre caixas, contas bancárias e contas de pagamento da empresa selecionada. A moeda desta etapa é BRL. O saldo inicial representa a abertura da data de referência, aceita zero ou valor negativo e exige uma data não futura.

| Permissão por empresa | Acesso |
| --- | --- |
| `accounts.read` | Nome, tipo, situação, data e saldo inicial |
| `accounts.manage` | Cadastro, edição e inativação |
| `accounts.bank` | Dados bancários, combinada com consulta ou gerenciamento |

As concessões são administradas pelo Master em **Permissões da empresa**. Não são derivadas de cargo, acesso à folha ou acesso a Contas a pagar/Faturamento. Contrato, empresa, usuário e vínculo devem estar ativos. O recurso utiliza a licença de fluxo de caixa do segmento Empresarial. Usuários existentes não recebem novas concessões automaticamente.

A lista não contém instituição, agência ou número da conta. A consulta bancária ocorre apenas ao solicitá-la nos detalhes e exige `accounts.read` e `accounts.bank`. Cadastrar ou alterar os dados bancários exige `accounts.manage` e `accounts.bank`. Quem gerencia sem consultar pode cadastrar, mas recebe somente identificador e revisão.

Os dados bancários são criptografados com a chave de identidade configurada no ambiente e vinculados à organização, empresa e identificador da conta. Sem a chave correta, o acesso bancário falha de forma fechada. Não são armazenadas credenciais de internet banking. Agência e conta aceitam apenas números, sem pontuação.

Nome e situação podem ser editados. Dados bancários podem ser substituídos por quem possui as permissões correspondentes. Omissão desses campos preserva os valores existentes. Saldo inicial, data de referência, tipo e moeda ficam preservados após o cadastro, inclusive por proteção no banco. A correção de uma posição inicial deve futuramente usar lançamentos de ajuste auditados. Não existe exclusão de contas; use inativação.

Cadastros usam chave de idempotência. Edições exigem a revisão esperada e são rejeitadas quando outro usuário já alterou a conta. Cada cadastro e edição gera evento de auditoria transacional com metadados, sem valores bancários ou saldo no evento.

Rotas sob `/api/v1/organizations/{organization_id}/companies/{company_id}/financial-accounts`:

- `GET`: consulta paginada por identificador, com filtro opcional `status` e limite de até 100 itens.
- `POST`: cadastro com `Idempotency-Key`.
- `PUT /{account_id}`: alteração com `expected_revision`.
- `GET /{account_id}/bank-details`: consulta protegida dos dados bancários.

As respostas são `no-store`. As contas ficam isoladas por organização e empresa. A migration `c9e2047d81af` cria a estrutura e amplia os catálogos fechados; o downgrade é bloqueado se existirem contas, concessões ou eventos novos.

A lista apresenta posições iniciais. Nos detalhes, o saldo calculado exige também consulta de Contas a pagar e Faturamento e considera apenas movimentos explicitamente vinculados à conta. Nenhuma movimentação antiga é atribuída automaticamente. Consulte [Movimentos e saldo por conta](movimentos-por-conta.md) para atribuição, datas e tratamento de estornos.
