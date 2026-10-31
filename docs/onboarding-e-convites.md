# Onboarding e convites

## Fluxo implementado

1. O operador com `can_provision_organizations` cria a organização e indica o e-mail
   do primeiro Master. Confirma a própria senha; não escolhe a senha do convidado.
2. A API retorna um convite válido por **24 horas**, sem criar conta, vínculo ou
   proprietário antes do aceite. O operador não ganha acesso aos dados do cliente.
3. O convidado apresenta o token no corpo JSON. Se ainda não tiver conta, informa
   nome e define senha de 8 a 128 caracteres. Se já tiver conta, confirma a senha
   existente; nome, senha, status e permissões da plataforma não são sobrescritos.
4. O aceite cria o vínculo ativo e registra o primeiro Master na mesma transação.
   O vínculo inicial tem leitura dos metadados da própria organização, sem acesso
   a outras organizações, empresas ou módulos futuros. Nenhuma sessão é emitida:
   depois do aceite, o convidado usa o login normal com o e-mail convidado.
5. O Master pode convidar colaboradores, com acesso mínimo. O convite comum não
   concede Master, provisionamento ou perfis. `can_read_organization` começa falso;
   o Master pode conceder explicitamente essa leitura na emissão do convite.

Não há cadastro público irrestrito. A conta representa a pessoa que opera o ERP;
o cliente continua empresarial. Este onboarding cadastra o espaço `Organization`.
Cadastro jurídico de `Company`, CNPJ e regras fiscais continuam em etapa própria.

## Contratos HTTP

Todas as escritas aceitam somente JSON e recusam campos extras. Nos exemplos, os
campos de senha e token são marcadores; valores reais nunca devem ir para logs ou chat.

| POST | Autenticação e entrada | Resultado |
| --- | --- | --- |
| `/api/v1/organizations/onboarding` | Bearer do provisionador; `organization_name`, `email`, `password` do operador | 201: organização e convite inicial |
| `/api/v1/organizations/{organization_id}/owner-invitations` | Bearer do provisionador; `email`, `password` do operador; organização sem proprietário | 201: convite de Master para organização existente |
| `/api/v1/organizations/{organization_id}/invitations` | Bearer do Master; `email`, sua `password`, `can_read_organization` opcional | 201: convite de colaborador |
| `/api/v1/organizations/{organization_id}/invitations/{invitation_id}/revoke` | Bearer e `password`; provisionador para convite inicial, Master atual para colaborador | 204, sem corpo |
| `/api/v1/auth/invitations/accept` | Sem Bearer; `token`, `password` do convidado e `name` obrigatório somente para conta nova | 204, sem corpo |

Exemplo de onboarding:

```json
{
  "organization_name": "Empresa Exemplo",
  "email": "responsavel@example.com",
  "password": "SENHA_DO_OPERADOR"
}
```

Emissão retorna somente `organization_id`, `invitation_id`, `invitation_token` e
`expires_at`. O token original aparece **uma única vez nessa resposta**, disponível
apenas ao emissor autenticado e reautenticado. O banco guarda somente SHA-256.
Não existe endpoint para recuperar o token ou consultar convites por e-mail.

Nesta etapa não há integração de e-mail nem envio automático. O emissor entrega o
token somente ao destinatário, por canal privado previamente confirmado. O token
permite criar a conta caso o e-mail ainda não exista: tratá-lo como credencial.
Não colocá-lo em URL, planilha de controle, log ou armazenamento persistente do
navegador. Se houver dúvida sobre a entrega, revogar e emitir outro convite.

A entrega manual depende da confiança no emissor e não comprova tecnicamente a
titularidade do e-mail. Quem possuir o token poderá aceitar uma conta nova. Antes
de produção, integrar entrega direta e verificação de e-mail; o fluxo atual não
deve ser apresentado como proteção contra impersonação por um emissor malicioso.

Reemitir para o mesmo e-mail na organização revoga o convite pendente anterior.
Para Master inicial, reemitir também revoga qualquer convite inicial pendente,
mesmo para outro e-mail. Há no máximo um convite inicial pendente por organização.
Revogar novamente é idempotente enquanto o autor continuar autorizado; convite
já aceito não pode ser revogado. Gestão de vínculos existentes é um fluxo separado.

## Segurança e integridade

