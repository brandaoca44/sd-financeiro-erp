# API de títulos de contas a pagar

Prefixo: `/api/v1/organizations/{org}/companies/{company}/payables`.
Todas as operações exigem Bearer válido e usuário, vínculo, tenant e empresa ativos.

| Método e sufixo | Permissão | Resposta |
| --- | --- | --- |
| POST no prefixo | `payables.manage` | 201 com ID, revisão e estado; header Location |
| GET no prefixo | `payables.read` | Página de títulos autorizados |
| GET `/{id}` | `payables.read` | Título do escopo exato |
| PUT `/{id}` | `payables.manage` | ID, revisão e estado atualizados |
| POST `/{id}/cancel` | `payables.manage` | ID, revisão e estado CANCELLED |

Não há DELETE, reabertura, baixa, estorno ou pagamento bancário. As permissões
`payables.settle`, `payables.reverse` e `companies.read` não autorizam estas rotas.
O Master também precisa passar pelos controles de atividade e escopo.

## Contratos

POST recebe `description`, `amount`, `issue_date` e `due_date`. PUT substitui esses
campos e exige `expected_revision` inteiro positivo. Cancelamento recebe somente
`expected_revision`. Booleano não é revisão válida; campos adicionais são recusados.
Tenant, empresa, ator, moeda e estado não são escolhidos pelo corpo.

Valor é string decimal positiva com até duas casas, limite `9999999999999999.99`.
Datas usam `AAAA-MM-DD`; vencimento não antecede emissão. Descrição tem até 300
caracteres. Respostas de leitura usam duas casas, como `"0.10"`, sem float.

Escritas retornam somente `id`, `revision` e `status`. Gestão não implica leitura,
mesmo para o título criado pelo próprio ator. GET retorna descrição, valor, moeda,
datas, estado, revisão, timestamps e escopo; não inclui criador ou histórico.

Listagem aceita `limit` de 1 a 100, `cursor` UUID, `due_from`, `due_to` e `status`
OPEN/CANCELLED. Datas de vencimento são inclusivas. Intervalo invertido retorna
422. Ordenação/cursor são por UUID; `next_cursor` indica a próxima página ou null.
Tenant, empresa e permissão são filtrados no SQL antes do limite.

## Transações

O ator é reobtido do token dentro da transação, com nova conferência de permissão
e sessão, inclusive se houve revogação entre a resolução HTTP e a escrita.
Locks seguem organização, identidade/vínculo, empresa, sessão e título. O lock
da organização serializa com a administração de acessos; é conservador e poderá
limitar vazão. Otimizações futuras precisam preservar a segurança e a ordem dos locks.

Revisão divergente, edição de cancelado e cancelamento repetido retornam 409.
Cancelamento preserva dados e histórico. Com movimentos existentes, não permite
cancelar com líquido pago nem reduzir valor abaixo dele; emissão não pode passar
a ser posterior a um movimento. Isso não disponibiliza um serviço de baixa.

Título, histórico e renovação da inatividade são confirmados juntos. Falha de
histórico/banco desfaz a operação. Não há limite absoluto novo para a sessão nem
senha exigida em cada lançamento; reautenticação permanece na gestão de acessos.
Snapshots não duplicam descrição; valores financeiros não entram nos logs.

Criação ainda não tem idempotência: repetir um POST bem-sucedido gera outro título.
Após timeout com resultado desconhecido, não repetir cegamente; conferir registros
com usuário autorizado. Idempotência das futuras baixas/estornos é requisito próprio.

## Limites e segurança

Escritas usam contadores `payables_manage` separados dos administrativos, com
janelas de 60 segundos: 60 por ator, 180 por origem e 1200 no geral, por namespace.
Não consomem vagas de hash Argon2. Redis indisponível bloqueia escrita com 503;
integridade financeira permanece no PostgreSQL.

Sem sessão: 401. Escopo/recurso/permissão incompatível: 404 genérico. Entrada
inválida: 422. Conflito: 409. Rate limit: 429 com Retry-After. Infraestrutura: 503;
erro inesperado: 500 mínimo. Permanecem HTTPS em staging/produção, JSON limitado
a 4096 bytes nas escritas, `no-store`, `X-Request-ID` e logs por campos permitidos.

Não requer migration nova nem cria títulos ou concessões reais. Testes HTTP usam
bancos temporários e cobrem fluxo, isolamento, permissões, precisão, paginação,
revogação, concorrência, rollback, Redis, HTTPS e limites. Próximo incremento:
baixa e estorno com integridade de saldo e idempotência.

Validação completa: **452 testes aprovados**, 15 novos de HTTP financeiro. Na API
local, health 200 e GET/POST sem sessão 401 com `no-store`. Sucesso autenticado
foi validado em infraestrutura isolada. Tabelas financeiras reais e bancos
temporários foram conferidos vazios ao final.
