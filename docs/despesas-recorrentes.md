# Despesas recorrentes

Em Financeiro → Despesas, uma operação mensal gera uma ocorrência por competência.
As cobranças ficam em Recorrências → Cobranças mensais. Valores fixos criam a
despesa e o título em Contas a pagar. Valores variáveis ficam em revisão até um
usuário com permissão payables.manage confirmar valor, vencimento e comprovante.

A geração começa na competência em que a recorrência é cadastrada. O dia 30 é
ajustado para o último dia de fevereiro quando necessário. A competência e a data
de emissão do lançamento gerado usam o primeiro dia do mês. O vencimento segue o
dia configurado na recorrência. A geração não registra pagamento.

## Ativação das recorrências anteriores

As regras anteriores à migration d0a783e14bc2 não possuíam um autorizador persistido.
Elas aparecem como Aguardando ativação. Um usuário autorizado deve abrir Ativar
geração e salvar a regra. A geração começa na competência em que a regra é ativada,
sem inferir meses anteriores. Revise a regra antes de ativá-la.

## Processamento

A API executa a verificação ao iniciar e a cada 60 segundos enquanto está ativa.
Fechar o navegador não interrompe a geração. Se a API ficar desligada, ela recupera
as competências pendentes ao voltar. Cada passagem recupera até 12 competências
por regra, continuando as demais na passagem seguinte.

O processamento está habilitado por padrão fora do ambiente de testes. A variável
RECURRING_EXPENSES_ENABLED=false permite desabilitá-lo explicitamente. No ambiente
de testes o gerador é chamado diretamente, com data controlada.

Cada ocorrência usa uma chave determinística por recorrência e mês e uma restrição
única no banco. A despesa, o título, o histórico de criação e o avanço do calendário
são persistidos na mesma transação. Múltiplas instâncias da API serializam a operação
pelo bloqueio da organização. Uma falha reverte a operação e permite nova tentativa.

## Permissões e histórico

A geração automática revalida o usuário que autorizou a regra, seu vínculo, a empresa,
o contrato e a permissão payables.manage. Uma revogação impede novas gerações até
que um usuário autorizado salve a recorrência novamente.

Alterações afetam as competências ainda não geradas. Ocorrências geradas e rascunhos
mantêm o retrato da regra e do fornecedor no momento de criação. Cancelar a regra
interrompe a geração e bloqueia a confirmação dos rascunhos pendentes. Despesas e
títulos já gerados permanecem no histórico e seguem seu próprio fluxo financeiro.

A confirmação de uma cobrança variável é idempotente por ocorrência. Repetir os
mesmos dados devolve o lançamento anterior. Dados diferentes após a confirmação
produzem conflito. A consulta mostra até 200 ocorrências recentes por empresa.
