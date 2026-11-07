# Central de alertas financeiros

A Central de alertas fica no menu Financeiro e no sino da barra superior.
Cada consulta usa a empresa selecionada e exige payables.read no backend.

Os tipos de alerta são contas vencidas, contas que vencem hoje, contas com
vencimento entre amanhã e sete dias a partir de hoje e cobranças recorrentes
aguardando revisão. As datas usam o fuso America/Sao_Paulo.

O valor mostrado é o saldo atual do título, descontando baixas e considerando
estornos. Títulos cancelados e títulos com saldo zero ficam fora da central.
Cobranças variáveis ficam fora dos saldos até a confirmação e aparecem com valor
a confirmar. Rascunhos de recorrências canceladas ficam fora dos alertas.

O sino mostra o total de pendências. A central permite filtrar por tipo e abrir
o título ou a ocorrência exata. Usuários com consulta podem ver uma cobrança em
revisão, enquanto sua confirmação exige payables.manage.

Os alertas refletem os registros atuais e desaparecem quando a pendência é
resolvida. A central não mantém um indicador separado de notificações não lidas.

## Atualização e isolamento

A interface atualiza ao navegar, após operações financeiras e a cada 60 segundos
com a página visível. A opção Atualizar solicita uma nova consulta. Na troca de
empresa, o estado anterior é limpo e a requisição anterior é cancelada.

O endpoint não renova o prazo de inatividade, para que a atualização automática
não mantenha a sessão aberta. A API exige uma sessão válida em toda consulta.

Os totais e itens usam o mesmo snapshot SQL. A tela mostra até 200 pendências,
por prioridade e vencimento. Os contadores incluem todas as pendências, mesmo
quando o limite de exibição é atingido. As respostas usam Cache-Control: no-store.
