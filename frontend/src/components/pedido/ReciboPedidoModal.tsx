// Modal "Imprimir Pedido" — preview de recibo estilo térmico (réplica de
// `Pedido_48_COL`, FrmManPedBar.frm) + impressão via um iframe oculto
// (ver src/utils/printHtml.ts). Só web — não existe infraestrutura de
// impressão térmica silenciosa (socket/agente local) nesta migração ainda
// (ver CLAUDE.md > "Platform Scope"); decisão explícita do usuário
// 2026-07-16: preview + impressão do navegador, entregável agora sem essa
// infra.
//
// A impressão em si NÃO usa o truque de CSS "esconde tudo com `body *`,
// mostra só o #id do recibo" — na prática saía em branco (reportado pelo
// usuário 2026-07-16: o preview de impressão só trazia o cabeçalho/rodapé
// nativos do navegador, nada do conteúdo), provavelmente por causa de
// algum ancestral (Modal/ScrollView/Pressable) cortando o conteúdo via
// overflow/posicionamento. Um iframe oculto com seu PRÓPRIO documento HTML
// evita esse problema inteiro — por isso o conteúdo é montado duas vezes:
// como JSX (preview na tela) e como string HTML (só na hora de imprimir,
// em `buildHtml`). Mantenha as duas versões em sincronia ao alterar o
// conteúdo do recibo/ticket.
//
// Reaproveita a mesma lista já usada por "Pedido Totalizado" (Command65,
// já implementado em usePedidoItens.ts) pro agrupamento de itens
// repetidos — o checkbox "Imprimir Totalizado" do legado (Check100,
// default marcado) vira o toggle "agrupado" aqui.
import { useEffect, useState } from "react";
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL, formatDateBR, fmtNum } from "@/src/utils/format";
import { apiGet } from "@/src/utils/api";
import { printHtml, escHtml } from "@/src/utils/printHtml";
import { Connection } from "@/src/utils/storage/connections";
import { PedidoData, ClienteRow, ClienteResumo, ItemPrintData } from "./types";
import { UsePedidoItens } from "./usePedidoItens";
import { styles } from "./styles";

const isWeb = Platform.OS === "web";

// Largura da bobina térmica usada pra recibo/ticket de cozinha — confirmada
// pelo usuário 2026-07-23 (impressora de 80mm). Sem passar isso pro
// `printHtml`, o navegador imprime na página padrão dele (A4/Letter), sem
// noção da largura real do rolo, o que desproporciona o cupom (achado ao
// vivo, comparando contra um cupom impresso de verdade). Se algum cliente
// usar bobina de 58mm, isto vira um campo de configuração — por ora, fixo,
// já que só uma largura foi confirmada até agora.
const PAPER_WIDTH_MM = 80;

// Clientes reservados (Mesa/Comanda) costumam ter `cgc_cpf` gravado como
// "0"/zeros em vez de vazio — sem esse filtro o recibo imprimia "Doc: 0",
// um dado sem sentido pro cliente final. Achado comparando a impressão real
// contra o recibo legado VB6 (que simplesmente omite a linha quando não há
// documento de verdade), 2026-07-18.
function temDocumentoValido(cgc: string | null | undefined): boolean {
  const v = (cgc || "").replace(/\D/g, "");
  return v.length > 0 && !/^0+$/.test(v);
}

type Empresa = {
  fantasia?: string | null; rz_social?: string | null; uf?: string | null;
  endereco: string; numero: number | null; complemento: string; bairro: string; cidade: string;
  cep: string; ddd: string | number; telefone: string; celular: string; cgc: string; inscr_est: string;
};

