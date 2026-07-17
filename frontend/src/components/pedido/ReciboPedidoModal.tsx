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
  it: UsePedidoItens;
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

  const buildHtml = (): string => {
    const parts: string[] = [];
    const hr = () => parts.push('<div class="hr"></div>');
    const center = (t: string) => parts.push(`<div class="center">${escHtml(t)}</div>`);
    const bold = (t: string) => parts.push(`<div class="bold">${escHtml(t)}</div>`);
    const line = (t: string) => parts.push(`<div class="mb">${escHtml(t)}</div>`);
    const big = (t: string) => parts.push(`<div class="big mb">${escHtml(t)}</div>`);
    const row = (a: string, b: string) =>
      parts.push(`<div class="row"><span>${escHtml(a)}</span><span>${escHtml(b)}</span></div>`);
    // Linha de item: descrição (esquerda) / qtd x unit (meio) / total (direita) —
    // alinhamento justificado nas duas pontas, valor total sempre alinhado à
    // direita da linha, pedido explícito do usuário 2026-07-16.
    const itemRow = (desc: string, qtdUnit: string, total: string) =>
      parts.push(
        `<div class="row3"><span>${escHtml(desc)}</span><span>${escHtml(qtdUnit)}</span><span>${escHtml(total)}</span></div>`
      );

    center((empresa?.fantasia || empresa?.rz_social || "").toUpperCase());
    if (enderecoEmpresa) center(enderecoEmpresa);
    if (cidadeEmpresa) center(`${cidadeEmpresa}${empresa?.cep ? ` CEP: ${empresa.cep}` : ""}`);
    if (empresa?.telefone) {
      center(`Tel: (${empresa.ddd}) ${empresa.telefone}${empresa.celular ? ` / ${empresa.celular}` : ""}`);
    }
    if (empresa?.cgc) center(`CNPJ: ${empresa.cgc}${empresa.inscr_est ? ` IE: ${empresa.inscr_est}` : ""}`);
    hr();
    bold(`${situacaoLabel} nº ${pedido.pedido}${pedido.localizacao_descricao ? `   Local: ${pedido.localizacao_descricao}` : ""}`);
    hr();

    if (isItemMode && item) {
      parts.push(`<div class="big center mb">${escHtml(`${formatDateBR(pedido.data)} ${new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`)}</div>`);
      hr();
      parts.push(`<div class="big mb">${escHtml(item.descricao)}</div>`);
      if (item.complemento && item.complemento.trim().toUpperCase() !== item.descricao.trim().toUpperCase()) {
        parts.push(`<div class="big mb">${escHtml(item.complemento)}</div>`);
      }
      big(`QTD: ${fmtNum(item.qtd)}`);
      hr();
      if (pedido.obs) { line(`Obs: ${pedido.obs}`); hr(); }
      if (cliente) {
        big(cliente.nome);
        if (clienteResumo?.endereco) line(clienteResumo.endereco);
        if (clienteResumo?.telefone) line(`Tel: ${clienteResumo.telefone}`);
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
            row_.descricao + (row_.complemento ? ` — ${row_.complemento}` : ""),
            `${fmtNum(row_.qtd)} x ${formatBRL(row_.valor_unitario)}`,
            formatBRL(row_.qtd * row_.valor_unitario)
          );
        });
      }
      hr();
      row("TOTAL", formatBRL(pedido.total));
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
        if (cliente.cgc_cpf) line(`Doc: ${cliente.cgc_cpf}`);
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
    printHtml(buildHtml(), isItemMode ? "Imprimir Item" : "Imprimir Pedido");
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
              <Text style={rs.center}>{(empresa?.fantasia || empresa?.rz_social || "").toUpperCase()}</Text>
              {enderecoEmpresa ? <Text style={rs.center}>{enderecoEmpresa}</Text> : null}
              {cidadeEmpresa ? <Text style={rs.center}>{cidadeEmpresa}{empresa?.cep ? ` CEP: ${empresa.cep}` : ""}</Text> : null}
              {empresa?.telefone ? (
                <Text style={rs.center}>Tel: ({empresa.ddd}) {empresa.telefone}{empresa.celular ? ` / ${empresa.celular}` : ""}</Text>
              ) : null}
              {empresa?.cgc ? <Text style={rs.center}>CNPJ: {empresa.cgc}{empresa.inscr_est ? ` IE: ${empresa.inscr_est}` : ""}</Text> : null}

              <View style={rs.hr} />
              <Text style={rs.bold}>
                {situacaoLabel} nº {pedido.pedido}{pedido.localizacao_descricao ? `   Local: ${pedido.localizacao_descricao}` : ""}
              </Text>
              <View style={rs.hr} />

              {isItemMode && item ? (
                <>
                  <Text style={rs.dataHora}>{formatDateBR(pedido.data)} {new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}</Text>
                  <View style={rs.hr} />
                  <Text style={rs.itemDesc}>{item.descricao}</Text>
                  {item.complemento && item.complemento.trim().toUpperCase() !== item.descricao.trim().toUpperCase() ? (
                    <Text style={rs.itemDesc}>{item.complemento}</Text>
                  ) : null}
                  <Text style={rs.itemDesc}>QTD: {fmtNum(item.qtd)}</Text>
                  <View style={rs.hr} />
                  {pedido.obs ? (
                    <>
                      <Text style={rs.mono}>Obs: {pedido.obs}</Text>
                      <View style={rs.hr} />
                    </>
                  ) : null}
                  {cliente ? (
                    <>
                      <Text style={rs.itemDesc}>{cliente.nome}</Text>
                      {clienteResumo?.endereco ? <Text style={rs.mono}>{clienteResumo.endereco}</Text> : null}
                      {clienteResumo?.telefone ? <Text style={rs.mono}>Tel: {clienteResumo.telefone}</Text> : null}
                    </>
                  ) : null}
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
                  {agrupado
                    ? it.pedidoTotalizadoGrupos.map((g) => (
                        <View key={g.produto} style={[rs.row, { marginBottom: 4 }]}>
                          <Text style={[rs.mono, rs.rowDesc]}>{g.descricao}</Text>
                          <Text style={[rs.mono, rs.rowQtd]}>
                            {fmtNum(g.qtd)} x {formatBRL(g.qtd ? g.valorTotal / g.qtd : 0)}
                          </Text>
                          <Text style={[rs.mono, rs.rowValue]}>{formatBRL(g.valorTotal)}</Text>
                        </View>
                      ))
                    : it.itens.map((row) => (
                        <View key={row.codauto} style={[rs.row, { marginBottom: 4 }]}>
                          <Text style={[rs.mono, rs.rowDesc]}>{row.descricao}{row.complemento ? ` — ${row.complemento}` : ""}</Text>
                          <Text style={[rs.mono, rs.rowQtd]}>
                            {fmtNum(row.qtd)} x {formatBRL(row.valor_unitario)}
                          </Text>
                          <Text style={[rs.mono, rs.rowValue]}>{formatBRL(row.qtd * row.valor_unitario)}</Text>
                        </View>
                      ))}

                  <View style={rs.hr} />
                  <View style={rs.row}>
                    <Text style={rs.bold}>TOTAL</Text>
                    <Text style={rs.bold}>{formatBRL(pedido.total)}</Text>
                  </View>
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
                      {cliente.cgc_cpf ? <Text style={rs.mono}>Doc: {cliente.cgc_cpf}</Text> : null}
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
  dataHora: { fontSize: 15, fontFamily: isWeb ? "monospace" : undefined, fontWeight: "700", color: "#111", textAlign: "center" },
  center: { fontSize: 12, textAlign: "center", color: "#111" },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  rowDesc: { flexShrink: 1, flexGrow: 1, minWidth: 0 },
  rowQtd: { flexShrink: 0 },
  rowValue: { flexShrink: 0, minWidth: 64, textAlign: "right" },
  hr: { borderBottomWidth: 1, borderColor: "#999", marginVertical: 6 },
});
