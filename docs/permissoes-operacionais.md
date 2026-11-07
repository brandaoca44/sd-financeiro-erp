# Permissões operacionais por empresa

Os acessos pertencem ao vínculo do usuário com uma empresa específica. Cargo e plano não concedem permissão. O Master administra a própria organização, sem acesso a outras organizações.

Em **Configurações → Permissões da empresa**, o Master seleciona o usuário e concede ou revoga cada ação. Toda alteração exige sua senha, confere revisões do vínculo, da empresa e da concessão e gera histórico de auditoria. O Master não precisa de concessões diretas e não pode alterar os próprios acessos por essa tela.

| Área | Permissões |
| --- | --- |
| Contas a pagar e despesas | `payables.read`, `payables.manage`, `payables.settle`, `payables.reverse` |
| Faturamento e clientes | `billing.read`, `billing.manage`, `billing.receive`, `billing.reverse` |
| Cadastro profissional | `people.read`, `people.create`, `people.update`, `people.terminate` |
| Documentos, endereço e contato | `people.documents` |
| Remuneração e prévia de folha | `people.compensation` |
| Banco, agência, conta e Pix | `people.bank` |

Consultar não permite registrar, editar, receber, pagar, estornar ou desligar. As telas de listagem precisam de consulta para localizar os registros; as APIs verificam a permissão específica de cada ação.

A consulta básica de colaboradores retorna somente identificação profissional e histórico do vínculo. Dados protegidos sem concessão são **omitidos da resposta da API**, não apenas escondidos na tela. Para alterar um grupo protegido é necessário também `people.update`; para consultar, `people.read`. Atualizações parciais preservam os grupos não enviados.

O novo cadastro continua exigindo CPF válido, celular e dados bancários. Quem o realiza precisa de `people.create`, `people.documents` e `people.bank`. A remuneração exige a concessão adicional correspondente. Passaporte permanece opcional. O conteúdo protegido continua criptografado em armazenamento. A prévia de folha permanece restrita ao ambiente de desenvolvimento.

Todas as operações exigem usuário, vínculo, organização e empresa ativos, contrato Empresarial válido e empresa habilitada. Faturamento usa a licença `business.receivables`; Pessoas usa `business.staff_costs`. Uma permissão de Contas a pagar não abre esses módulos. As concessões são reavaliadas no backend a cada operação; as escritas revalidam sessão e autorização dentro da transação.

As concessões usam as rotas existentes `GET/PUT /api/v1/organizations/{organization_id}/companies/{company_id}/members/{user_id}/permissions/{permission_key}`. O `PUT` exige status, revisões esperadas e senha do Master. Não são aceitos curingas ou permissões administrativas nessa rota. `can_manage_access` no contexto do frontend serve à navegação; a autoridade é sempre verificada novamente na API.

A migration `a14c5e93b207` expande o catálogo fechado de concessões sem criar acessos para usuários existentes. O downgrade é bloqueado enquanto existirem concessões das novas áreas, preservando o histórico.

O Master também consulta o [Histórico de operações](auditoria-operacoes.md), sem conceder acesso ao histórico aos demais perfis.


A permissão de consulta de Faturamento também habilita os [indicadores de Contas a receber](contas-a-receber-painel.md), sem conceder leitura de Contas a pagar.


As [Contas financeiras da empresa](contas-financeiras.md) usam accounts.read, accounts.manage e accounts.bank, independentes dos acessos às contas bancárias pessoais e dos colaboradores.


O saldo calculado de uma conta exige accounts.read, payables.read e billing.read. Vincular movimentos antigos exige também accounts.manage e a permissão de registro da área correspondente.