type FormaPagLinha = { descricao: string; forma_pag: string; valor: number };

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  pedido: PedidoData | null;
  cliente: ClienteRow | null;
  clienteResumo: ClienteResumo | null;
  // Só `.itens`/`.pedidoTotalizadoGrupos` são lidos aqui — `Pick` em vez do
  // hook inteiro (`UsePedidoItens`) pra permitir montar esse recibo fora do
  // fluxo normal de pedido-form/pedido-geral (ex.: Painel de Pedidos,
  // `app/pedidos.tsx`) sem precisar instanciar `usePedidoItens` inteiro (que
  // carrega muito mais estado — descontos, modais de item, etc. — do que
  // esse componente usa). Pedido explícito do usuário, 2026-07-17.
  it: Pick<UsePedidoItens, "itens" | "pedidoTotalizadoGrupos">;
  // Quando informado, imprime só ESTE item (ticket de cozinha/bar — sem
  // preço, sem forma de pagamento, sem totais), réplica de `Pedido_Geral`
  // com `item <> ""` (FrmManPedBar.frm) — usado pelo botão "Imprimir" de
  // cada linha e pelo disparo automático por Finalidade. Sem `item`,
  // imprime o pedido inteiro (modo já existente).
  item?: ItemPrintData | null;
};

export default function ReciboPedidoModal({ visible, onClose, conn, pedido, cliente, clienteResumo, it, item }: Props) {
  const [empresa, setEmpresa] = useState<Empresa | null>(null);
  const [mensagens, setMensagens] = useState<string[]>([]);
  const [formasPag, setFormasPag] = useState<FormaPagLinha[]>([]);
  const [agrupado, setAgrupado] = useState(true);
  const isItemMode = !!item;

  useEffect(() => {
    if (!visible || !conn) return;
    (async () => {
      const [je, jm, jf] = await Promise.all([
        apiGet(conn, "/api/controle/empresa").catch(() => null),
        apiGet(conn, "/api/controle/mensagens-pdv").catch(() => null),
        !isItemMode && pedido?.pedido
          ? apiGet(conn, `/api/pedidos/${pedido.pedido}/formas-pagamento`).catch(() => null)
          : Promise.resolve(null),
      ]);
      if (je?.success) setEmpresa(je);
      if (jm?.success) setMensagens(jm.linhas || []);
      if (jf?.success) setFormasPag(jf.items || []);
    })();
  }, [visible, conn, pedido?.pedido, isItemMode]);

  if (!pedido) return null;

  const situacaoLabel = pedido.situacao === "A" ? "Orçamento" : "Pedido";
  const enderecoEmpresa = empresa
    ? [empresa.endereco, empresa.numero ? String(empresa.numero) : null, empresa.complemento].filter(Boolean).join(" ")
    : "";
  const cidadeEmpresa = empresa ? [empresa.bairro, empresa.cidade, empresa.uf].filter(Boolean).join(" - ") : "";

  // Sub-Total (preço de tabela, sem desconto) x Desconto — ver bloco
  // "SUB-TOTAL/DESCONTO/TOTAL" mais abaixo pro racional completo.
  const subtotalBruto = it.itens.reduce((s, r) => s + r.qtd * (r.p_normal || r.valor_unitario), 0);
  const descontoTotal = subtotalBruto - pedido.total;

  const buildHtml = (): string => {
    const parts: string[] = [];
    const hr = () => parts.push('<div class="hr"></div>');
    const center = (t: string) => parts.push(`<div class="center">${escHtml(t)}</div>`);
    const bold = (t: string) => parts.push(`<div class="bold">${escHtml(t)}</div>`);
    const line = (t: string) => parts.push(`<div class="mb">${escHtml(t)}</div>`);
    const row = (a: string, b: string) =>
      parts.push(`<div class="row"><span>${escHtml(a)}</span><span>${escHtml(b)}</span></div>`);
    // Linha de item: descrição ocupa a linha INTEIRA (quebra livre,
    // qualquer tamanho), qtd x unit / total ficam numa segunda linha
    // compacta abaixo. Substitui o layout anterior de 3 colunas numa linha
    // só (`row3`) — em papel de 80mm as colunas de qtd/total (que nunca
    // quebram) sobravam quase nenhum espaço pra descrição, quebrando
    // palavra por sílaba/letra. Corrigido a partir de print real da
    // impressora térmica mostrando o problema (2026-07-18).
    const itemRow = (desc: string, qtdUnit: string, total: string) => {
      parts.push(`<div class="mb">${escHtml(desc)}</div>`);
      parts.push(`<div class="row mb"><span>${escHtml(qtdUnit)}</span><span>${escHtml(total)}</span></div>`);
    };

    if (isItemMode) {
      // Ticket de cozinha/bar inteiro em negrito (pedido explícito do
      // usuário, 2026-07-23) — inclusive o nome da empresa, que no modo
      // pedido completo continua só centralizado (`center()`, sem negrito).
      parts.push(`<div class="bold center mb">${escHtml((empresa?.fantasia || empresa?.rz_social || "").toUpperCase())}</div>`);
    } else {
      center((empresa?.fantasia || empresa?.rz_social || "").toUpperCase());
    }
    // Endereço/telefone/CNPJ da empresa só fazem sentido no recibo do
    // cliente — o ticket de cozinha/bar (modo item) é uso interno, esses
    // dados só ocupam espaço à toa (pedido explícito do usuário).
    if (!isItemMode) {
      if (enderecoEmpresa) center(enderecoEmpresa);
      if (cidadeEmpresa) center(`${cidadeEmpresa}${empresa?.cep ? ` CEP: ${empresa.cep}` : ""}`);
      if (empresa?.telefone) {
        center(`Tel: (${empresa.ddd}) ${empresa.telefone}${empresa.celular ? ` / ${empresa.celular}` : ""}`);
      }
      if (empresa?.cgc) center(`CNPJ: ${empresa.cgc}${empresa.inscr_est ? ` IE: ${empresa.inscr_est}` : ""}`);
    }
    hr();
    // Nome do cliente entra na mesma linha do nº do pedido, mesma fonte
    // (pedido explícito do usuário, modelo anexado) — só no modo item;
    // no recibo completo o cliente já aparece em linha própria mais abaixo.
    bold(
      `${situacaoLabel} nº ${pedido.pedido}` +
      (pedido.localizacao_descricao ? `   Local: ${pedido.localizacao_descricao}` : "") +
      (isItemMode && cliente ? `   ${cliente.nome}` : "")
    );
    hr();

    if (isItemMode && item) {
      // Ticket de cozinha/bar — Qtd e Produto em fonte grande (`.huge2`,
      // um pouco menor que a `.huge` anterior — pedido explícito do
      // usuário) pra continuar legível de longe na cozinha, mas sem
      // dominar o ticket inteiro. Atendente e Data/Hora dividem a mesma
      // linha, mesma fonte (antes eram 2 linhas separadas, a de
      // Data/Hora em fonte gigante). A linha "Pedido nº X   Impressão:
      // Y" foi REMOVIDA (pedido explícito do usuário, ver modelo
      // anexado — a mesma informação de nº do pedido já está na linha do
      // cabeçalho, acima).
      bold(
        `Atendente: ${pedido.vendedor_nome}   ` +
        `${formatDateBR(pedido.data)}  ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
      );
      hr();
      parts.push(`<div class="huge2 mb">${escHtml(`QTD: ${fmtNum(item.qtd)}`)}</div>`);
      parts.push(`<div class="huge2 mb">${escHtml(item.descricao)}</div>`);
      if (item.complemento && item.complemento.trim().toUpperCase() !== item.descricao.trim().toUpperCase()) {
        parts.push(`<div class="big mb">${escHtml(item.complemento)}</div>`);
      }
      if (item.comprimento && item.largura) {
        parts.push(`<div class="big mb">${escHtml(`${fmtNum(item.comprimento)} x ${fmtNum(item.largura)} m`)}</div>`);
      }
      hr();
      if (pedido.obs) { bold(`Obs: ${pedido.obs}`); hr(); }
      if (clienteResumo?.endereco || clienteResumo?.telefone) {
        if (clienteResumo?.endereco) bold(clienteResumo.endereco);
        if (clienteResumo?.telefone) bold(`Tel: ${clienteResumo.telefone}`);
      }
      if (pedido.previsao_entrega) {
        hr();
        bold(`Entrega em ${formatDateBR(pedido.previsao_entrega)}${pedido.hora_entrega ? ` às ${pedido.hora_entrega.slice(0, 5)} hs.` : ""}`);
      }
    } else {
      if (agrupado) {
        it.pedidoTotalizadoGrupos.forEach((g) => {
          itemRow(g.descricao, `${fmtNum(g.qtd)} x ${formatBRL(g.qtd ? g.valorTotal / g.qtd : 0)}`, formatBRL(g.valorTotal));
        });
      } else {
        it.itens.forEach((row_) => {
          itemRow(
            row_.descricao
              + (row_.complemento ? ` — ${row_.complemento}` : "")
              // Dimensão m² (Fase B — módulo Metro Quadrado), só quando
              // gravada. Ver PENDENCIAS.md > "Transações" > "Pedido Geral —
              // Metro Quadrado".
              + (row_.comprimento && row_.largura ? ` — ${fmtNum(row_.comprimento)} x ${fmtNum(row_.largura)} m` : "")
              // Agendamento (Fase B — módulo Clínica) — data/hora/profissional
              // por linha, só quando o item de Serviço já foi agendado. Ver
              // PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: Clínica
              // (Agendamento)".
              + (row_.agendamento ? ` — Agendado: ${formatDateBR(row_.agendamento.data)} às ${row_.agendamento.hora_ini} (${row_.agendamento.profissional})` : ""),
            `${fmtNum(row_.qtd)} x ${formatBRL(row_.valor_unitario)}`,
            formatBRL(row_.qtd * row_.valor_unitario)
          );
        });
      }
      hr();
      // Sub-Total/Desconto — réplica do recibo legado VB6 (colado pelo
      // usuário 2026-07-18: "* SUB-TOTAL:" / "* DESCONTO:" / "* TOTAL:"),
      // que detalha o valor bruto e o desconto separados antes do total.
      // Calculado a partir de `p_normal` (preço de tabela, sem desconto)
      // de `it.itens` — sempre a lista crua, independente do toggle
      // "Totalizado" acima (esse resumo é fixo, não segue o agrupamento).
      // Só aparece quando há desconto de fato (evita "Desconto: R$ 0,00"
      // poluindo pedidos sem nenhum desconto lançado).
      if (subtotalBruto > 0 && descontoTotal > 0.005) {
        row("SUB-TOTAL", formatBRL(subtotalBruto));
        row("DESCONTO", formatBRL(descontoTotal));
      }
      row("TOTAL", formatBRL(pedido.total));
      // Divisão da conta pela qtd. de pessoas (Painel de Pedidos, campo
      // "Qtd. Pessoas" do card) — só aparece quando informada. Pedido
      // explícito do usuário, 2026-07-17.
      if (pedido.qtd_pessoas && pedido.qtd_pessoas > 0) {
        row(`Valor p/ pessoa (${pedido.qtd_pessoas})`, formatBRL(pedido.total / pedido.qtd_pessoas));
      }
      hr();
      if (pedido.obs) { line(`Obs: ${pedido.obs}`); hr(); }
      bold("FORMA DE PAGAMENTO");
      if (formasPag.length > 0) {
        formasPag.forEach((f) => row(f.descricao || f.forma_pag, formatBRL(f.valor)));
      } else if (pedido.forma_pag_descricao) {
        row(pedido.forma_pag_descricao, formatBRL(pedido.total));
      } else {
        line("(não definida)");
      }
      hr();
      if (cliente) {
        if (temDocumentoValido(cliente.cgc_cpf)) line(`Doc: ${cliente.cgc_cpf}`);
        line(cliente.nome);
        if (clienteResumo?.endereco) line(clienteResumo.endereco);
        if (clienteResumo?.telefone) line(`Tel: ${clienteResumo.telefone}`);
        hr();
      }
      line(`Vendedor: ${pedido.vendedor_nome}`);
      line(`${formatDateBR(pedido.data)} ${pedido.hora_aberto}`);
    }

    if (mensagens.length > 0) {
      hr();
      mensagens.forEach((m) => center(m));
    }

    return parts.join("\n");
  };

  const handlePrint = () => {
    if (!isWeb) return;
    // Título em branco no modo item: no ticket de cozinha/bar (papel
    // térmico estreito, sem uso de "salvar como PDF") o título só reforça
    // a faixa de cabeçalho que o PRÓPRIO NAVEGADOR imprime em cima da
    // página ("data — título"), fora do nosso controle via CSS — ver
    // "Impressão — cabeçalho do navegador" em CLAUDE.md/PENDENCIAS.md
    // pro que precisa ser desligado manualmente em "Mais definições" >
    // "Cabeçalhos e rodapés" do diálogo de impressão. No modo pedido
    // inteiro o título continua útil (identifica o PDF quando o destino é
    // "Salvar como PDF"), não mudado.
    printHtml(buildHtml(), isItemMode ? "" : "Imprimir Pedido", PAPER_WIDTH_MM);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{isItemMode ? "Imprimir Item" : "Imprimir Pedido"}</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          {!isItemMode ? (
            <TouchableOpacity
              onPress={() => setAgrupado((a) => !a)}
              style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: spacing.sm }}
              testID="pedido-recibo-agrupado"
            >
              <Ionicons name={agrupado ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
              <Text style={{ fontSize: 13, color: colors.onSurface }}>Imprimir Totalizado (agrupa itens repetidos)</Text>
            </TouchableOpacity>
          ) : null}

          <ScrollView style={{ maxHeight: 480 }}>
            <View style={rs.paper}>
              <Text style={isItemMode ? [rs.bold, rs.center] : rs.center}>
                {(empresa?.fantasia || empresa?.rz_social || "").toUpperCase()}
              </Text>
              {!isItemMode && enderecoEmpresa ? <Text style={rs.center}>{enderecoEmpresa}</Text> : null}
              {!isItemMode && cidadeEmpresa ? <Text style={rs.center}>{cidadeEmpresa}{empresa?.cep ? ` CEP: ${empresa.cep}` : ""}</Text> : null}
              {!isItemMode && empresa?.telefone ? (
                <Text style={rs.center}>Tel: ({empresa.ddd}) {empresa.telefone}{empresa.celular ? ` / ${empresa.celular}` : ""}</Text>
              ) : null}
              {!isItemMode && empresa?.cgc ? <Text style={rs.center}>CNPJ: {empresa.cgc}{empresa.inscr_est ? ` IE: ${empresa.inscr_est}` : ""}</Text> : null}

              <View style={rs.hr} />
              {/* Nome do cliente entra na mesma linha do nº do pedido, mesma
                  fonte — só no modo item (pedido explícito do usuário). */}
              <Text style={rs.bold}>
                {situacaoLabel} nº {pedido.pedido}
                {pedido.localizacao_descricao ? `   Local: ${pedido.localizacao_descricao}` : ""}
                {isItemMode && cliente ? `   ${cliente.nome}` : ""}
              </Text>
              <View style={rs.hr} />

              {isItemMode && item ? (
                <>
                  {/* Atendente e Data/Hora na mesma linha, mesma fonte —
                      antes eram 2 linhas separadas (a de Data/Hora em fonte
                      gigante). A linha "Pedido nº X   Impressão: Y" foi
                      REMOVIDA (pedido explícito do usuário, ver modelo
                      anexado — a informação do nº do pedido já está no
                      cabeçalho, acima). */}
                  <Text style={rs.bold}>
                    Atendente: {pedido.vendedor_nome}{"   "}
                    {formatDateBR(pedido.data)}  {new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                  </Text>
                  <View style={rs.hr} />
                  {/* Qtd/Produto em fonte grande (`rs.huge2`, um pouco menor
                      que `rs.huge` — pedido explícito do usuário) pra
                      continuar legível de longe na cozinha. */}
                  <Text style={rs.huge2}>QTD: {fmtNum(item.qtd)}</Text>
                  <Text style={rs.huge2}>{item.descricao}</Text>
                  {item.complemento && item.complemento.trim().toUpperCase() !== item.descricao.trim().toUpperCase() ? (
                    <Text style={rs.itemDesc}>{item.complemento}</Text>
                  ) : null}
                  <View style={rs.hr} />
                  {pedido.obs ? (
                    <>
                      <Text style={rs.bold}>Obs: {pedido.obs}</Text>
                      <View style={rs.hr} />
                    </>
                  ) : null}
                  {clienteResumo?.endereco ? <Text style={rs.bold}>{clienteResumo.endereco}</Text> : null}
                  {clienteResumo?.telefone ? <Text style={rs.bold}>Tel: {clienteResumo.telefone}</Text> : null}
                  {pedido.previsao_entrega ? (
                    <>
                      <View style={rs.hr} />
                      <Text style={rs.bold}>
                        Entrega em {formatDateBR(pedido.previsao_entrega)}{pedido.hora_entrega ? ` às ${pedido.hora_entrega.slice(0, 5)} hs.` : ""}
                      </Text>
                    </>
                  ) : null}
                </>
              ) : (
                <>
                  {/* Descrição na linha inteira + qtd/total numa linha compacta
                      abaixo — mesmo layout do `buildHtml`, ver comentário lá
                      (colunas fixas de qtd/total espremiam a descrição em
                      papel de 80mm real). */}
                  {agrupado
                    ? it.pedidoTotalizadoGrupos.map((g) => (
                        <View key={g.produto} style={{ marginBottom: 4 }}>
                          <Text style={rs.mono}>{g.descricao}</Text>
                          <View style={rs.row}>
                            <Text style={rs.mono}>{fmtNum(g.qtd)} x {formatBRL(g.qtd ? g.valorTotal / g.qtd : 0)}</Text>
                            <Text style={rs.mono}>{formatBRL(g.valorTotal)}</Text>
                          </View>
                        </View>
                      ))
                    : it.itens.map((row) => (
                        <View key={row.codauto} style={{ marginBottom: 4 }}>
                          <Text style={rs.mono}>
                            {row.descricao}{row.complemento ? ` — ${row.complemento}` : ""}
                            {row.agendamento ? ` — Agendado: ${formatDateBR(row.agendamento.data)} às ${row.agendamento.hora_ini} (${row.agendamento.profissional})` : ""}
                          </Text>
                          <View style={rs.row}>
                            <Text style={rs.mono}>{fmtNum(row.qtd)} x {formatBRL(row.valor_unitario)}</Text>
                            <Text style={rs.mono}>{formatBRL(row.qtd * row.valor_unitario)}</Text>
                          </View>
                        </View>
                      ))}

                  <View style={rs.hr} />
                  {subtotalBruto > 0 && descontoTotal > 0.005 ? (
                    <>
                      <View style={rs.row}>
                        <Text style={rs.mono}>SUB-TOTAL</Text>
                        <Text style={rs.mono}>{formatBRL(subtotalBruto)}</Text>
                      </View>
                      <View style={rs.row}>
                        <Text style={rs.mono}>DESCONTO</Text>
                        <Text style={rs.mono}>{formatBRL(descontoTotal)}</Text>
                      </View>
                    </>
                  ) : null}
                  <View style={rs.row}>
                    <Text style={rs.bold}>TOTAL</Text>
                    <Text style={rs.bold}>{formatBRL(pedido.total)}</Text>
                  </View>
                  {pedido.qtd_pessoas && pedido.qtd_pessoas > 0 ? (
                    <View style={rs.row}>
                      <Text style={rs.mono}>Valor p/ pessoa ({pedido.qtd_pessoas})</Text>
                      <Text style={rs.mono}>{formatBRL(pedido.total / pedido.qtd_pessoas)}</Text>
                    </View>
                  ) : null}
                  <View style={rs.hr} />

                  {pedido.obs ? (
                    <>
                      <Text style={rs.mono}>Obs: {pedido.obs}</Text>
                      <View style={rs.hr} />
                    </>
                  ) : null}

                  <Text style={rs.bold}>FORMA DE PAGAMENTO</Text>
                  {formasPag.length > 0 ? (
                    formasPag.map((f) => (
                      <View key={`${f.forma_pag}-${f.valor}`} style={rs.row}>
                        <Text style={rs.mono}>{f.descricao || f.forma_pag}</Text>
                        <Text style={rs.mono}>{formatBRL(f.valor)}</Text>
                      </View>
                    ))
                  ) : pedido.forma_pag_descricao ? (
                    <View style={rs.row}>
                      <Text style={rs.mono}>{pedido.forma_pag_descricao}</Text>
                      <Text style={rs.mono}>{formatBRL(pedido.total)}</Text>
                    </View>
                  ) : (
                    <Text style={rs.mono}>(não definida)</Text>
                  )}
                  <View style={rs.hr} />

                  {cliente ? (
                    <>
                      {temDocumentoValido(cliente.cgc_cpf) ? <Text style={rs.mono}>Doc: {cliente.cgc_cpf}</Text> : null}
                      <Text style={rs.mono}>{cliente.nome}</Text>
                      {clienteResumo?.endereco ? <Text style={rs.mono}>{clienteResumo.endereco}</Text> : null}
                      {clienteResumo?.telefone ? <Text style={rs.mono}>Tel: {clienteResumo.telefone}</Text> : null}
                      <View style={rs.hr} />
                    </>
                  ) : null}

                  <Text style={rs.mono}>Vendedor: {pedido.vendedor_nome}</Text>
                  <Text style={rs.mono}>{formatDateBR(pedido.data)} {pedido.hora_aberto}</Text>
                </>
              )}

              {mensagens.length > 0 ? (
                <>
                  <View style={rs.hr} />
                  {mensagens.map((m, i) => (
                    <Text key={i} style={rs.center}>{m}</Text>
                  ))}
                </>
              ) : null}
            </View>
          </ScrollView>

          <View style={styles.modalBtns}>
            <Pressable onPress={onClose} style={[styles.secondaryBtn, { flex: 1, alignItems: "center" }]} testID="pedido-recibo-fechar">
              <Text style={styles.secondaryBtnText}>Fechar</Text>
            </Pressable>
            <Pressable onPress={handlePrint} style={[styles.primaryBtn, { flex: 1 }]} testID="pedido-recibo-imprimir">
              <Text style={styles.primaryBtnText}>Imprimir</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const rs = StyleSheet.create({
  paper: { backgroundColor: "#fff", padding: spacing.md, borderRadius: radius.sm },
  mono: { fontSize: 12, fontFamily: isWeb ? "monospace" : undefined, color: "#111" },
  bold: { fontSize: 12, fontFamily: isWeb ? "monospace" : undefined, fontWeight: "700", color: "#111" },
  itemDesc: { fontSize: 15, fontFamily: isWeb ? "monospace" : undefined, fontWeight: "700", color: "#111" },
  // Ticket de cozinha/bar (modo item) — Mesa/Data/Hora/Qtd/Produto em fonte
  // bem maior, legível de longe (pedido explícito do usuário, a partir de
  // um exemplo real de cupom anexado).
  huge: { fontSize: 24, fontFamily: isWeb ? "monospace" : undefined, fontWeight: "800", color: "#111", marginBottom: 4 },
  hugeCenter: { fontSize: 24, fontFamily: isWeb ? "monospace" : undefined, fontWeight: "800", color: "#111", textAlign: "center", marginBottom: 4 },
  // Qtd/Produto do ticket de cozinha/bar — um pouco menor que `huge`
  // (pedido explícito do usuário, 2026-07-23), mirror de `.huge2` em
  // printHtml.ts.
  huge2: { fontSize: 18, fontFamily: isWeb ? "monospace" : undefined, fontWeight: "800", color: "#111", marginBottom: 4 },
  center: { fontSize: 12, textAlign: "center", color: "#111" },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  hr: { borderBottomWidth: 1, borderColor: "#999", marginVertical: 6 },
});
