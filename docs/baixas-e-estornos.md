# Baixas manuais e estornos de contas a pagar

## Contratos

Prefixo: `/api/v1/organizations/{org}/companies/{company}/payables/{title}`.

| Método e sufixo | Permissão | Resultado |
| --- | --- | --- |
| POST `/payments` | `payables.settle` | Registra baixa parcial ou total |
| POST `/payments/{payment}/reverse` | `payables.reverse` | Estorna integralmente uma baixa |
| GET `/position` | `payables.read` | Posição derivada do título |
| GET `/movements` | `payables.read` | Movimentos paginados, incluindo estornos |

São registros manuais de pagamentos informados pelo usuário. Nenhuma operação
envia dinheiro, cancela transação bancária ou chama uma integração externa.
Consulta, gestão, baixa e estorno continuam permissões independentes. O Master
também precisa ter sessão, vínculo, tenant e empresa ativos.

## Entrada e resposta

Baixa recebe `amount` como string decimal, `occurred_on` em `AAAA-MM-DD` e
`expected_revision` inteiro positivo. Estorno recebe data, revisão e `reason`
não vazio, de até 300 caracteres; o valor vem da baixa original, sem campo de
valor ou referência substituível no corpo. Campos extras são recusados.

Nas duas escritas, o header **Idempotency-Key** é obrigatório e deve ser UUID.
Gerar uma chave por intenção de operação e guardá-la para eventual repetição.
A resposta 201 contém somente `payable_id`, `movement_id`, `revision` e `kind`.
Não retorna valor, saldo ou motivo para quem possui apenas baixa/estorno.

Uma baixa não pode exceder o saldo aberto. Sua data deve estar entre emissão e
o dia operacional atual. Estorno não pode anteceder a baixa nem estar no futuro.
O calendário operacional desta versão usa `America/Sao_Paulo`, independente do
fuso do computador e sem aceitar fuso escolhido pelo cliente. Configuração por
empresa fica para evolução posterior. O runtime precisa disponibilizar essa zona
IANA; no Windows ela já é fornecida pelas dependências instaladas do projeto.

Título cancelado não recebe movimentos novos. Cada baixa admite somente um
estorno integral. Não é possível estornar outro estorno, origem de outro título
ou empresa, ou baixa já estornada com uma nova chave. Para correção parcial,
estornar a baixa e cadastrar o valor correto com revisão e chave novas.

## Idempotência

A chave é isolada por tenant, empresa, ator e operação. Sessões diferentes do
mesmo usuário compartilham esse escopo; usuários diferentes e baixa/estorno têm
espaços de chave independentes. Não reutilizar uma chave para outro título.

O hash considera o payload normalizado, incluindo título, revisão esperada, data
e valor ou origem/motivo. `40` e `40.00` são o mesmo valor normalizado. Repetição
com mesma chave e conteúdo retorna 201 com o comprovante original, sem novo
movimento, histórico ou incremento de revisão. Conteúdo diferente retorna 409.

No retry após timeout, reenviar **a mesma chave e o mesmo conteúdo**, inclusive
a revisão original. Não atualizar a revisão desse retry. Uma nova intenção usa
nova chave e a revisão atual.

A sessão e a permissão atual são validadas antes do replay. Revogação, inatividade
ou expiração não podem ser contornadas conhecendo uma chave. Um replay autorizado
retorna o comprovante histórico, mesmo se o título já teve outros movimentos ou
foi cancelado depois; não é uma consulta da revisão atual.

Os resultados ficam no PostgreSQL e não expiram automaticamente. Não apagar
registros idempotentes para liberar chaves: isso pode permitir repetição de efeitos.

## Saldo, concorrência e auditoria

Baixa, estorno, revisão do título, auditoria, resultado idempotente e renovação
da sessão são confirmados juntos. Falha desfaz tudo e permite repetir a intenção
original. Não há reserva de chave confirmada sem movimento correspondente.

São usados os locks da escrita financeira e do título. Eles serializam a operação
com edição, cancelamento, outras baixas, estornos e gestão de acessos. Revisão
desatualizada e saldo insuficiente retornam 409; concorrência não pode ultrapassar
o valor do título nem estornar a mesma origem duas vezes. A unicidade da origem
do estorno também é protegida no banco.

Movimentos não são editados ou apagados pela API. Correção ocorre por novo estorno.
O motivo é dado sensível, persistido no movimento e consultável apenas com leitura
financeira. Auditoria registra referências, revisão e líquido pago, sem copiar o
motivo. Nada disso entra nos logs operacionais. SQL privilegiado ainda exige os
controles operacionais de acesso ao banco; esta entrega não implementa RLS.

## Consultas

`position` retorna revisão, BRL, valor original, líquido pago, valor em aberto e
estado derivado OPEN/PARTIALLY_PAID/PAID/CANCELLED. Cancelado não compõe valor em
aberto, mantendo o original para histórico. A leitura bloqueia brevemente o título
para não combinar revisão e movimentos incompatíveis; timeout de lock é cinco
segundos. Não é uma posição consolidada por empresa ou uma previsão de caixa.

`movements` usa cursor UUID, limite de 1 a 100 e filtro de autorização no SQL.
Retorna valor, data, tipo, origem, motivo e timestamp, sem ator ou chave idempotente.
Somente `payables.read` permite essas consultas, inclusive para quem criou a baixa.

Permanecem rate limit financeiro, HTTPS em staging/produção, JSON de até 4096
bytes, `no-store`, `X-Request-ID`, 401 sem sessão, 404 genérico sem acesso/recurso,
409 para conflitos, 422 para entrada/header inválido e 503 em indisponibilidade.
Replays também passam pelo rate limit; Redis indisponível bloqueia a escrita.

## Migration e validação

`b29e6431da08` sucede `a18d5320cf97`. Adiciona motivo opcional a movimentos legados
e a tabela `payable_movement_requests`, com FKs completas de escopo. Não cria
títulos, movimentos ou concessões. Novos estornos da API exigem motivo; linhas
legadas podem continuar com null. Downgrade bloqueia se houver qualquer movimento
ou resultado idempotente, protegendo histórico e o reconhecimento de retries.

Os testes usam bancos temporários e cobrem precisão, replay, mudança de payload,
escopo de chave, permissão independente, revogação, concorrência, rollback,
referências forjadas, datas, consulta e migrations. Próximo incremento: posição
a pagar consolidada por empresa e período, agora disponível no
[contrato de resumo](resumo-contas-a-pagar.md), com totais sem dupla contagem.

Validação completa: **477 testes aprovados**, com 25 novos. Migration local aplicada
na porta 5433, contagens anteriores preservadas e schema alinhado. Nenhum movimento
ou resultado idempotente real criado; sem bancos temporários restantes. API local:
health 200, escrita de baixa e consultas sem sessão 401, com `no-store`. Sucesso
autenticado foi validado apenas em infraestrutura isolada.
