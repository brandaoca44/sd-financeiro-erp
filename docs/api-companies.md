# Cadastro empresarial — Company

## Escopo da entrega

Company é o cadastro jurídico de uma empresa dentro de uma Organization. Esta
etapa permite criar, consultar, listar, editar nomes e ativar/inativar o cadastro.
Não cria contas, vínculos, empresas em outros tenants ou dados fiscais/financeiros.

O **Master atual**, com usuário e vínculo ativos em organização ativa, administra
esses cadastros. Colaboradores podem consultar empresas ativas mediante concessão
explícita de `companies.read` para cada empresa. `companies.manage` e a gestão das
concessões continuam exclusivas do Master. Leitura do tenant, cargo CEO, delegação
de perfis ou provisionamento da plataforma não concedem esse acesso. Consulte o
[contrato de acesso por empresa](acesso-por-empresa.md).

## Contratos HTTP

Todas as rotas exigem `Authorization: Bearer`. Escritas também confirmam a senha
do próprio Master; tenant e autor não são aceitos no corpo.

| Método e rota | Resultado |
| --- | --- |
| `POST /api/v1/organizations/{organization_id}/companies` | 201, empresa criada e `Location` com seu caminho |
| `GET /api/v1/organizations/{organization_id}/companies` | Página com `items` e `next_cursor` |
| `GET /api/v1/organizations/{organization_id}/companies/{company_id}` | 200, cadastro do tenant exato |
| `PUT /api/v1/organizations/{organization_id}/companies/{company_id}` | 200, configuração atualizada com nova revisão |

Criação, com dados e senha ilustrativos:

```json
{
  "legal_name": "Empresa Exemplo Ltda",
  "trade_name": "Empresa Exemplo",
  "tax_id": "12.ABC.345/01DE-35",
  "password": "SENHA_DO_MASTER"
}
```

`legal_name` é obrigatório, entre 1 e 200 caracteres após remover espaços nas
extremidades. `trade_name` é opcional, com o mesmo limite; vazio vira `null`.
Criação não aceita status, revisão, permissões ou CPF. O sistema define status
interno `ACTIVE` e revisão 1.

PUT é substituição de configuração: recebe `legal_name`, `trade_name` opcional,
`status` (`ACTIVE` ou `INACTIVE`), `expected_revision` inteiro positivo e senha.
Não aceita alteração de CNPJ ou Organization. O CNPJ é imutável nessa edição;
correções de identidade jurídica precisam de um fluxo próprio, ainda não implementado.
Atualização com revisão antiga é recusada, inclusive em solicitações concorrentes.

Resposta contém somente `id`, `organization_id`, `legal_name`, `trade_name`, `tax_id`,
`status`, `revision`, `created_at` e `updated_at`, sem relacionamentos ou credenciais.
Listagem aceita `limit` de 1 a 100 (padrão 50) e `cursor` UUID. Cadastros inativos
continuam visíveis ao Master para revisão e reativação. Não há exclusão física.
Para colaboradores, a listagem filtra empresas autorizadas antes da paginação.
Inativar e reativar uma empresa limpa concessões de leitura sem restaurá-las.

## Validação do CNPJ

