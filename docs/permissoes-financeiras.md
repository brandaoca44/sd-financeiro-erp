# Permissões financeiras por empresa

## Escopo

Esta entrega implementa a política e a administração de permissões financeiras.
As [rotas de títulos](api-contas-a-pagar.md) já consomem essa política.
[Baixas e estornos](baixas-e-estornos.md) também estão disponíveis. Posição
consolidada continua pendente.

| Chave | Autoridade independente |
| --- | --- |
| `payables.read` | Consultar títulos e movimentos autorizados |
| `payables.manage` | Criar, editar e cancelar títulos |
| `payables.settle` | Registrar baixa manual |
| `payables.reverse` | Estornar baixa |

As chaves estão no catálogo autenticado `GET /api/v1/auth/permissions`, com escopo
`COMPANY`. A permissão de uma operação não implica as outras. Por exemplo, baixa
não concede consulta, edição ou estorno; os futuros contratos retornarão apenas
os campos necessários à operação autorizada.

`companies.read`, leitura da organização, cargos e provisionamento da plataforma
não dão acesso financeiro. As novas chaves não podem ser colocadas em perfis ou
tetos de delegação organizacionais, pois isso perderia o escopo da empresa.

## Política de acesso

`CompanyAccessPolicy.has_financial_permission` exige o usuário e o tenant ativos,
vínculo ativo e empresa ativa no tenant exato. A autoridade vem do Master vigente
ou de uma concessão direta ativa para a chave e empresa informadas.

O Master tem autoridade financeira nas empresas ativas de sua organização, mas
também precisa passar pelas verificações de atividade e escopo. A política de
organização recusa todas as chaves financeiras: não há autorização financeira sem
empresa. A leitura administrativa de cadastro de empresa inativa pelo Master
continua possível, sem liberar operações financeiras nessa empresa.

Para consultas futuras, `financial_visibility` produz filtro SQL por empresa,
tenant e chave, antes da paginação. Chaves desconhecidas resultam em negação.
Essa expressão se aplica a Company; consultas de títulos deverão vinculá-la ao
escopo correto, sem filtrar dados depois de enviá-los ao frontend.

## Administração pelo Master

Prefixo de rota:
`/api/v1/organizations/{org}/companies/{company}/members/{user}/permissions/{permission_key}`

| Método | Contrato |
| --- | --- |
| GET | Configuração mínima ou `null` se ainda não houver concessão |
| PUT | Define `ACTIVE` ou `INACTIVE` para exatamente uma das quatro chaves |

PUT recebe `status`, `expected_revision`, `expected_company_revision`,
`expected_membership_revision` e a senha do Master. Revisão da concessão é zero
somente quando ela não existe; revisões dos pais são positivas. A chave vem da
rota fechada, nunca de campo no corpo. Escopo, ator, wildcard e acesso a todas
as empresas não são aceitos no corpo.

Somente o Master pode consultar ou alterar essa configuração. O alvo precisa ter
vínculo no tenant. Ativação exige alvo, vínculo e empresa ativos; a revogação pode
ser feita mesmo com alvo/empresa inativos. O Master não concede nem revoga sua
própria autoridade por essa rota.

A resposta contém apenas empresa, usuário, chave, status, revisão da concessão,
revisões dos pais e `effective`. Este último mede a concessão direta; não uma
atribuição de cargo nem uma sessão carregada com permissões.

Reautenticação, rate limit compartilhado de administração, limite de corpo,
HTTPS em staging/produção, `no-store` e erros mínimos são os mesmos das concessões
de leitura existentes. Revisão desatualizada retorna 409. Recurso/autoridade
incompatível retorna 404 genérico; chave inválida retorna 422. Sem sessão, 401.

## Revogação e auditoria

Inativação e reativação de vínculo ou empresa limpam também as concessões
financeiras, incrementando suas revisões. Reativar não restaura direitos antigos.
Revogação de uma chave não revoga outra chave nem outra empresa. Colaboradores
não recebem acesso a empresas futuras por possuir uma concessão existente.

Transferência do Master preserva concessões diretas anteriores, mas troca quem
pode administrá-las. O antigo Master perde a autoridade de proprietário; uma
eventual concessão direta anterior é avaliada separadamente.

A gravação e o histórico `COMPANY_PERMISSION_SET` pertencem à mesma transação,
sob os locks de administração existentes. Histórico guarda somente status e
revisões; não copia senha, token, e-mail ou valores financeiros. Falha de histórico
desfaz a concessão. A próxima consulta de política lê o estado persistido, sem
cache de permissões dentro do token.

## Migration e validação

`a18d5320cf97` sucede `f07c4219be86`. Amplia dois CHECKs nas tabelas existentes,
sem criar registros, alterar concessões ou ativar direitos. A rota antiga
`read-access` mantém seu contrato e continua limitada a `companies.read`.
Downgrade bloqueia se houver qualquer concessão ou histórico financeiro,
inclusive concessão inativa. Não apagar histórico para forçá-lo.

Os testes cobrem chaves independentes, isolamento, Master, transferência,
inatividade, revisões, concorrência, falha de Redis/auditoria, rate limit, corpo
limitado, HTTPS e migration sem backfill. Usam apenas infraestrutura temporária.

Suíte completa: **437 testes aprovados**, 24 novos nesta entrega. Migration local
aplicada na porta 5433, schema alinhado, contagens e concessões anteriores
preservadas, zero concessões financeiras reais e zero bancos temporários restantes.
API local com health 200, contrato GET/PUT no OpenAPI e recusa 401 sem sessão,
com `no-store`. Sucesso autenticado foi validado apenas em infraestrutura isolada.

Serviços e rotas de lançamento, edição, cancelamento e consulta de títulos já
consomem esta política. Baixas e estornos agora também validam suas chaves
independentes, com integridade de saldo, idempotência e concorrência.
