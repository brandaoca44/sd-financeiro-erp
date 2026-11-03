# Catálogo e página de assinatura

O catálogo de trabalho `business-v1-draft` organiza Essential, Professional e Enterprise no
segmento Empresarial/Serviços. A mesma matriz será usada para outros segmentos somente depois
da implementação e homologação de cada domínio.

- `GET /api/v1/catalog/plans` retorna definições públicas, limites propostos e disponibilidade
  dos recursos. Não consulta contratos nem retorna dados de organizações, preços ou credenciais.
- `/plans` é a comparação pública, acessível pelo link **Conhecer os planos** no login.
- `/finance/subscription` integra a mesma comparação em **Configurações → Assinatura e planos**.
  Exige sessão; não depende de ter uma empresa selecionada.
- Os blocos resumem os planos. A seleção abre detalhes por área; a comparação completa fica
  recolhida. A página não solicita pagamento, cria contrato ou altera permissões. Recursos
  planejados são identificados separadamente.

## Política comercial interna

O catálogo imutável define disponibilidade, composição e limites iniciais.
`evaluate_access` verifica snapshots internos de usuário, organização, empresa e contrato,
incluindo segmento, vigência, empresa habilitada, recurso disponível e permissão para a ação.
`evaluate_capacity` verifica capacidade proposta sem reservar vagas. Enterprise exige limite
explícito para cada capacidade avaliada. Os motivos da decisão são internos e não devem
revelar ao cliente a existência de recursos ou contratos de outro tenant.

A persistência e a autorização comercial de contas a pagar estão descritas em
[Contratos Empresarial](contratos-empresarial.md). A cobrança e os aceites
de documentos revisados seguem como etapas posteriores.

## Imagem da página

Arquivo: `frontend/public/brand/plans-boardroom.png`. Criado com a ferramenta nativa de geração
de imagens para esta página. A imagem é ilustrativa e não contém dados financeiros reais.

Prompt final:

> Use case: photorealistic-natural. Asset type: wide photographic background for the subscription plans page of Sistema Digital Financeiro, a serious enterprise ERP. Create a NEW scene, distinctly different from a laptop on a sunset desk. Premium corporate boardroom in a modern high-rise, polished dark conference table, architectural glass partitions, panoramic city in blue hour daylight, an elegant large wall display showing only subtle abstract blue data visualization shapes with NO legible text or financial figures. No people. Restrained navy, slate, steel and cyan palette consistent with a corporate financial software interface. Architectural editorial photography, realistic glass and brushed-metal textures, balanced sophisticated lighting, no excessive science-fiction effects. Wide cinematic horizontal composition, usable quiet dark space across the upper center for white HTML text; subject architectural details toward edges, lower half naturally darker behind separate HTML pricing cards. No logo, typography, words, watermark, money piles, UI mockup or pricing cards baked into the image. This is a standalone background photo, not an entire website design.
