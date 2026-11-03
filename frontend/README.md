# Frontend do SD Financeiro

Aplicação Angular com TypeScript, componentes standalone, formulários reativos,
rotas carregadas sob demanda e serviços HTTP tipados.

## Execução

Com Node compatível e o backend disponível em `127.0.0.1:8000`, execute nesta pasta:

```powershell
npm ci
npm start
```

Interface: `http://127.0.0.1:4200`. O proxy encaminha somente `/api/` ao backend
local. Não configure um endereço externo para receber credenciais. O servidor
de desenvolvimento não é uma configuração de produção.

```powershell
npm run build
npm test
npm audit
```

Build em `dist/sd-financeiro/browser`, sem source maps de produção. O lockfile
fixa a árvore; `overrides` aplica versões corrigidas de glob/minimatch na cadeia
do CLI. Rever esses overrides quando atualizar Angular/CLI, preservando build,
testes e auditoria. Eles não pertencem ao bundle financeiro do navegador.

## Fluxos

- Login com conta existente e saída com revogação no backend.
- Seleção de empresa dentre contextos financeiros autorizados.
- Visão financeira com saldos atuais, atividade do período e valores diários.
- Títulos com paginação e filtro de situação cadastral.
- Cadastro, edição e cancelamento conforme `payables.manage`.
- Detalhes, posição e movimentos conforme `payables.read`.
- Baixa e estorno com suas chaves independentes e confirmação explícita.

A interface não cadastra usuários publicamente, concede permissões, cria empresas
ou executa pagamentos bancários. Onboarding e administração permanecem nos
contratos existentes do backend até os próximos incrementos de interface.

## Sessão e dados

Token somente em memória; não é salvo em localStorage, sessionStorage ou cookies.
Recarregar/fechar a aplicação exige novo login. Não há logout por prazo absoluto
nem polling para prolongar a sessão sem interação. O servidor controla inatividade;
401 limpa a sessão do cliente. Sair só é confirmado após revogação responder.

O interceptor adiciona Bearer exclusivamente a URLs relativas de `/api/v1/`.
Não há analytics, fontes externas, service worker ou cache de dados financeiros.
Angular interpola textos como texto; não usar innerHTML ou bypass de sanitização
para descrições/motivos. Permissões da tela são conveniência: cada operação volta
a ser autorizada pelo backend.

Troca de empresa limpa os dados anteriores. Respostas atrasadas são descartadas.
Valores exibidos usam formatação textual exata; a conversão numérica do gráfico
serve apenas ao desenho, nunca a saldo, envio ou cálculo financeiro.

Baixa/estorno conserva chave e payload enquanto a operação estiver aberta, inclusive
em resultado desconhecido. Não há retry automático. Sair/trocar contexto após uma
tentativa incerta exige aviso; recarregar perde referências em memória. Depois de
um resultado incerto, conferir movimentos antes de iniciar outra intenção.
Criação de título ainda não é idempotente: timeout bloqueia a repetição na mesma
janela e orienta conferir os registros com usuário autorizado.

## Conferência visual isolada

Após build, `node tools/qa-server.mjs` abre uma prévia **sintética**, em
`127.0.0.1:4201`, sem conexão ou proxy ao ERP. Use somente a conta fictícia
`qa@example.invalid` / `somente-qa`. Escritas são recusadas; serve para conferir
layout, navegação e formulários, não para homologar regras financeiras.
Não usar credenciais reais nessa prévia. Encerrar o processo após a conferência.

Os testes Angular cobrem transporte de token, ausência de persistência de segredo,
401 atrasado, isolamento após troca de empresa, valores exatos e replay de operações.
Regras financeiras e autorização também são testadas no PostgreSQL/Redis isolados.

Contratos: [títulos](../docs/api-contas-a-pagar.md),
[movimentos](../docs/baixas-e-estornos.md),
[resumo](../docs/resumo-contas-a-pagar.md) e
[contexto e arquitetura](../docs/interface-financeira.md).

As rotas públicas `/register`, `/resend-confirmation`, `/confirm-email`, `/forgot-password`, `/reset-password` e `/mfa` compartilham o layout de acesso. `/finance/security` administra o segundo fator do usuário autenticado, inclusive sem empresas. O cadastro exige nome completo, CPF, e-mail e senha; o envio permanece bloqueado até existir transporte de e-mail. Consulte [Ciclo de conta](../docs/ciclo-de-conta.md). O fundo é uma imagem ilustrativa fornecida para o projeto, servida localmente; não representa dados reais.
