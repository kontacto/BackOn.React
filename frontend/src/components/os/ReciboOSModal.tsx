// Modal "Imprimir O.S." — preview de recibo + impressão via iframe oculto
// (ver src/utils/printHtml.ts, mesmo padrão de `pedido/ReciboPedidoModal.tsx`
// — NUNCA o truque de CSS "esconde tudo/mostra só #id", que sai em branco,
// ver CLAUDE.md > "Impressão via iframe, não CSS hide"). Mais simples que o
// do Pedido: sem "Totalizado"/qtd. de pessoas/localização/agendamento
// (conceitos exclusivos do Pedido) — mas com o detalhamento por Situação/
// Destino do item (Cliente/Garantia/Interno/Contrato), que o Pedido não tem.
import { useEffect, useState } from "react";
import { Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL, formatDateBR, fmtNum } from "@/src/utils/format";
import { apiGet } from "@/src/utils/api";
import { printHtml, escHtml } from "@/src/utils/printHtml";
import { Connection } from "@/src/utils/storage/connections";
import { ClienteRow, ClienteResumo } from "@/src/components/pedido/types";
import { styles } from "@/src/components/pedido/styles";
import { OSData, OSItemRow, osSituacaoItemLabel } from "./types";

const isWeb = Platform.OS === "web";
const PAPER_WIDTH_MM = 80;

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
  os: OSData | null;
  cliente: ClienteRow | null;
  clienteResumo: ClienteResumo | null;
  itens: OSItemRow[];
};