- Gestão exige sessão, confirmação da senha e autoridade atual. O operador não
  pode convidar colaboradores nem substituir Master existente. O Master não pode
  emitir convites para outro tenant ou escolher privilégios da plataforma.
- O aceite revalida organização e emissor ativos, vínculo do Master ativo e
  propriedade atual. Transferir Master invalida convites comuns emitidos pelo antigo
  proprietário. Perder a permissão de provisionamento invalida convites iniciais.
- Token é de uso único. Expiração é reavaliada após o trabalho de senha. Convites
  não reativam usuários ou vínculos inativos nem alteram um vínculo já existente.
  Para proprietário com vínculo já existente, usar a designação protegida já disponível.
- Locks serializam aceite, revogação, reemissão e designação no tenant. A criação
  da mesma conta por convites de tenants diferentes é serializada pelo e-mail.
  FKs, constraints e índices únicos protegem a integridade, incluindo o vínculo
  do aceitante na organização exata. Falhas revertem toda a transação.
- Trilha mínima: organização, e-mail destinatário, concessão de leitura, emissor,
  datas e responsáveis por aceite/revogação. O histórico de propriedade registra
  o aceite inicial pelo novo Master. Senhas e tokens originais não são persistidos.
- Gestão e aceite usam namespaces Redis separados do login e da transferência.
  Cada grupo permite 5 admissões em 15 minutos por ator autenticado (gestão) ou
  token apresentado (aceite), 30 por origem/minuto e 300 gerais/minuto. IP vem da
  conexão; trocar headers encaminhados não reinicia o contador. Chaves usam HMAC.
- Todos compartilham `AUTH_HASH_CONCURRENCY` por worker. Cancelar uma requisição
  mantém a vaga até terminar Argon2 e reverte a escrita. Gestão concluída renova
  inatividade na mesma transação; recusas e aceite sem sessão não renovam sessões.

## Respostas e operação local

| HTTP | Situação |
| --- | --- |
| 201 / 204 | Emissão ou conclusão, conforme contrato |
| 400 | Aceite negado, com mensagem única para token, senha, conta ou estado inválidos |
| 401 | Gestão sem sessão válida |
| 404 | Gestão negada sem distinguir tenant, destinatário ou autoridade |
| 413 / 415 / 422 | Corpo acima de 4096 bytes, formato não JSON ou dados inválidos, sem refletir entrada |
| 429 | Limite excedido, com `Retry-After` |
| 503 / 500 | Infraestrutura/capacidade/configuração indisponível ou erro inesperado, sem detalhes internos |

Todas as respostas usam `Cache-Control: no-store`. HTTPS é obrigatório em
staging/production. Falha de Redis impede gestão e aceite; logout permanece disponível.
Não repetir automaticamente emissão com resultado incerto: ainda não há contrato
de idempotência HTTP. Uma reemissão posterior invalida o token pendente anterior.

A migration `f3a82c17d905`, após `e7b1c90a42d3`, cria apenas a tabela de convites e
suas constraints. Não cria usuários, convites, vínculos ou proprietários reais.
Testes automatizados usam PostgreSQL temporário e Redis com namespace exclusivo.

Validação: 208 testes aprovados na suíte completa, sendo 35 novos nesta etapa.
A migration foi aplicada ao banco local em `f3a82c17d905 (head)`, porta 5433, com
schema alinhado, contagens anteriores preservadas e zero convites criados. Não
restaram bancos temporários. A API local foi reiniciada com o código atualizado:
health 200, cinco contratos presentes no OpenAPI, gestão sem sessão 401 e aceite
de token inexistente 400, com `no-store`. O sucesso foi testado apenas na infraestrutura
isolada, sem credenciais reais do desenvolvedor.

Perfis e delegação limitada de atribuições estão no [contrato de perfis](perfis-e-permissoes.md).
Pendências: frontend de aceite/gestão, entrega por e-mail, política de retenção de
convites expirados, recuperação de conta e administração global de identidades.
Ativação/desativação por tenant está no [ciclo dos vínculos](ciclo-de-vida-de-vinculos.md).
Permissões por área/empresa continuam no cronograma, conforme os módulos existirem.
O bloqueio local de senhas previsíveis é mínimo e não substitui uma política
abrangente de senhas comprometidas antes da produção.
