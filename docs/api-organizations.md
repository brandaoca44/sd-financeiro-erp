# API de organizações

## Estado atual

As rotas estão implementadas com autenticação por sessão e autorização no servidor.
Dependem das migrations aplicadas e da configuração de autenticação descrita em
[Autenticação e segurança](autenticacao.md). O frontend ainda não está implementado.

## Organização e acesso

`Organization` representa o tenant. `Company` representa uma entidade jurídica
vinculada a ele. Conhecer o UUID de uma organização não permite acessá-la.

O ERP atende exclusivamente empresas. O identificador jurídico de `Company` é
CNPJ, sem alternativa por CPF. O usuário é a pessoa autorizada a operar o ERP;
isso não representa atendimento a cliente pessoa física. Organization agrupa as
empresas do cliente e não duplica seus identificadores jurídicos.

| Operação | Condições |
| --- | --- |
| Criar organização | Sessão válida, usuário ativo e `can_provision_organizations=true` |
| Consultar organização | Sessão válida, usuário ativo, vínculo ativo e `can_read_organization=true` no tenant solicitado |

Provisionamento e leitura são permissões independentes. O primeiro operador pode
criar tenants, mas não recebe acesso global ou vínculos automáticos com eles.
As permissões são consultadas no banco a cada operação; não são aceitas em headers,
corpo da requisição ou claims enviados pelo cliente.

## POST /api/v1/organizations

Requer `Authorization: Bearer <token>`. Corpo JSON:

```json
{"name": "Empresa Exemplo"}
```

Aceita somente `name`, entre 1 e 150 caracteres após remover espaços nas extremidades.
UUID, status inicial `ACTIVE` e timestamps são controlados pelo sistema. Não existe
unicidade de nome ou cadastro público de tenants.

Sucesso: HTTP 201, header `Location` com o caminho da organização e resposta contendo
somente `id`, `name`, `status`, `created_at` e `updated_at`.

O service confirma a criação antes da resposta. A operação não cria empresas,
usuários, vínculos ou sessões. Ainda não há chave de idempotência; não repetir
automaticamente uma criação cujo resultado ficou incerto.

## GET /api/v1/organizations/{organization_id}

Requer `Authorization: Bearer <token>` e UUID válido. Retorna HTTP 200 com os mesmos
cinco campos de OrganizationResponse, sem relacionamentos ou dados de usuários.

Organização inexistente e organização fora do acesso do usuário retornam o mesmo
HTTP 404: `Organização não encontrada.` A autorização precede a consulta dos dados.
Um vínculo autorizado pode consultar metadados de tenant inativo; isso não autoriza
operações empresariais nem reativa o tenant.

## Erros e proteção dos dados

| HTTP | Significado |
| --- | --- |
| 401 | Sessão ausente, inválida, expirada, revogada ou usuário inativo |
| 403 | Usuário sem permissão de provisionamento |
| 404 | Organização ausente ou sem permissão de leitura |
| 413 / 415 | Corpo de criação excessivo ou formato diferente de JSON |
| 422 | Dados inválidos ou campos extras, sem reproduzir valores enviados |
| 503 | Configuração ou infraestrutura indisponível |
| 500 | Falha inesperada, com mensagem genérica |

Respostas dessas rotas usam `Cache-Control: no-store`. Senhas, hashes, permissões,
credenciais do banco e exceções internas não são serializados para o frontend.
Criar e consultar uma organização com autorização registra atividade na sessão;
consultas negadas não renovam o prazo. Atualizações automáticas futuras precisarão
ser diferenciadas de ações reais do usuário.

## Estrutura interna

- `schemas.py`: entrada e saída validadas.
- `repository.py`: acesso aos dados, sem commit.
- `service.py`: criação transacional e consulta interna.
- `router.py`: contratos HTTP e verificação de acesso.
- `identity/authorization.py`: política de permissões persistidas.

Sessões de leitura/autorização são separadas das sessões de escrita que controlam
suas próprias transações. Revogação confirmada bloqueia novas verificações; não
interrompe uma operação que já estava autorizada e em andamento.

## Validação

Os testes HTTP usam login real, Argon2id, PostgreSQL temporário e Redis com namespace
exclusivo. Validam acesso sem token, permissões, troca de tenant, respostas 404
uniformes, expiração, revogação e ausência de dados internos nos erros.
Permissões por empresa, auditoria completa e fluxos de convite continuam pendentes.
