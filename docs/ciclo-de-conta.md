# Identidade, cadastro e segurança da conta

O usuário representa uma pessoa responsável pelo acesso ao Sistema Digital Financeiro.
A organização e a empresa são entidades separadas. CPF identifica o titular; CNPJ identifica
a pessoa jurídica. Cadastro de usuário não concede permissões administrativas nem acesso a tenants.

## Implementado neste incremento

- Telas de login, cadastro, solicitação/reenvio de confirmação, recuperação, redefinição e segundo fator.
- Cadastro público preparado com nome completo conforme documento, CPF, e-mail e senha de 8 a 128 caracteres.
  A API valida CPF numérico ou formatado, incluindo os dígitos verificadores e bloqueio de números repetidos.
  Isso não comprova titularidade, autenticidade documental ou representação legal.
- Novas identidades por convite também exigem nome completo e CPF; contas existentes continuam com suas
  credenciais e permissões. O bootstrap administrativo da plataforma permanece separado.
- CPF cifrado com Fernet e índice de unicidade por HMAC com contexto próprio. Não retornar CPF, cifra,
  índice, hashes ou segredos nas respostas comuns. Uma identidade pode participar de várias organizações.
- Confirmação e recuperação com tokens aleatórios de 256 bits, armazenados somente como SHA-256,
  finalidade vinculada, expiração e consumo único com bloqueio transacional. Confirmação: 24 horas;
  redefinição: 30 minutos. Reenvio invalida o link anterior da mesma finalidade.
- Redefinição altera a senha, revoga sessões e invalida desafios pendentes na mesma transação.
  Ela não autentica automaticamente nem remove o MFA. Mudança anterior de credencial invalida o token.
- Rate limit compartilhado por Redis, limite de corpo JSON, respostas sanitizadas e `Cache-Control: no-store`.

## Envio de e-mail deliberadamente desativado

O provedor será escolhido posteriormente. Não há SMTP, integração externa, caixa de testes, worker ou
entrega implementados. O contrato `EmailDelivery` é apenas um ponto de extensão, usado com coletor
em memória nos testes isolados. Sem adaptador, as solicitações retornam 503 antes de criar contas ou
links; a interface desabilita o envio e informa indisponibilidade. Não há sucesso fictício.

Antes de habilitar o envio, implementar fila/outbox privada, timeout, retentativa controlada e mensagens
transacionais. O endpoint público deve responder de forma uniforme, inclusive no tempo, sem aguardar
SMTP ou revelar se o destinatário existe. Configurar origem pública HTTPS fixa, nunca derivada do
header Host. Os links previstos são `/confirm-email#TOKEN` e `/reset-password#TOKEN`. O frontend
consome o fragmento em memória e o remove do endereço; não usar query string, analytics ou logs com tokens.

| Rota de API | Finalidade |
| --- | --- |
| `GET /api/v1/auth/capabilities` | Disponibilidade pública dos recursos, sem informações de contas |
| `POST /api/v1/auth/register` | Solicitar cadastro e confirmação |
| `POST /api/v1/auth/email/resend` | Reenviar confirmação |
| `POST /api/v1/auth/email/confirm` | Consumir confirmação |
| `POST /api/v1/auth/password/forgot` | Solicitar redefinição |
| `POST /api/v1/auth/password/reset` | Consumir redefinição |

## Autenticação multifator

TOTP conforme RFC 6238, SHA-1, 6 dígitos e janela de 30 segundos, com tolerância de um intervalo
anterior ou posterior. Cada intervalo aceito só pode ser utilizado uma vez por conta.
O cadastro do autenticador usa chave manual e exige senha atual. O segredo pendente expira em 10 minutos;
somente um código válido ativa o fator. O segredo fica cifrado no banco. Oito códigos aleatórios de
recuperação são exibidos uma única vez e persistidos somente como hashes, com consumo único.

Com MFA ativo, login por senha retorna desafio de 5 minutos, sem token de sessão. O desafio não é Bearer
e não permite acesso a empresas. A sessão é emitida somente após validação do segundo fator, com
revalidação da conta e da credencial sob lock. Desativação exige senha e fator válido. Ativação e
desativação revogam as outras sessões; a sessão que realizou a alteração é preservada. Não há recuperação
automática de MFA apenas por e-mail. Perda de todos os fatores requer processo de identidade separado.

Rotas: `POST /auth/mfa/login` é pública e limitada; `GET /auth/mfa/status` e
`POST /auth/mfa/{setup,enable,disable}` exigem sessão. Todas estão sob `/api/v1`.
A página `/finance/security` funciona mesmo quando o usuário ainda não tem empresas autorizadas.

Configurações opcionais: `AUTH_MFA_ENCRYPTION_KEY` e `AUTH_IDENTITY_ENCRYPTION_KEY`, ambas chaves
Fernet distintas e válidas. Sem chave de MFA, novas ativações ficam indisponíveis e contas já protegidas
não conseguem pular o segundo fator. Sem chave de identidade, novos cadastros não armazenam CPF.
Em produção, injetar via gestão de segredos; preservar as chaves nos procedimentos de restauração.
Rotação precisa recifrar registros e reconstruir o índice de CPF, não apenas substituir a variável.
Valores locais não são versionados. Nenhum segundo fator é ativado automaticamente para usuários existentes.

Migration: `c30f7542eb19`, sem backfill de CPF ou alteração de privilégios existentes. Downgrade bloqueado
quando houver estado de segurança, para evitar perda de fatores, registros de identidade e desafios.

## Próxima etapa: abertura e validação da empresa

Fluxo pretendido: conta confirmada → dados do responsável → dados da empresa → documentos → validação
→ criação da organização e atribuição do primeiro Master em operação atômica. Ainda não implementado.
O cadastro autônomo não deve permitir assumir organização ou CNPJ existente. O provisionamento
administrativo e os convites atuais continuam disponíveis, com suas autorizações próprias.

Requisitos definidos para essa etapa:

- Responsável: nome e CPF já informados; complementar data de nascimento, endereço e vínculo/poderes
  de representação. Definir os demais campos pelo objetivo da verificação, sem coleta indiscriminada.
- Empresa: CNPJ, razão social, nome fantasia quando aplicável, endereço, atividade, regime e inscrições
  pertinentes. Validar os campos conforme o tipo e atividade da pessoa jurídica.
- Contador: identificação, registro profissional, contato e vínculo com a empresa. Cadastrar o contato
  não concede acesso ao ERP; eventual conta recebe convite e permissões específicas.
- Documentos: definir matriz por tipo societário e atividade antes de exigir arquivos. Prever armazenamento
  privado, autorização por objeto, limites e validação de conteúdo, inspeção, retenção e trilha de acesso.
- Reconhecimento facial e fotos de documentos: etapa futura de verificação de identidade, ainda sem
  provedor, upload, biometria, coleta ou alegação de validação implementados.

Referências: [OWASP: recuperação de senha](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html),
[OWASP: MFA](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html),
[RFC 6238](https://datatracker.ietf.org/doc/html/rfc6238).