Aceita CNPJ numérico e alfanumérico: 12 posições de A–Z/0–9 e dois dígitos
verificadores numéricos. Valida módulo 11, pesos de 2 a 9 e conversão ASCII menos
48 conforme o [manual técnico da Receita Federal](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/documentos-tecnicos/cnpj/manual-dv-cnpj.pdf).
Os CNPJs numéricos existentes permanecem válidos, conforme as
[perguntas e respostas oficiais](https://www.gov.br/receitafederal/pt-br/centrais-de-conteudo/publicacoes/perguntas-e-respostas/cnpj/cnpj-alfanumerico.pdf).
Fontes conferidas em 31/10/2026.

Entrada deve ser string limpa de 14 posições ou máscara completa
`AA.AAA.AAA/AAAA-00`. Letras ASCII minúsculas são convertidas para maiúsculas após
validar o formato. Espaços nas extremidades são removidos; letras não são descartadas.
CPF, máscaras parciais, separadores extras, dígitos repetidos e caracteres Unicode
parecidos com letras/dígitos ASCII são recusados. Banco persiste 14 caracteres
canônicos e também valida formato/DV pela função `sd_is_valid_cnpj`.

Validação local não comprova existência, situação cadastral ou representação legal
perante a Receita. Não há consulta externa ou preenchimento automático. `ACTIVE`
é status interno do ERP, sem afirmar regularidade fiscal do CNPJ.

## Isolamento e unicidade

O CNPJ é único **dentro da organização**, incluindo registros inativos. Repetição
nesse escopo retorna conflito. Organizações diferentes podem cadastrar o mesmo
CNPJ de forma independente, com UUIDs e dados próprios; isso não cria vínculo,
compartilhamento ou descoberta de informações de outro cliente.

A migration substitui a unicidade global inicial por índice único
`(organization_id, tax_id)`. Toda consulta do repository inclui o tenant; não há
endpoint de consulta global por CNPJ. Conhecer CNPJ ou UUID não concede acesso.

## Segurança, erros e auditoria

Escritas compartilham com a gestão de acesso os limites de 5 admissões por ator/15
minutos, 30 por origem/minuto e 300 gerais/minuto. Usam o mesmo limite de concorrência
de Argon2 e autorização transacional compartilhada em `identity/access_security.py`.
Cancelamento aguarda o fim do hash antes de liberar a vaga e reverte a transação.
Mudanças confirmadas e leituras autorizadas registram atividade; recusas não renovam.

| HTTP | Situação |
| --- | --- |
| 401 | Sessão ausente ou inválida |
| 404 | Autoridade, senha, tenant ou cadastro recusados, sem distinguir existência |
| 409 | CNPJ já cadastrado no tenant autorizado ou revisão desatualizada |
| 413 / 415 / 422 | Corpo acima de 4096 bytes, formato não JSON ou entrada inválida, sem refletir valores |
| 429 | Limite excedido, com `Retry-After` |
| 503 / 500 | Infraestrutura/capacidade/configuração indisponível ou erro inesperado, sem detalhes internos |

Respostas usam `Cache-Control: no-store`; HTTPS é exigido em staging/production.
Falha de Redis impede escrita; logout permanece disponível. A auditoria grava
tenant, empresa, ator, ação, revisões, status e nomes dos campos alterados, sem
replicar razão social, nome fantasia, CNPJ, senha ou token nos snapshots. Falha da
auditoria reverte cadastro/edição na mesma transação. Não há histórico completo
dos valores anteriores dos nomes nem API para apagar os registros de auditoria.

## Migration e próximos passos

`d85fa1049ce3`, após `c74e901a6bd2`, valida registros anteriores antes de criar
constraints, sem normalizar ou corrigir dados silenciosamente. Inconsistências
interrompem a atualização com erro genérico para revisão autorizada. A tabela de
empresas é bloqueada durante a transição para evitar inserção concorrente inválida.
Dados válidos são preservados, com revisão inicial 1.

Downgrade é recusado quando há histórico de empresas ou CNPJs repetidos em tenants
distintos, evitando apagar auditoria ou restaurar unicidade global incompatível.
Não resolve conflitos removendo cadastros automaticamente.

Pendências: interface de cadastro/seleção,
dados fiscais e endereços conforme os módulos, verificação externa opcional e
correção controlada de CNPJ. Financeiro, fiscal e operações futuras deverão avaliar
o escopo da empresa e seu status; a leitura de cadastro não concede essas ações.

## Validação da entrega

Suíte completa: **332 testes aprovados**, incluindo 30 novos (6 de contratos/CNPJ,
21 HTTP e 3 de migrations). Cobertura inclui exemplos oficiais numérico/alfanumérico,
Python/PostgreSQL, duplicidade no tenant, cadastros independentes entre tenants,
escopo por UUID, ausência de acesso por cargo/flag/delegação, transferência do
Master, revisões, rate limit, cancelamento, erros seguros e rollback de auditoria.
Também valida bloqueio de legado inválido, preservação de histórico e downgrade
incompatível. As regressões da autorização compartilhada passaram na suíte completa.

Migration aplicada ao PostgreSQL local em `d85fa1049ce3 (head)`, porta 5433, com
schema alinhado e dados/flags/status/revisões/contagens anteriores preservados.
Nenhuma empresa real criada/alterada e nenhum banco temporário restante. Health
local 200, quatro operações no OpenAPI e todas recusadas sem sessão com 401 e
`no-store`. Testes de sucesso usaram infraestrutura isolada, sem credenciais reais.
