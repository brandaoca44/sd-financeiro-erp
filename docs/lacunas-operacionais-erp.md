# Lacunas operacionais para o ERP de serviços

Comparação funcional para priorização interna. Cadastros, alertas, migração, permissões e
recuperação já estão no planejamento. A lacuna principal é conectar os registros em processos
que permitam conferir o resultado e tratar exceções.

| Prioridade | Capacidade a detalhar | Aplicação no SDF |
| --- | --- | --- |
| Alta | Conciliação bancária | Importar extrato, sugerir vínculos com baixas e recebimentos e revisar diferenças antes de confirmar. Sem executar pagamentos. |
| Alta | Fechamento de períodos | Conferir pendências, bloquear alterações retroativas e permitir correções controladas com justificativa, autorização e auditoria. |
| Alta | Compras de ponta a ponta | Solicitação → cotação → aprovação → pedido → confirmação de entrega/serviço → nota → obrigação. Conferir divergências de valor, quantidade e contraparte. |
| Alta para Serviços | Projetos, horas e margem | Relacionar horas, despesas e faturamento ao projeto/contrato. Separar custo previsto, realizado e horas faturáveis. |
| Média | Integração contábil | Relacionar categorias a um plano de contas validado pelo contador; exportar eventos e referências com conferência. Não confundir resultado gerencial com escrituração completa. |
| Média | Fila de exceções e pendências | Reunir documentos sem vínculo, extratos sem conciliação, importações rejeitadas, divergências e aprovações pendentes. Mostrar responsável e trilha de resolução. |

Conciliação e fechamento vêm antes de indicadores contábeis mais amplos. Para diferenciar o SDF
em Serviços, priorizar a ligação **contrato → serviço executado → faturamento → recebimento → margem**.
Esses itens entram como requisitos de avaliação, sem promessa de cobertura atual ou aumento
automático de escopo dos planos. A decisão comercial será tomada após detalhar dependências e custos.

Referências de produto: [conciliação bancária](https://docs.frappe.io/erpnext/bank-reconciliation),
[fechamento de períodos](https://docs.frappe.io/erpnext/accounting-period),
[pedidos de compra](https://docs.frappe.io/erpnext/purchase-order),
[custos de projetos](https://docs.frappe.io/erpnext/project-costing) e
[lançamentos contábeis](https://docs.frappe.io/erpnext/accounting-entries).
