# Edição e cancelamento de despesas

Em Financeiro → Despesas → Despesas registradas, usuários com payables.manage
podem editar e cancelar uma despesa ativa. A consulta e o histórico exigem
payables.read na empresa selecionada.

Editar abre um formulário dedicado. Descrição, categoria, fornecedor, competência,
comprovante, valor e datas podem ser corrigidos. O título vinculado recebe os dados
financeiros na mesma transação. Quando a despesa ainda não tem título, adicionar
vencimento cria um único título vinculado.

Uma despesa com título não pode perder o vencimento. O valor corrigido precisa
ser igual ou superior ao total pago líquido. A emissão não pode passar para depois
de movimentos registrados. Cancelar exige saldo pago líquido zero e cancela o
título vinculado. Para cancelar uma despesa paga, as baixas precisam ser estornadas
primeiro por um usuário autorizado a estornar.

## Consistência e histórico

A revisão da despesa e a revisão do título são verificadas antes de qualquer
alteração. Pagamentos ou alterações concorrentes invalidam a revisão carregada e
exigem atualizar o registro. O bloqueio da organização serializa a operação com
pagamentos, estornos e gerações mensais.

O histórico guarda ator, data e estado anterior e posterior. A tela mostra a
operação e os campos alterados. Novos cadastros, inclusive gerados por recorrência,
passam a registrar histórico. Não são fabricados eventos para cadastros anteriores.
A tela apresenta até 100 eventos recentes por despesa.

As rotas anteriores de edição e cancelamento de títulos também sincronizam a
despesa vinculada e seu histórico. O resultado por competência exclui despesas
canceladas, inclusive aquelas sem título. Dados e eventos só são confirmados se
a transação inteira for concluída.