export default function ReciboOSModal({ visible, onClose, conn, os, cliente, clienteResumo, itens }: Props) {
  const [empresa, setEmpresa] = useState<Empresa | null>(null);
  const [formasPag, setFormasPag] = useState<FormaPagLinha[]>([]);

  useEffect(() => {
    if (!visible || !conn) return;
    (async () => {
      const [je, jf] = await Promise.all([
        apiGet(conn, "/api/controle/empresa").catch(() => null),
        os?.codigo ? apiGet(conn, `/api/os/${os.codigo}/formas-pagamento`).catch(() => null) : Promise.resolve(null),
      ]);
      if (je?.success) setEmpresa(je);
      if (jf?.success) setFormasPag(jf.items || []);
    })();
  }, [visible, conn, os?.codigo]);

  if (!os) return null;

  const enderecoEmpresa = empresa
    ? [empresa.endereco, empresa.numero ? String(empresa.numero) : null, empresa.complemento].filter(Boolean).join(" ")
    : "";
  const cidadeEmpresa = empresa ? [empresa.bairro, empresa.cidade, empresa.uf].filter(Boolean).join(" - ") : "";

  const clientePaga = itens.filter((i) => (i.situacao ?? 0) === 0);
  const outrasSit = itens.filter((i) => (i.situacao ?? 0) !== 0);
  const totalClientePaga = clientePaga.reduce((s, i) => s + i.qtd * i.valor_unitario, 0);
  const totalOutras = outrasSit.reduce((s, i) => s + i.qtd * i.valor_unitario, 0);

  const buildHtml = (): string => {
    const parts: string[] = [];
    const hr = () => parts.push('<div class="hr"></div>');
    const center = (t: string) => parts.push(`<div class="center">${escHtml(t)}</div>`);
    const bold = (t: string) => parts.push(`<div class="bold">${escHtml(t)}</div>`);
    const line = (t: string) => parts.push(`<div class="mb">${escHtml(t)}</div>`);
    const row = (a: string, b: string) =>
      parts.push(`<div class="row"><span>${escHtml(a)}</span><span>${escHtml(b)}</span></div>`);
    const itemRow = (desc: string, qtdUnit: string, total: string) => {
      parts.push(`<div class="mb">${escHtml(desc)}</div>`);
      parts.push(`<div class="row mb"><span>${escHtml(qtdUnit)}</span><span>${escHtml(total)}</span></div>`);
    };

    center((empresa?.fantasia || empresa?.rz_social || "").toUpperCase());
    if (enderecoEmpresa) center(enderecoEmpresa);
    if (cidadeEmpresa) center(`${cidadeEmpresa}${empresa?.cep ? ` CEP: ${empresa.cep}` : ""}`);
    if (empresa?.telefone) center(`Tel: (${empresa.ddd}) ${empresa.telefone}${empresa.celular ? ` / ${empresa.celular}` : ""}`);
    if (empresa?.cgc) center(`CNPJ: ${empresa.cgc}${empresa.inscr_est ? ` IE: ${empresa.inscr_est}` : ""}`);
    hr();
    bold(`O.S. nº ${os.codigo}`);
    hr();

    // Dados do veículo (O.S. Oficina) — gap confirmado 2026-08-26 contra
    // modelo real de impressão do legado (RJ PNEUS): mostra Placa/Marca
    // antes da lista de serviços. Só aparece quando a O.S. tem placa
    // preenchida (critério já usado no resto do projeto pra distinguir
    // Oficina de Assistência Técnica nesta mesma tela compartilhada).
    if (os.placa) {
      line("Dados do veículo:");
      line(`Placa: ${os.placa}`);
      if (os.marca || os.modelo) line(`Marca: ${[os.marca, os.modelo].filter(Boolean).join(" / ")}`);
      hr();
    }

    itens.forEach((it) => {
      itemRow(
        it.descricao + (it.complemento ? ` — ${it.complemento}` : "") + ` [${osSituacaoItemLabel(it.situacao ?? 0)}]`,
        `${fmtNum(it.qtd)} x ${formatBRL(it.valor_unitario)}`,
        formatBRL(it.qtd * it.valor_unitario)
      );
    });
    hr();
    row("Serviços + Produtos", formatBRL(totalClientePaga));
    if (totalOutras > 0) row("Garantia / Interno / Contrato", formatBRL(totalOutras));
    row("TOTAL", formatBRL(os.total));
    hr();
    if (os.obs) { line(`Obs: ${os.obs}`); hr(); }
    if (os.resumo) { line(`Serviço Executado: ${os.resumo}`); hr(); }
    bold("FORMA DE PAGAMENTO");
    if (formasPag.length > 0) {
      formasPag.forEach((f) => row(f.descricao || f.forma_pag, formatBRL(f.valor)));
    } else if (os.forma_pagamento_descricao) {
      row(os.forma_pagamento_descricao, formatBRL(os.total));
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
    line(`Atendente: ${os.atendente_nome}`);
    line(`${formatDateBR(os.data)} ${os.hora}`);

    return parts.join("\n");
  };

  const handlePrint = () => {
    if (!isWeb) return;
    printHtml(buildHtml(), "Imprimir O.S.", PAPER_WIDTH_MM);
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Imprimir O.S.</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <ScrollView style={{ maxHeight: 480 }}>
            <View style={rs.paper}>
              <Text style={rs.center}>{(empresa?.fantasia || empresa?.rz_social || "").toUpperCase()}</Text>
              {enderecoEmpresa ? <Text style={rs.center}>{enderecoEmpresa}</Text> : null}
              {cidadeEmpresa ? <Text style={rs.center}>{cidadeEmpresa}{empresa?.cep ? ` CEP: ${empresa.cep}` : ""}</Text> : null}
              {empresa?.telefone ? <Text style={rs.center}>Tel: ({empresa.ddd}) {empresa.telefone}{empresa.celular ? ` / ${empresa.celular}` : ""}</Text> : null}
              {empresa?.cgc ? <Text style={rs.center}>CNPJ: {empresa.cgc}{empresa.inscr_est ? ` IE: ${empresa.inscr_est}` : ""}</Text> : null}
              <View style={rs.hr} />
              <Text style={rs.bold}>O.S. nº {os.codigo}</Text>
              <View style={rs.hr} />

              {os.placa ? (
                <>
                  <Text style={rs.mono}>Dados do veículo:</Text>
                  <Text style={rs.mono}>Placa: {os.placa}</Text>
                  {os.marca || os.modelo ? (
                    <Text style={rs.mono}>Marca: {[os.marca, os.modelo].filter(Boolean).join(" / ")}</Text>
                  ) : null}
                  <View style={rs.hr} />
                </>
              ) : null}

              {itens.map((it) => (
                <View key={it.cod_os_prod} style={{ marginBottom: 4 }}>
                  <Text style={rs.mono}>
                    {it.descricao}{it.complemento ? ` — ${it.complemento}` : ""} [{osSituacaoItemLabel(it.situacao ?? 0)}]
                  </Text>
                  <View style={rs.row}>
                    <Text style={rs.mono}>{fmtNum(it.qtd)} x {formatBRL(it.valor_unitario)}</Text>
                    <Text style={rs.mono}>{formatBRL(it.qtd * it.valor_unitario)}</Text>
                  </View>
                </View>
              ))}
              <View style={rs.hr} />
              <View style={rs.row}>
                <Text style={rs.mono}>Serviços + Produtos</Text>
                <Text style={rs.mono}>{formatBRL(totalClientePaga)}</Text>
              </View>
              {totalOutras > 0 ? (
                <View style={rs.row}>
                  <Text style={rs.mono}>Garantia / Interno / Contrato</Text>
                  <Text style={rs.mono}>{formatBRL(totalOutras)}</Text>
                </View>
              ) : null}
              <View style={rs.row}>
                <Text style={rs.bold}>TOTAL</Text>
                <Text style={rs.bold}>{formatBRL(os.total)}</Text>
              </View>
              <View style={rs.hr} />

              {os.obs ? (<><Text style={rs.mono}>Obs: {os.obs}</Text><View style={rs.hr} /></>) : null}
              {os.resumo ? (<><Text style={rs.mono}>Serviço Executado: {os.resumo}</Text><View style={rs.hr} /></>) : null}

              <Text style={rs.bold}>FORMA DE PAGAMENTO</Text>
              {formasPag.length > 0 ? (
                formasPag.map((f) => (
                  <View key={`${f.forma_pag}-${f.valor}`} style={rs.row}>
                    <Text style={rs.mono}>{f.descricao || f.forma_pag}</Text>
                    <Text style={rs.mono}>{formatBRL(f.valor)}</Text>
                  </View>
                ))
              ) : os.forma_pagamento_descricao ? (
                <View style={rs.row}>
                  <Text style={rs.mono}>{os.forma_pagamento_descricao}</Text>
                  <Text style={rs.mono}>{formatBRL(os.total)}</Text>
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
              <Text style={rs.mono}>Atendente: {os.atendente_nome}</Text>
              <Text style={rs.mono}>{formatDateBR(os.data)} {os.hora}</Text>
            </View>
          </ScrollView>

          <View style={styles.modalBtns}>
            <Pressable onPress={onClose} style={[styles.secondaryBtn, { flex: 1, alignItems: "center" }]} testID="os-recibo-fechar">
              <Text style={styles.secondaryBtnText}>Fechar</Text>
            </Pressable>
            <Pressable onPress={handlePrint} style={[styles.primaryBtn, { flex: 1 }]} testID="os-recibo-imprimir">
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
  center: { fontSize: 12, textAlign: "center", color: "#111" },
  row: { flexDirection: "row", justifyContent: "space-between", gap: 8 },
  hr: { borderBottomWidth: 1, borderColor: "#999", marginVertical: 6 },
});
