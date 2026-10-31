# Revisão e conversão da leitura antiga

## O que muda

O Master pode identificar se a leitura vem da flag `can_read_organization`, de
perfis ou das duas fontes. Pode converter explicitamente a flag em atribuição de
perfil, ou revogar somente essa flag. Não há conversão automática, remoção da
coluna ou alteração da permissão global `can_provision_organizations`.

Todas as operações se limitam ao vínculo e à organização indicados na rota.
Delegados, cargos elevados e operadores da plataforma não recebem autoridade para
revisar/converter flags de clientes. `identity.members.manage` continua exclusiva
do Master e agora também descreve a revisão da concessão antiga.

## Procedimento

1. Consultar o diretório paginado `GET /api/v1/organizations/{org}/members` e
   localizar vínculos com `legacy_read=true`.
2. Consultar a revisão detalhada de leitura. Uma flag configurada em usuário ou
   vínculo inativo não representa acesso efetivo.
3. Se a leitura deve continuar, escolher ou criar um perfil **ativo**, da mesma
   organização, com a permissão exata `["organizations.read"]`. Perfil com qualquer
   permissão adicional, sem permissões ou inativo é recusado na conversão.
4. Consultar a revisão do perfil e as atribuições do vínculo. Se ainda não houver
   atribuição desse perfil, usar revisão de atribuição 0; caso contrário, usar a atual.
5. Confirmar a conversão com a senha do próprio Master. A transação cria/reativa
   a atribuição, registra origem direta, remove a flag e incrementa as revisões
   do vínculo e da atribuição. A leitura é preservada sem adicionar outras ações.

Se a flag não deveria mais existir, revogá-la diretamente. Isso preserva perfis
e delegações já existentes; o resultado pode continuar com leitura efetiva por
outra concessão. Remover um perfil depois de uma conversão não pode recorrer à
flag antiga, pois ela já foi desabilitada.

Se a atribuição escolhida tinha origem delegada, a conversão a torna direta e
registra a origem anterior na auditoria. Isso substitui uma flag que já era direta;
desativar posteriormente o delegado não remove a nova concessão direta.

O Master pode converter ou revogar a própria flag sem perder a propriedade ou
administração. A proteção contra desativação do proprietário continua no fluxo
de status. Conversão exige usuário e vínculo ativos; revogação permite limpar
uma flag de usuário/vínculo inativos sem reativá-los.

## Contratos HTTP

Todas as rotas exigem organização ativa e Bearer do Master atual. Escritas também exigem confirmação
da própria senha e compartilham as proteções da gestão de acesso.

| Método e rota | Resultado |
| --- | --- |
| `GET /api/v1/organizations/{org}/members/{user}/read-access` | Revisão mínima da origem e do acesso efetivo |
| `POST /api/v1/organizations/{org}/members/{user}/legacy-read/convert` | Converte a flag em atribuição direta de perfil de leitura |
| `POST /api/v1/organizations/{org}/members/{user}/legacy-read/revoke` | Remove somente a flag antiga |

Revisão retorna somente `user_id`, `revision` do vínculo, `membership_status`,
`user_status`, `legacy_read` configurada, `legacy_effective`, `profile_read` e
`effective_read`. Os dois últimos consideram concessões válidas, incluindo status,
teto e origem de delegação. Estado e origem são consultados no mesmo snapshot SQL.
Não há nomes, e-mails, hashes, tokens ou permissões da plataforma nessa resposta.

Corpo da conversão, com UUID e senha ilustrativos:

```json
{
  "expected_revision": 1,
  "role_id": "11111111-1111-4111-8111-111111111111",
  "expected_role_revision": 1,
  "expected_assignment_revision": 0,
  "password": "SENHA_DO_MASTER"
}
```

`role_id` deve apontar para um perfil real previamente revisado. A resposta da
conversão inclui a revisão de leitura atualizada, `role_id` e `assignment_revision`.
Revogação recebe apenas `expected_revision` do vínculo e `password`, retornando
a revisão de leitura atualizada. Sucesso é HTTP 200, confirmado após commit.

| HTTP | Significado |
| --- | --- |
| 401 | Sessão ausente ou inválida |
| 404 | Autoridade, senha, tenant, alvo ou perfil recusados, sem distinguir a causa |
| 409 | Revisão desatualizada ou flag já ausente; consultar novamente antes de repetir |
| 413 / 415 / 422 | Corpo acima de 4096 bytes, formato não JSON ou dados inválidos, sem refletir entradas |
| 429 | Limite excedido, com `Retry-After` |
| 503 / 500 | Infraestrutura/capacidade/configuração indisponível ou erro inesperado, sem detalhes internos |

Escritas compartilham 5 admissões por ator/15 minutos, 30 por origem/minuto e 300
gerais/minuto com perfis e status de vínculos. Usam senha limitada por
`AUTH_HASH_CONCURRENCY`, locks e revisões contra concorrência. Recusas não renovam
inatividade. Redis indisponível impede escrita; logout permanece disponível.
Respostas usam `no-store`; HTTPS é obrigatório em staging/production.

## Persistência e limites

Auditoria registra tenant, ator, alvo, perfil escolhido, revisões, flag e origem
anterior/nova da atribuição, sem nome, e-mail, senha ou token nos snapshots.
Falha na auditoria reverte flag, atribuição e revisões na mesma transação.

A migration `c74e901a6bd2`, após `b92f8d06e4a1`, apenas amplia as ações aceitas no
histórico (`LEGACY_READ_CONVERTED` e `LEGACY_READ_REVOKED`). Não altera flags,
status, perfis ou usuários. Downgrade é recusado se esses novos registros já
existirem, preservando a trilha de segurança.

Perfis compartilhados continuam sob gestão explícita do Master: futuras edições
de permissões são operações distintas e auditadas. A conversão valida o conteúdo
exato do perfil no momento da operação, sem torná-lo imutável.

Contratos anteriores de convite/onboarding ainda podem criar concessão de leitura
pela flag. Eles foram preservados por compatibilidade e podem ser revisados por
esse fluxo. Descontinuar a flag e alterar esses contratos é uma etapa própria.
Cadastro jurídico de Company, CNPJ e permissões por empresa seguem no cronograma.

## Validação da entrega

Suíte completa: **302 testes aprovados**, incluindo 28 novos (24 HTTP, 3 de schemas
e 1 de migrations). Cobrem origem da leitura, conversão sem permissões adicionais,
perfil restrito, reuso e origem de atribuição, flags de usuários/vínculos inativos,
revogação independente, isolamento, proteção de sessão, concorrência, rate limit,
cancelamento de hash, rollback de auditoria e preservação do histórico no downgrade.

Migration aplicada ao banco local em `c74e901a6bd2 (head)`, porta 5433. Flags,
status, revisões e contagens anteriores foram preservados, com schema alinhado.
Não houve conversão/revogação de acesso real e não restaram bancos temporários.
Health local 200; três contratos novos no OpenAPI; consulta, conversão e revogação
sem sessão retornaram 401 com `no-store`. O sucesso foi testado em infraestrutura
isolada, sem uso das senhas ou tokens reais do desenvolvedor.
