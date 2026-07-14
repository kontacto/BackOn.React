import React, { useState } from "react";
import {
  ActivityIndicator, Alert, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import DateField from "@/src/components/DateField";
import {
  useControleSistemaForm, ControleForm, CfopIcmsPar,
} from "@/src/hooks/useControleSistemaForm";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

// Cadastro/Configurações > Geral > Controle do Sistema (tabelas `controle` +
// `controle_aux`, linha única — mono-empresa por ora). Legado: FrmGerCon.frm
// ("Dados para controle"), versão mestra em
// `C:\Desenv\VB6\Diario Access-SQL\SQLSERVER\Geral\FrmGerCon.frm` — ver "Legacy
// VB6 Source Reference" no CLAUDE.md. Mapeamento campo→coluna completo em
// `backend/services/controle_sistema_service.py`.
//
// A aba "Kontacto" do legado (ferramenta interna de suporte/revenda) não entra
// aqui — só as 7 abas de configuração de negócio. `controle_aux.baixa_pedido_compra`
// também não entra (bug confirmado do legado: nunca teve efeito em produção).
//
// Achados de rótulo errado no legado, corrigidos aqui: `controle_aux.Regime_Trib`
// (rotulado "Regime Tributação Municipal" no legado — é na verdade o CRT, Código
// de Regime Tributário nacional do Simples Nacional).

type TabKey = "empresarial" | "movimentacoes" | "diversos" | "fiscal" | "outros" | "financeiro" | "contratos" | "kontacto";
// `comando` bate com o botão cadastrado em `permissoes_service.CTRL_SISTEMA`
// (um por aba) — controla quais abas cada grupo de usuário enxerga, não só o
// acesso à tela como um todo.
const TABS: { key: TabKey; label: string; comando: string }[] = [
  { key: "empresarial", label: "Empresarial", comando: "EMPRESARIAL" },
  { key: "movimentacoes", label: "Movimentações", comando: "MOVIMENTACOES" },
  { key: "diversos", label: "Diversos", comando: "DIVERSOS" },
  { key: "fiscal", label: "Fiscal", comando: "FISCAL" },
  { key: "outros", label: "Outros", comando: "OUTROS" },
  { key: "financeiro", label: "Financeiro", comando: "FINANCEIRO" },
  { key: "contratos", label: "Contratos", comando: "CONTRATOS" },
];
// Aba "Kontacto" — pedido explícito do usuário: só o usuário Master vê essa
// aba (mesmo critério de acesso já usado no legado, onde ela ficava atrás de
// um desbloqueio por senha oculta). Fica fora do array `TABS` acima (que
// alimenta a barra de abas incondicionalmente) e é adicionada condicionalmente
// no render.
const TAB_KONTACTO: { key: TabKey; label: string; comando: string } = { key: "kontacto", label: "Kontacto", comando: "" };

const UF_OPTS: SelectOption[] = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
  "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
].map((uf) => ({ value: uf, label: uf }));

const TIPO_CONTROLE_OPTS: SelectOption[] = [
  { value: "0", label: "Revenda" },
  { value: "1", label: "Fabricante" },
  { value: "2", label: "Distribuidor" },
  { value: "3", label: "Outras" },
];

type FieldProps = { form: ControleForm; setField: (k: string, v: string | boolean) => void };

// Componentes de campo definidos FORA da tela (nível de módulo) — mesmo padrão
// já usado em `taxas.tsx`: se ficassem dentro do corpo do componente, cada
// re-render criaria uma nova referência de função por campo, e o React
// desmontaria/remontaria toda a subárvore a cada tecla digitada (perde foco).
function Txt({ form, setField, campo, label, placeholder, maxLength, keyboardType, disabled = false }: FieldProps & {
  campo: string; label: string; placeholder?: string; maxLength?: number;
  keyboardType?: "default" | "number-pad" | "email-address"; disabled?: boolean;
}) {
  return (
    <View style={styles.colThird}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={String(form[campo] ?? "")}
        onChangeText={(v) => setField(campo, v)}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={[styles.input, disabled && styles.inputDisabled]}
        maxLength={maxLength}
        keyboardType={keyboardType}
        editable={!disabled}
        testID={`ctrl-${campo}`}
      />
    </View>
  );
}

function Num({ form, setField, campo, label, decimais = 2, placeholder, disabled = false }: FieldProps & {
  campo: string; label: string; decimais?: number; placeholder?: string; disabled?: boolean;
}) {
  return (
    <View style={styles.colThird}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={String(form[campo] ?? "")}
        onChangeText={(v) => setField(campo, v.replace(/[^0-9,.-]/g, ""))}
        keyboardType="decimal-pad"
        placeholder={placeholder ?? (decimais === 4 ? "0,0000" : "0,00")}
        placeholderTextColor={colors.muted}
        editable={!disabled}
        style={[styles.input, disabled && styles.inputDisabled]}
        testID={`ctrl-${campo}`}
      />
    </View>
  );
}

function Chk({ form, setField, campo, label }: FieldProps & { campo: string; label: string }) {
  return (
    <View style={styles.switchRow}>
      <Switch value={!!form[campo]} onValueChange={(v) => setField(campo, v)} testID={`ctrl-${campo}-switch`} />
      <Text style={styles.switchLabel}>{label}</Text>
    </View>
  );
}

function SectionTitle({ children }: { children: string }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}
function SubSectionTitle({ children }: { children: string }) {
  return <Text style={styles.subSectionTitle}>{children}</Text>;
}

type FormApi = ReturnType<typeof useControleSistemaForm>;

// Mini-CRUD "Outras Séries NFe" (tabela `controle_nota_fiscal`) — mesmo padrão
// de lista+form inline já usado nas telas de Tabelas Auxiliares. Componente
// de módulo (não inline) pelo mesmo motivo de Txt/Num/Chk acima.
function SeriesNfGrid({ f, canSave }: { f: FormApi; canSave: boolean }) {
  const [serie, setSerie] = useState("");
  const [numero, setNumero] = useState("");
  const add = async () => {
    if (!serie.trim()) return;
    const ok = await f.saveSerieNf(serie.trim(), parseInt(numero, 10) || 0);
    if (ok) { setSerie(""); setNumero(""); }
  };
  return (
    <View>
      {f.seriesNf.map((s) => (
        <View key={s.serie_nf} style={styles.gridRow} testID={`ctrl-serie-${s.serie_nf}`}>
          <Text style={styles.gridRowText}>Série {s.serie_nf} — Número {s.numero_nf}</Text>
          {canSave ? (
            <Pressable onPress={() => f.deleteSerieNf(s.serie_nf)} hitSlop={8}>
              <Ionicons name="trash-outline" size={18} color={colors.error} />
            </Pressable>
          ) : null}
        </View>
      ))}
      {canSave ? (
        <View style={styles.rowFields}>
          <View style={styles.colThird}>
            <Text style={styles.label}>Número:</Text>
            <TextInput value={numero} onChangeText={(v) => setNumero(v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} testID="ctrl-serie-numero" />
          </View>
          <View style={styles.colThird}>
            <Text style={styles.label}>Série:</Text>
            <TextInput value={serie} onChangeText={setSerie} style={styles.input} testID="ctrl-serie-serie" />
          </View>
          <View style={[styles.colThird, { justifyContent: "flex-end" }]}>
            <Pressable onPress={add} style={styles.secondaryBtn} testID="ctrl-serie-gravar">
              <Text style={styles.secondaryBtnText}>Gravar</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

// Mini-CRUD "Horário de Fechamento dos Turnos" (tabela `controle_turno_horario`).
function TurnoGrid({ f, canSave }: { f: FormApi; canSave: boolean }) {
  const [turno, setTurno] = useState("");
  const [horaFim, setHoraFim] = useState("");
  const add = async () => {
    if (!turno.trim() || !horaFim.trim()) return;
    const ok = await f.saveTurnoHorario(parseInt(turno, 10) || 0, horaFim.trim());
    if (ok) { setTurno(""); setHoraFim(""); }
  };
  return (
    <View>
      {f.turnoHorario.map((t) => (
        <View key={t.turno} style={styles.gridRow} testID={`ctrl-turno-${t.turno}`}>
          <Text style={styles.gridRowText}>Turno {t.turno} — fecha às {t.hora_fim} (abre {t.hora_inicio})</Text>
          {canSave ? (
            <Pressable onPress={() => f.deleteTurnoHorario(t.turno)} hitSlop={8}>
              <Ionicons name="trash-outline" size={18} color={colors.error} />
            </Pressable>
          ) : null}
        </View>
      ))}
      {canSave ? (
        <View style={styles.rowFields}>
          <View style={styles.colThird}>
            <Text style={styles.label}>Turno:</Text>
            <TextInput value={turno} onChangeText={(v) => setTurno(v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} testID="ctrl-turno-numero" />
          </View>
          <View style={styles.colThird}>
            <Text style={styles.label}>Hora (HH:MM):</Text>
            <TextInput value={horaFim} onChangeText={setHoraFim} placeholder="23:45" placeholderTextColor={colors.muted} style={styles.input} testID="ctrl-turno-hora" />
          </View>
          <View style={[styles.colThird, { justifyContent: "flex-end" }]}>
            <Pressable onPress={add} style={styles.secondaryBtn} testID="ctrl-turno-gravar">
              <Text style={styles.secondaryBtnText}>Gravar</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

// Mini-CRUD "Certificado Digital" (tabela `certificado_digital`) — upload real
// (.pfx + senha), parse feito no backend com a lib `cryptography`. Web-only
// (a tela inteira já é web-only): usa <input type="file"> nativo do browser
// em vez de um picker nativo, mesmo raciocínio já usado em `DateField.tsx`
// pra não puxar dependência nova só pra mobile.
function CertificadoGrid({ f, canSave }: { f: FormApi; canSave: boolean }) {
  const [senha, setSenha] = useState("");
  const [tipo, setTipo] = useState("A1");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const fb = useFeedback();

  const upload = async () => {
    if (!arquivo) { fb.showWarning("Selecione o arquivo .pfx."); return; }
    const ok = await f.uploadCertificado(arquivo, arquivo.name, senha, tipo);
    if (ok) { setSenha(""); setArquivo(null); }
  };

  return (
    <View>
      {f.certificados.map((c) => (
        <View key={c.sequencia} style={styles.gridRow} testID={`ctrl-cert-${c.sequencia}`}>
          <Text style={styles.gridRowText}>
            {c.tipo_certificado || "A1"} — válido {c.data_inicio} a {c.data_fim}
            {c.cnpj_certificado ? ` — CNPJ ${c.cnpj_certificado}` : ""}
          </Text>
          {canSave ? (
            <Pressable onPress={() => f.deleteCertificado(c.sequencia)} hitSlop={8}>
              <Ionicons name="trash-outline" size={18} color={colors.error} />
            </Pressable>
          ) : null}
        </View>
      ))}
      {canSave ? (
        <View style={styles.rowFields}>
          <View style={styles.colThird}>
            <Text style={styles.label}>Arquivo (.pfx)</Text>
            {Platform.OS === "web" ? (
              <input
                type="file" accept=".pfx,.p12"
                onChange={(e) => setArquivo((e.target as HTMLInputElement).files?.[0] || null)}
                style={{
                  height: 36, boxSizing: "border-box", padding: "0 8px", fontSize: 13,
                  border: `1px solid ${colors.border}`, borderRadius: radius.sm,
                  backgroundColor: colors.surface, color: colors.onSurface,
                }}
              />
            ) : null}
          </View>
          <Txt form={{ senha } as ControleForm} setField={(_k, v) => setSenha(String(v))} campo="senha" label="Senha" />
          <View style={[styles.colThird, { justifyContent: "flex-end" }]}>
            <Pressable onPress={upload} style={styles.secondaryBtn} testID="ctrl-cert-upload">
              <Text style={styles.secondaryBtnText}>Cadastrar Certificado (A1)</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

type ModalContentProps = { f: FormApi; canSave: boolean; onClose: () => void };

// Modais da aba Outros — layout original do legado tinha essas 5 telas como
// botões separados (`FrmConEm_.frm`, `FrmDadCEP.frm`, `FrmIntTray.frm`,
// `FrmCadImp.frm`, `FrmConNDV.frm`/Form8, todos achados na pasta
// `SQLSERVER\Kontacto\` do legado). Email/CEP/Tray reaproveitam campos que já
// fazem parte do form geral (`controle_aux`) — o "Gravar" desses 3 modais
// simplesmente chama `f.save()` (grava a tela toda) e fecha o modal; não têm
// endpoint dedicado como Impressora/Remessa (que são tabelas próprias).

function EmailModalContent({ f, canSave, onClose }: ModalContentProps) {
  const salvar = async () => { const ok = await f.save(); if (ok) onClose(); };
  return (
    <View>
      <Text style={styles.modalTitle}>Configuração de Emails...</Text>
      <Chk form={f.form} setField={f.setField} campo="protocolo_tls_email" label="Usa TLS 1.2" />
      <SubSectionTitle>Email Principal (XML e Danfe de NFe/NFCe)</SubSectionTitle>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="e_mail_rel" label="Email" keyboardType="email-address" />
        <Txt form={f.form} setField={f.setField} campo="smtp_rel" label="Smtp" />
        <Num form={f.form} setField={f.setField} campo="porta_smtp_rel" label="Porta SMTP" decimais={0} />
      </View>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="login_rel" label="Login" />
        <Txt form={f.form} setField={f.setField} campo="senha_rel" label="Senha" />
        <Chk form={f.form} setField={f.setField} campo="ssl_rel" label="Requer SSL" />
      </View>
      <SubSectionTitle>Email de Cobrança</SubSectionTitle>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="e_mail_COBRANCA" label="Email" keyboardType="email-address" />
        <Txt form={f.form} setField={f.setField} campo="ident_COBRANCA" label="Identificação Remetente" />
      </View>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="smtp_COBRANCA" label="Smtp" />
        <Num form={f.form} setField={f.setField} campo="porta_smtp_COBRANCA" label="Porta SMTP" decimais={0} />
        <Txt form={f.form} setField={f.setField} campo="login_COBRANCA" label="Login" />
      </View>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="senha_COBRANCA" label="Senha" />
        <Chk form={f.form} setField={f.setField} campo="ssl_COBRANCA" label="Requer SSL" />
      </View>
      <SubSectionTitle>Email de Contratos</SubSectionTitle>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="e_mail_contrato" label="Email" keyboardType="email-address" />
        <Txt form={f.form} setField={f.setField} campo="ident_contrato" label="Identificação Remetente" />
      </View>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="smtp_contrato" label="Smtp" />
        <Num form={f.form} setField={f.setField} campo="porta_smtp_contrato" label="Porta SMTP" decimais={0} />
        <Txt form={f.form} setField={f.setField} campo="login_contrato" label="Login" />
      </View>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="senha_contrato" label="Senha" />
        <Chk form={f.form} setField={f.setField} campo="ssl_contrato" label="Requer SSL" />
        <Txt form={f.form} setField={f.setField} campo="identificacao_remetente_contrato" label="Identificação Remetente (adicional)" />
      </View>
      <View style={styles.rowFields}>
        {canSave ? (
          <Pressable onPress={salvar} style={styles.secondaryBtn} testID="ctrl-email-gravar">
            <Text style={styles.secondaryBtnText}>Gravar</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={onClose} style={styles.secondaryBtn} testID="ctrl-email-sair">
          <Text style={styles.secondaryBtnText}>Sair</Text>
        </Pressable>
      </View>
    </View>
  );
}

function CepModalContent({ f, canSave, onClose }: ModalContentProps) {
  const salvar = async () => { const ok = await f.save(); if (ok) onClose(); };
  return (
    <View>
      <Text style={styles.modalTitle}>Consulta CEP</Text>
      <Chk form={f.form} setField={f.setField} campo="CEP_CORREIOS" label="Consulta na API Correios" />
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="CEP_USUARIO" label="Usuário" />
        <Txt form={f.form} setField={f.setField} campo="CEP_CONTRATO" label="Contrato" />
      </View>
      <Txt form={f.form} setField={f.setField} campo="CEP_SENHA" label="Senha" />
      <Txt form={f.form} setField={f.setField} campo="CEP_URL_TOKEN" label="URL Token" />
      <Txt form={f.form} setField={f.setField} campo="CEP_URL_CEP" label="URL Consulta por CEP" />
      <Txt form={f.form} setField={f.setField} campo="CEP_URL_LOGRADOURO" label="URL Consulta por logradouro" />
      <Chk form={f.form} setField={f.setField} campo="CEP_GUIACEP" label="Consulta na API GuiaCEP" />
      <View style={styles.rowFields}>
        {canSave ? (
          <Pressable onPress={salvar} style={styles.secondaryBtn} testID="ctrl-cep-gravar">
            <Text style={styles.secondaryBtnText}>Gravar</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={onClose} style={styles.secondaryBtn} testID="ctrl-cep-sair">
          <Text style={styles.secondaryBtnText}>Sair</Text>
        </Pressable>
      </View>
    </View>
  );
}

function TrayModalContent({ f, canSave, onClose }: ModalContentProps) {
  const salvar = async () => { const ok = await f.save(); if (ok) onClose(); };
  return (
    <View>
      <Text style={styles.modalTitle}>Integração Tray</Text>
      <Text style={styles.helperText}>
        Só os campos de credencial/ativação — sincronização de pedidos do site e armazenamento em nuvem (Azure/S3)
        ficam de fora: não existe motor de sincronização Tray implementado neste app pra consumir esses valores.
      </Text>
      <Chk form={f.form} setField={f.setField} campo="integracao_tray" label="Integra com a Tray" />
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="TRAY_ID_LOJA" label="ID da Loja" />
        <Txt form={f.form} setField={f.setField} campo="TRAY_url_api" label="URL Api" />
      </View>
      <View style={styles.rowFields}>
        <Txt form={f.form} setField={f.setField} campo="TRAY_Consumer_Key" label="Consumer Key" />
        <Txt form={f.form} setField={f.setField} campo="TRAY_Consumer_Secret" label="Consumer Secret" />
      </View>
      <Txt form={f.form} setField={f.setField} campo="TRAY_code" label="Code" />
      <View style={styles.rowFields}>
        {canSave ? (
          <Pressable onPress={salvar} style={styles.secondaryBtn} testID="ctrl-tray-gravar">
            <Text style={styles.secondaryBtnText}>Gravar</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={onClose} style={styles.secondaryBtn} testID="ctrl-tray-sair">
          <Text style={styles.secondaryBtnText}>Sair</Text>
        </Pressable>
      </View>
    </View>
  );
}

function ImpressoraModalContent({ f, canSave, onClose }: ModalContentProps) {
  const [computador, setComputador] = useState("");
  const [tipo, setTipo] = useState<string | null>(null);
  const [impressora, setImpressora] = useState("");
  const [automatica, setAutomatica] = useState(false);
  const tipoOpts: SelectOption[] = f.tipoPecaOptions.map((i) => ({ value: i.codigo, label: i.descricao }));

  const gravar = async () => {
    if (!computador.trim() || tipo === null || !impressora.trim()) return;
    const ok = await f.saveDirecionamentoImpressora(computador.trim(), parseInt(tipo, 10), impressora.trim(), automatica);
    if (ok) { setImpressora(""); setAutomatica(false); }
  };

  return (
    <View>
      <Text style={styles.modalTitle}>Direcionamento de Impressão por grupo</Text>
      {f.direcionamentoImpressora.map((it) => (
        <View key={it.codigo} style={styles.gridRow} testID={`ctrl-impr-${it.codigo}`}>
          <Text style={styles.gridRowText}>
            {it.computador} — tipo {it.tipo} — {it.impressora}{it.automatica ? " (automática)" : ""}
          </Text>
          {canSave ? (
            <Pressable onPress={() => f.deleteDirecionamentoImpressora(it.codigo)} hitSlop={8}>
              <Ionicons name="trash-outline" size={18} color={colors.error} />
            </Pressable>
          ) : null}
        </View>
      ))}
      {canSave ? (
        <>
          <View style={styles.rowFields}>
            <View style={styles.colThird}>
              <Text style={styles.label}>Nome do Computador</Text>
              <TextInput value={computador} onChangeText={setComputador} style={styles.input} testID="ctrl-impr-computador" />
            </View>
            <View style={styles.colThird}>
              <Text style={styles.label}>Tipo</Text>
              <SelectField value={tipo} onChange={(v) => setTipo(v != null ? String(v) : null)} options={tipoOpts} compactWeb testID="ctrl-impr-tipo" modalTitle="Tipo" />
            </View>
          </View>
          <View style={styles.rowFields}>
            <View style={styles.colThird}>
              <Text style={styles.label}>Impressora</Text>
              <TextInput value={impressora} onChangeText={setImpressora} style={styles.input} testID="ctrl-impr-nome" />
            </View>
          </View>
          <Chk form={{ automatica } as ControleForm} setField={() => setAutomatica((v) => !v)} campo="automatica" label="Impressão Automática" />
        </>
      ) : null}
      <View style={styles.rowFields}>
        {canSave ? (
          <Pressable onPress={gravar} style={styles.secondaryBtn} testID="ctrl-impr-gravar">
            <Text style={styles.secondaryBtnText}>Gravar</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={onClose} style={styles.secondaryBtn} testID="ctrl-impr-sair">
          <Text style={styles.secondaryBtnText}>Sair</Text>
        </Pressable>
      </View>
    </View>
  );
}

function RemessaModalContent({ f, canSave, onClose }: ModalContentProps) {
  const [tipoMov, setTipoMov] = useState(f.simplesRemessa.tipo_mov);
  const [dentro, setDentro] = useState<CfopIcmsPar[]>(() => {
    const base = [...f.simplesRemessa.dentro];
    while (base.length < 4) base.push({ cfop: "", cod_icms: "" });
    return base.slice(0, 4);
  });
  const [fora, setFora] = useState<CfopIcmsPar[]>(() => {
    const base = [...f.simplesRemessa.fora];
    while (base.length < 4) base.push({ cfop: "", cod_icms: "" });
    return base.slice(0, 4);
  });
  const tipoMovOpts: SelectOption[] = f.tipoMovOptions.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }));

  const setPar = (grupo: CfopIcmsPar[], setGrupo: (v: CfopIcmsPar[]) => void, idx: number, campo: "cfop" | "cod_icms", valor: string) => {
    const copia = [...grupo];
    copia[idx] = { ...copia[idx], [campo]: valor };
    setGrupo(copia);
  };

  const gravar = async () => {
    if (!tipoMov) return;
    const ok = await f.saveSimplesRemessa(tipoMov, dentro, fora);
    if (ok) onClose();
  };

  return (
    <View>
      <Text style={styles.modalTitle}>NFe de Simples Remessa dos DAV's</Text>
      <Text style={styles.label}>Tipo de Movimentação</Text>
      <SelectField value={tipoMov || ""} onChange={(v) => setTipoMov(v ? String(v) : "")} options={tipoMovOpts} allowClear compactWeb testID="ctrl-remessa-tipo-mov" modalTitle="Tipo de Movimentação" />
      <View style={styles.rowFields}>
        <View style={styles.colThird}>
          <SubSectionTitle>{`Dentro do Estado (UF ${f.simplesRemessa.uf || "—"})`}</SubSectionTitle>
          {dentro.map((par, idx) => (
            <View key={idx} style={styles.rowFields}>
              <View style={styles.colThird}>
                <Text style={styles.label}>Cfop</Text>
                <TextInput value={par.cfop} onChangeText={(v) => setPar(dentro, setDentro, idx, "cfop", v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" maxLength={4} style={styles.input} testID={`ctrl-remessa-dentro-cfop-${idx}`} />
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>Cod Icms</Text>
                <TextInput value={par.cod_icms} onChangeText={(v) => setPar(dentro, setDentro, idx, "cod_icms", v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" maxLength={2} style={styles.input} testID={`ctrl-remessa-dentro-icms-${idx}`} />
              </View>
            </View>
          ))}
        </View>
        <View style={styles.colThird}>
          <SubSectionTitle>Fora do Estado</SubSectionTitle>
          {fora.map((par, idx) => (
            <View key={idx} style={styles.rowFields}>
              <View style={styles.colThird}>
                <Text style={styles.label}>Cfop</Text>
                <TextInput value={par.cfop} onChangeText={(v) => setPar(fora, setFora, idx, "cfop", v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" maxLength={4} style={styles.input} testID={`ctrl-remessa-fora-cfop-${idx}`} />
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>Cod Icms</Text>
                <TextInput value={par.cod_icms} onChangeText={(v) => setPar(fora, setFora, idx, "cod_icms", v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" maxLength={2} style={styles.input} testID={`ctrl-remessa-fora-icms-${idx}`} />
              </View>
            </View>
          ))}
        </View>
      </View>
      <View style={styles.rowFields}>
        {canSave ? (
          <Pressable onPress={gravar} style={styles.secondaryBtn} testID="ctrl-remessa-gravar">
            <Text style={styles.secondaryBtnText}>Gravar</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={onClose} style={styles.secondaryBtn} testID="ctrl-remessa-sair">
          <Text style={styles.secondaryBtnText}>Sair</Text>
        </Pressable>
      </View>
    </View>
  );
}

export default function ControleSistemaScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Controle do Sistema está disponível apenas no web."
        testID="controle-sistema-web-only"
      />
    );
  }

  const f = useControleSistemaForm();
  const visibleTabs = TABS.filter((t) => can(`CTRL_SISTEMA.${t.comando}`) || isMaster);
  const allTabs = isMaster ? [...visibleTabs, TAB_KONTACTO] : visibleTabs;
  const [tab, setTab] = useState<TabKey>(allTabs[0]?.key ?? "empresarial");
  const canSave = can("CTRL_SISTEMA.GRAVAR") || isMaster;
  const [modal, setModal] = useState<null | "email" | "cep" | "tray" | "impressora" | "remessa">(null);

  const planoContasFiltrado = (tipo: "R" | "D") => f.planoContas.filter((c) => c.tipo === tipo);
  const subClassesDe = (classes: typeof f.planoContas, classeCodigo: string | boolean) => {
    const cod = Number(classeCodigo);
    const classe = classes.find((c) => c.codigo === cod);
    return classe ? classe.sub_classes : [];
  };

  const tipoMovOpts: SelectOption[] = f.tipoMovOptions.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }));
  const formaPagOpts: SelectOption[] = f.formaPagamentoOptions.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }));
  const contasOpts: SelectOption[] = f.contasOptions.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }));

  const classeOpts = (tipo: "R" | "D"): SelectOption[] =>
    planoContasFiltrado(tipo).map((c) => ({ value: String(c.codigo), label: c.descricao }));
  const subClasseOpts = (tipo: "R" | "D", classeField: string): SelectOption[] =>
    subClassesDe(planoContasFiltrado(tipo), f.form[classeField]).map((sc) => ({ value: String(sc.codigo), label: sc.descricao }));

  const handleSave = async () => {
    await f.save();
  };

  if (f.loadingInit) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="controle-sistema-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Controle do Sistema</Text>
        {canSave ? (
          <Pressable onPress={handleSave} disabled={f.saving} style={styles.saveBtn} testID="controle-sistema-salvar">
            {f.saving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.saveBtnText}>Gravar</Text>}
          </Pressable>
        ) : <View style={{ width: 40 }} />}
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tabBarScroll} contentContainerStyle={styles.tabBar}>
        {allTabs.map((t) => (
          <Pressable
            key={t.key}
            onPress={() => setTab(t.key)}
            style={[styles.tabBtn, tab === t.key && styles.tabBtnActive]}
            testID={`controle-sistema-tab-${t.key}`}
          >
            <Text style={[styles.tabBtnText, tab === t.key && styles.tabBtnTextActive]}>{t.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView style={styles.contentScroll} contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={WEB_CONTENT_SHELL}>
          {allTabs.length === 0 ? (
            <Text style={styles.helperText}>Sem permissão para nenhuma aba desta tela.</Text>
          ) : null}

          {tab === "empresarial" && allTabs.some((t) => t.key === "empresarial") ? (
            <View style={styles.card}>
              <SectionTitle>Dados Cadastrais</SectionTitle>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="cgc" label="CNPJ" maxLength={14} keyboardType="number-pad" />
                <Txt form={f.form} setField={f.setField} campo="rz_social" label="Razão Social" />
                <DateField label="Data Abertura" value={(f.form.data_abertura as string) || null} onChange={(v) => f.setField("data_abertura", v || "")} />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="fantasia" label="Fantasia" />
                <Txt form={f.form} setField={f.setField} campo="inscr_est" label="Insc. Est." />
                <Txt form={f.form} setField={f.setField} campo="inscr_municipal" label="Insc. Municipal" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="nire" label="Nire" />
                <Txt form={f.form} setField={f.setField} campo="suframa" label="Suframa" />
                <Txt form={f.form} setField={f.setField} campo="cnae_fiscal_principal" label="Cnae Principal" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="cnae_fiscal_servico" label="Cnae Serviço" />
                <Num form={f.form} setField={f.setField} campo="ddd" label="DDD" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="telefone" label="Telefone" keyboardType="number-pad" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="CELULAR" label="Celular" keyboardType="number-pad" />
                <Txt form={f.form} setField={f.setField} campo="endereco" label="Endereço" />
                <Num form={f.form} setField={f.setField} campo="numero" label="Número" decimais={0} />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="complemento" label="Complemento" />
                <Txt form={f.form} setField={f.setField} campo="bairro" label="Bairro" />
                <Txt form={f.form} setField={f.setField} campo="cep" label="CEP" keyboardType="number-pad" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="cidade" label="Cidade" />
                <View style={styles.colThird}>
                  <Text style={styles.label}>UF</Text>
                  <SelectField value={(f.form.uf as string) || ""} onChange={(v) => f.setField("uf", v ? String(v) : "")} options={UF_OPTS} placeholder="UF" compactWeb testID="ctrl-uf" modalTitle="UF" />
                </View>
                <Num form={f.form} setField={f.setField} campo="dias_troca" label="Dias troca" decimais={0} />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="percent_troca" label="% troca" />
                <View style={styles.colThird}>
                  <Text style={styles.label}>Tipo</Text>
                  <SelectField value={String(f.form.tipo_controle ?? "")} onChange={(v) => f.setField("tipo_controle", v != null ? String(v) : "")} options={TIPO_CONTROLE_OPTS} compactWeb testID="ctrl-tipo-controle" modalTitle="Tipo" />
                </View>
                <Txt form={f.form} setField={f.setField} campo="codigo" label="Código na fábrica" />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="numero_anp" label="Código Anp" />
                <Num form={f.form} setField={f.setField} campo="qtdturnos" label="Qtd Turno" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="e_mail" label="Email Principal" keyboardType="email-address" />
              </View>
              <SubSectionTitle>Código de Segurança do Contribuinte (SEFAZ)</SubSectionTitle>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="csc" label="CSC" />
                <Txt form={f.form} setField={f.setField} campo="csc_hash" label="CSC Hash" />
              </View>
            </View>
          ) : null}

          {tab === "movimentacoes" ? (
            <View style={styles.card}>
              <SectionTitle>Num/Série e Modelo NF</SectionTitle>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_nf" label="Nº Prod/Serv." decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="serie_nf" label="Série" />
                <Num form={f.form} setField={f.setField} campo="modelo_nf" label="Modelo" decimais={0} />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_nf_ent" label="Nº Só Entrada" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="serie_nf_ent" label="Série" />
                <Num form={f.form} setField={f.setField} campo="modelo_nf_ent" label="Modelo" decimais={0} />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_nf_ser" label="Nº NF Serviço" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="serie_nf_ser" label="Série" />
                <Txt form={f.form} setField={f.setField} campo="versao_nfe" label="Versão NFe" disabled />
              </View>
              {canSave ? (
                <Pressable onPress={f.saveNfPrincipal} style={styles.secondaryBtn} testID="ctrl-gravar-nfe">
                  <Text style={styles.secondaryBtnText}>Gravar Alterações NFE</Text>
                </Pressable>
              ) : null}

              <SubSectionTitle>Outras Séries NFe</SubSectionTitle>
              <SeriesNfGrid f={f} canSave={canSave} />

              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_nfce" label="Nº NFCe" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="serie_nfce" label="Série" />
                <Txt form={f.form} setField={f.setField} campo="versao_layout_nfce" label="Versão NFCe" disabled />
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="VersaoQrCodeNFCe" label="Versão QrCode" />
                <Num form={f.form} setField={f.setField} campo="modelo_danfe_nfce" label="Modelo Danfe NFCe" decimais={0} />
              </View>
              {canSave ? (
                <Pressable onPress={f.saveNfceNumeracao} style={styles.secondaryBtn} testID="ctrl-gravar-nfce">
                  <Text style={styles.secondaryBtnText}>Gravar Alterações NFCE</Text>
                </Pressable>
              ) : null}

              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_MDFE" label="Nº MDF-e" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="serie_MDFE" label="Série" />
              </View>
              {canSave ? (
                <Pressable onPress={f.saveMdfeNumeracao} style={styles.secondaryBtn} testID="ctrl-gravar-mdfe">
                  <Text style={styles.secondaryBtnText}>Gravar Alterações MDF-e</Text>
                </Pressable>
              ) : null}
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="margem_nf" label="Margem Danfe" />
              </View>

              <SectionTitle>Modelo de</SectionTitle>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="modelo_os" label="OS" decimais={0} />
                <Num form={f.form} setField={f.setField} campo="modelo_recibo" label="Recibo" decimais={0} />
                <Num form={f.form} setField={f.setField} campo="modelo_pedido" label="Pedido Venda" decimais={0} />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="modelo_pedido_compra" label="Pedido Compra" decimais={0} />
              </View>

              <SectionTitle>Relatórios Peças</SectionTitle>
              <View style={styles.switchRow}>
                <Pressable onPress={() => f.setField("cod_rel", "I")} style={styles.radioOpt}>
                  <Ionicons name={f.form.cod_rel === "I" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Cod. Interno</Text>
                </Pressable>
                <Pressable onPress={() => f.setField("cod_rel", "F")} style={styles.radioOpt}>
                  <Ionicons name={f.form.cod_rel === "F" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Cod. Fabricação</Text>
                </Pressable>
              </View>

              <SectionTitle>Configurações Posto</SectionTitle>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="porta_concentrador" label="Porta do Concentrador" />
                <Num form={f.form} setField={f.setField} campo="id_fusion" label="ID Fusion" decimais={0} />
              </View>
              <View style={styles.switchRow}>
                <Pressable onPress={() => f.setField("modelo_concentrador", "0")} style={styles.radioOpt}>
                  <Ionicons name={f.form.modelo_concentrador === "0" || f.form.modelo_concentrador === "" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Fusion</Text>
                </Pressable>
                <Pressable onPress={() => f.setField("modelo_concentrador", "1")} style={styles.radioOpt}>
                  <Ionicons name={f.form.modelo_concentrador === "1" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Companytec</Text>
                </Pressable>
              </View>
              <View style={styles.switchRow}>
                <Pressable onPress={() => f.setField("tipo_comunicacao_concentrador", "0")} style={styles.radioOpt}>
                  <Ionicons name={f.form.tipo_comunicacao_concentrador === "0" || f.form.tipo_comunicacao_concentrador === "" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>TXT</Text>
                </Pressable>
                <Pressable onPress={() => f.setField("tipo_comunicacao_concentrador", "1")} style={styles.radioOpt}>
                  <Ionicons name={f.form.tipo_comunicacao_concentrador === "1" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>DLL</Text>
                </Pressable>
              </View>
              <SubSectionTitle>Horário de Fechamento dos Turnos</SubSectionTitle>
              <TurnoGrid f={f} canSave={canSave} />
              <Chk form={f.form} setField={f.setField} campo="Permite_venda_combustiveis" label="Permite venda de combustíveis fora da automação" />
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="QTD_ABASTECIMENTOS_NFCE" label="Número de Abastecimentos por Venda" decimais={0} />
              </View>

              <SectionTitle>Número / Código</SectionTitle>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_os" label="O.S." decimais={0} />
                <Num form={f.form} setField={f.setField} campo="cod_peca" label="Produto" decimais={0} />
              </View>

              <SectionTitle>Movimentação</SectionTitle>
              <View style={styles.rowFields}>
                <DateField label="Data" value={(f.form.data_movimento as string) || null} onChange={() => { /* readonly, igual ao legado */ }} />
              </View>
            </View>
          ) : null}

          {tab === "diversos" ? (
            <View style={styles.card}>
              <SectionTitle>Configurações Diversas</SectionTitle>
              <Chk form={f.form} setField={f.setField} campo="nome_fantasia_cabecalho_dav" label="Imprime Nome Fantasia nos cabeçalhos dos DAV's" />
              <Chk form={f.form} setField={f.setField} campo="Inclui_Dados_Faturar_Para" label="Inclui dados do Cliente &quot;Faturar para&quot;" />
              <Chk form={f.form} setField={f.setField} campo="Destaca_Desconto_Cedido" label="Destacar descontos cedidos..." />
              <Chk form={f.form} setField={f.setField} campo="Habilita_Preco_Tabela_Pedido" label="Permitir DAV's com Preço Tabela" />
              <Chk form={f.form} setField={f.setField} campo="registra_venda_automatica" label="Vende itens automaticamente por código de barras" />
              <Chk form={f.form} setField={f.setField} campo="Senha_Gerente" label="Senha para venda com estoque negativo" />
              <Chk form={f.form} setField={f.setField} campo="fecha_pedido_automaticamente" label="Fecha Pedido Venda ao imprimir" />
              <Chk form={f.form} setField={f.setField} campo="exige_aprovacao_itens_os" label="Exige Autorização de itens O.S." />
              <Chk form={f.form} setField={f.setField} campo="exige_expedicao_itens_os" label="Exige Expedição Itens O.S." />
              <Chk form={f.form} setField={f.setField} campo="EXIGE_KM_OS" label="Exige Kilometragem O.S." />
              <Chk form={f.form} setField={f.setField} campo="EXIGE_referencia_OS" label="Exige Referência O.S." />
              <Chk form={f.form} setField={f.setField} campo="ControlaRevisaoOS" label="Controla Revisão O.S." />

              <SubSectionTitle>Recebimento de Nf's, atualiza preço de venda por...</SubSectionTitle>
              <View style={styles.switchRow}>
                <Pressable onPress={() => f.setField("Altera_preco_venda_tela", "1")} style={styles.radioOpt}>
                  <Ionicons name={f.form.Altera_preco_venda_tela === "1" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Tipo de Preço (Cadastro de Produtos)</Text>
                </Pressable>
                <Pressable onPress={() => f.setField("Altera_preco_venda_tela", "2")} style={styles.radioOpt}>
                  <Ionicons name={f.form.Altera_preco_venda_tela === "2" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Na própria tela de Recebimento</Text>
                </Pressable>
              </View>

              <Chk form={f.form} setField={f.setField} campo="ALERTA_ESTOQUE_NEGATIVO" label="Alerta Estoque Negativo" />
              <Chk form={f.form} setField={f.setField} campo="EXIGE_OS_ORIGINAL_GARANTIA" label="Exige O.S. Original das O.S's de Garantia" />
              <Chk form={f.form} setField={f.setField} campo="preco_cld" label="Preço CLD" />
              <Chk form={f.form} setField={f.setField} campo="paga_comissao_venda_garantia" label="Paga Comissão Venda Garantia" />
              <Chk form={f.form} setField={f.setField} campo="bloqueia_venda_cliente_com_debito" label="Bloqueia Pedido Cliente com Débito" />

              <SectionTitle>Trocas &amp; Devoluções</SectionTitle>
              <Chk form={f.form} setField={f.setField} campo="emite_vale_troca" label="Emite cupom de troca automaticamente no ECF" />
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="msg_vale_troca_1" label="Mensagem do cupom de troca (linha 1)" />
                <Txt form={f.form} setField={f.setField} campo="msg_vale_troca_2" label="Mensagem do cupom de troca (linha 2)" />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="validade_vale_troca" label="Dias de validade do Cupom de Troca" decimais={0} />
                <Num form={f.form} setField={f.setField} campo="dias_troca" label="Dias p/ solicitação de troca ou devolução" decimais={0} />
              </View>

              <SectionTitle>Descontos Vendas</SectionTitle>
              <View style={styles.switchRow}>
                <Pressable onPress={() => f.setField("desconto_PDV", "1")} style={styles.radioOpt}>
                  <Ionicons name={f.form.desconto_PDV === "1" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Aceita Desconto: Sim</Text>
                </Pressable>
                <Pressable onPress={() => f.setField("desconto_PDV", "0")} style={styles.radioOpt}>
                  <Ionicons name={f.form.desconto_PDV === "0" || f.form.desconto_PDV === "" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Não</Text>
                </Pressable>
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="desconto_PDV_Gerente" label="Gerente" />
                <Num form={f.form} setField={f.setField} campo="desconto_PDV_Vendedor" label="Vendedor" />
                <Num form={f.form} setField={f.setField} campo="desconto_PDV_Supervisor" label="Supervisor" />
              </View>

              <SectionTitle>Alerta de Estoque por Email</SectionTitle>
              <Chk form={f.form} setField={f.setField} campo="ALERTA_ESTOQUE" label="Habilitar alerta de estoque por e-mail" />
              <Txt form={f.form} setField={f.setField} campo="EMAIL_ALERTA_ESTOQUE" label="Email(s) para envio de alerta" />
              <Chk form={f.form} setField={f.setField} campo="ALERTA_ESTOQUE_MINIMO" label="Alertar produtos de Estoque Mínimo" />
              <Chk form={f.form} setField={f.setField} campo="ALERTA_ESTOQUE_RESSUPRIMENTO" label="Alertar produtos de Estoque Ressuprimento" />
              <Chk form={f.form} setField={f.setField} campo="ALERTA_ESTOQUE_ZERADO" label="Alertar produtos de Estoque Zerado ou Negativo" />

              <SectionTitle>Textos e Orçamento</SectionTitle>
              <Txt form={f.form} setField={f.setField} campo="MENSAGEM_OS" label="Mensagem do rodapé da O.S" />
              <Txt form={f.form} setField={f.setField} campo="MENSAGEM_obs_OS" label="Observação fixa da O.S" />
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="PRODUTO_ORCAMENTO" label="Produto para Orçamento" />
                <Num form={f.form} setField={f.setField} campo="COD_CLIENTE_ORCAMENTO" label="Cliente Orçamento" decimais={0} />
              </View>
            </View>
          ) : null}

          {tab === "fiscal" ? (
            <View style={styles.card}>
              <SectionTitle>Opções Fiscais</SectionTitle>
              <Num form={f.form} setField={f.setField} campo="informa_codigo_barras" label="Informa Código de Barras (código da opção)" decimais={0} />
              <Chk form={f.form} setField={f.setField} campo="Inclui_Endereco_Entrega_Obs_Nfe" label="Incluir Endereço de Entrega na observação da Nfe" />
              <Chk form={f.form} setField={f.setField} campo="Inclui_Endereco_Cobranca_Obs_Nfe" label="Incluir Endereço de Cobrança na observação da Nfe" />
              <Chk form={f.form} setField={f.setField} campo="indicador_intermediario" label="NFE/NFCe - Indicador de intermediário" />
              <Chk form={f.form} setField={f.setField} campo="IMPRIME_VENDEDOR_DANFE_NFCE" label="Imprime Dados complementares (vendedor) nos Danfes e DAV's" />
              <Chk form={f.form} setField={f.setField} campo="DEVOLUCAO_CANCELA_NFE_ORIGINAL" label="Devolução cancela Nfe original" />
              <Chk form={f.form} setField={f.setField} campo="imprime_dados_os_danfe" label="Imprime Placa/Km na NFe/Nfce" />
              <Chk form={f.form} setField={f.setField} campo="emite_nf_comanda" label="Emite NF Comanda" />
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="Regime_Trib" label="Regime Tributário (CRT)" decimais={0} />
                <Num form={f.form} setField={f.setField} campo="pagina_lmc" label="Página LMC" decimais={0} />
              </View>

              <SubSectionTitle>Certificado Digital</SubSectionTitle>
              <CertificadoGrid f={f} canSave={canSave} />

              <SectionTitle>Frete na NFCe</SectionTitle>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="SERVICO_FRETE_NFCE" label="Código Serviço Frete" />
                <Num form={f.form} setField={f.setField} campo="TRANSPORTADOR_FRETE_NFCE" label="Transportador Padrão" decimais={0} />
              </View>

              <Text style={styles.helperText}>
                Configuração de Emails e Consulta de CEP foram movidas pra aba Outros (botões próprios, igual ao
                layout original da tela legada).
              </Text>

              <SectionTitle>Configurações NFS-e</SectionTitle>
              <Chk form={f.form} setField={f.setField} campo="opcao_simples" label="Optante Simples" />
              <Chk form={f.form} setField={f.setField} campo="incentivo_cultural" label="Incentivo Cultural" />
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="RegimeEspecialTributacao" label="Regime Tributação Especial" />
                <Txt form={f.form} setField={f.setField} campo="NaturezaOperacao" label="Natureza da Operação" />
              </View>
              <View style={styles.switchRow}>
                <Pressable onPress={() => f.setField("PROTOCOLO_TLS_NFSE", "10")} style={styles.radioOpt}>
                  <Ionicons name={f.form.PROTOCOLO_TLS_NFSE === "10" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>TLS 1.0</Text>
                </Pressable>
                <Pressable onPress={() => f.setField("PROTOCOLO_TLS_NFSE", "12")} style={styles.radioOpt}>
                  <Ionicons name={f.form.PROTOCOLO_TLS_NFSE === "12" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>TLS 1.2</Text>
                </Pressable>
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_DPS" label="DPS Número" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="serie_DPS" label="Série" />
                <Txt form={f.form} setField={f.setField} campo="codigo_nbs" label="Código NBS" />
              </View>
              <Chk form={f.form} setField={f.setField} campo="ISS_Retido" label="Iss Retido" />
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="iss" label="ISS" />
                <Num form={f.form} setField={f.setField} campo="Simples_Servico" label="Aliquota Simples Nacional" />
              </View>
              <SubSectionTitle>PIS / Cofins</SubSectionTitle>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="cst_pis_cofins_dps" label="CST" />
                <Num form={f.form} setField={f.setField} campo="pis" label="PIS" />
                <Num form={f.form} setField={f.setField} campo="Cofins" label="Cofins" />
              </View>
              <Txt form={f.form} setField={f.setField} campo="retencao_pis_cofins_dps" label="Retenção" />
              <SubSectionTitle>Perc. Total Tributos</SubSectionTitle>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="perc_tributos_federais_dps" label="Federal" />
                <Num form={f.form} setField={f.setField} campo="perc_tributos_estaduais_dps" label="Estadual" />
                <Num form={f.form} setField={f.setField} campo="perc_tributos_municipais_dps" label="Municipal" />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_rps" label="RPS Número" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="serie_rps" label="Série" />
              </View>
            </View>
          ) : null}

          {tab === "outros" ? (
            <View style={styles.card}>
              <SectionTitle>Configurações</SectionTitle>
              <View style={styles.rowFields}>
                <Pressable onPress={() => setModal("email")} style={styles.secondaryBtn} testID="ctrl-btn-email">
                  <Text style={styles.secondaryBtnText}>Configuração de Emails</Text>
                </Pressable>
                <Pressable onPress={() => setModal("cep")} style={styles.secondaryBtn} testID="ctrl-btn-cep">
                  <Text style={styles.secondaryBtnText}>Configuração de CEP</Text>
                </Pressable>
              </View>
              <View style={styles.rowFields}>
                <Pressable onPress={() => setModal("impressora")} style={styles.secondaryBtn} testID="ctrl-btn-impressora">
                  <Text style={styles.secondaryBtnText}>Cadastro de Impressoras por Grupo de Produtos</Text>
                </Pressable>
                <Pressable onPress={() => setModal("remessa")} style={styles.secondaryBtn} testID="ctrl-btn-remessa">
                  <Text style={styles.secondaryBtnText}>Configuração Emissão NF Garantia DAV's</Text>
                </Pressable>
              </View>
              <View style={styles.rowFields}>
                <Pressable onPress={() => setModal("tray")} style={styles.secondaryBtn} testID="ctrl-btn-tray">
                  <Text style={styles.secondaryBtnText}>Integração TRAY</Text>
                </Pressable>
              </View>

              <SectionTitle>Metro Quadrado</SectionTitle>
              <Text style={styles.label}>Calcular Área Mínima em:</Text>
              <Chk form={f.form} setField={f.setField} campo="m2_area_minima_padrao" label="Venda Padrão" />
              <Chk form={f.form} setField={f.setField} campo="m2_area_minima_modelado" label="Modelado Comum" />
              <Chk form={f.form} setField={f.setField} campo="m2_area_minima_engenharia" label="Engenharia" />
              <Chk form={f.form} setField={f.setField} campo="m2_area_minima_modelado_engenharia" label="Modelado Engenharia" />
              <Chk form={f.form} setField={f.setField} campo="m2_area_minima_comum_lapidacao" label="Comum (C/ Lapidação)" />
              <Chk form={f.form} setField={f.setField} campo="m2_area_minima_comum_sem_lapidacao" label="Comum (S/ Lapidação)" />
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="metro_quadrado_minima_metragem" label="M2 Área Mínima" />
              </View>
              <Chk form={f.form} setField={f.setField} campo="vidro_controla_cabeca_chapa" label="Cálculo da Cabeça de Chapa" />

              <SectionTitle>Vendas Garantia</SectionTitle>
              <View style={styles.rowFields}>
                <View style={styles.colThird}>
                  <Text style={styles.label}>Tipo Movimentação para Vendas Garantia</Text>
                  <SelectField
                    value={(f.form.tipo_mov_garantia as string) || ""}
                    onChange={(v) => f.setField("tipo_mov_garantia", v ? String(v) : "")}
                    options={tipoMovOpts} allowClear compactWeb testID="ctrl-tipo-mov-garantia" modalTitle="Tipo de Movimentação"
                  />
                </View>
              </View>

              <SectionTitle>Pesquisa de Satisfação BTEN</SectionTitle>
              <Chk form={f.form} setField={f.setField} campo="Pesquisa_Satisfacao_BTEN" label="Habilitar Pesquisa de Satisfação BTEN" />
              <Txt form={f.form} setField={f.setField} campo="token_Authorization_pesquisa_satisfacao" label="Token Authorization" disabled={!f.form.Pesquisa_Satisfacao_BTEN} />
              <Txt form={f.form} setField={f.setField} campo="token_business_pesquisa_satisfacao" label="Token Business" disabled={!f.form.Pesquisa_Satisfacao_BTEN} />
            </View>
          ) : null}

          {tab === "financeiro" ? (
            <View style={styles.card}>
              <SectionTitle>Contas</SectionTitle>
              <View style={styles.rowFields}>
                <View style={styles.colThird}>
                  <Text style={styles.label}>Conta Padrão</Text>
                  <SelectField
                    value={(f.form.conta_transf_caixa as string) || ""}
                    onChange={(v) => f.setField("conta_transf_caixa", v ? String(v) : "")}
                    options={contasOpts} allowClear compactWeb testID="ctrl-conta-padrao" modalTitle="Conta Padrão"
                  />
                </View>
              </View>

              <SectionTitle>Receber — Categorias por Operação</SectionTitle>
              {([
                { label: "Tarifas Bancárias", classe: "classe_ent_tarifa", sub: "sub_classe_ent_tarifa" },
                { label: "Acréscimos + Juros", classe: "classe_ent_juros", sub: "sub_classe_ent_juros" },
                { label: "Descontos", classe: "classe_ent_descontos", sub: "sub_classe_ent_descontos" },
              ] as const).map((row) => (
                <View style={styles.rowFields} key={row.classe}>
                  <View style={styles.colThird}>
                    <Text style={styles.label}>{row.label} — Categoria</Text>
                    <SelectField value={(f.form[row.classe] as string) || ""} onChange={(v) => { f.setField(row.classe, v ? String(v) : ""); f.setField(row.sub, ""); }} options={classeOpts("R")} allowClear compactWeb testID={`ctrl-${row.classe}`} modalTitle="Categoria" />
                  </View>
                  <View style={styles.colThird}>
                    <Text style={styles.label}>Sub Categoria</Text>
                    <SelectField value={(f.form[row.sub] as string) || ""} onChange={(v) => f.setField(row.sub, v ? String(v) : "")} options={subClasseOpts("R", row.classe)} allowClear disabled={!f.form[row.classe]} compactWeb testID={`ctrl-${row.sub}`} modalTitle="Sub Categoria" />
                  </View>
                </View>
              ))}

              <SectionTitle>Pagar — Categorias por Operação</SectionTitle>
              {([
                { label: "Tarifas Bancárias", classe: "classe_sai_tarifa", sub: "sub_classe_sai_tarifa" },
                { label: "Acréscimos + Juros", classe: "classe_sai_juros", sub: "sub_classe_sai_juros" },
                { label: "Descontos", classe: "classe_sai_descontos", sub: "sub_classe_sai_descontos" },
              ] as const).map((row) => (
                <View style={styles.rowFields} key={row.classe}>
                  <View style={styles.colThird}>
                    <Text style={styles.label}>{row.label} — Categoria</Text>
                    <SelectField value={(f.form[row.classe] as string) || ""} onChange={(v) => { f.setField(row.classe, v ? String(v) : ""); f.setField(row.sub, ""); }} options={classeOpts("D")} allowClear compactWeb testID={`ctrl-${row.classe}`} modalTitle="Categoria" />
                  </View>
                  <View style={styles.colThird}>
                    <Text style={styles.label}>Sub Categoria</Text>
                    <SelectField value={(f.form[row.sub] as string) || ""} onChange={(v) => f.setField(row.sub, v ? String(v) : "")} options={subClasseOpts("D", row.classe)} allowClear disabled={!f.form[row.classe]} compactWeb testID={`ctrl-${row.sub}`} modalTitle="Sub Categoria" />
                  </View>
                </View>
              ))}

              <SectionTitle>Caixa</SectionTitle>
              <Chk form={f.form} setField={f.setField} campo="TROCO_CARTAO" label="Permite Troco em Cartões" />
              <Chk form={f.form} setField={f.setField} campo="Inclui_Classe_Caixa_Mov" label="Permite Lcto Sem Classe Pré Cadastrada" />
              <Chk form={f.form} setField={f.setField} campo="senha_gerente_cx" label="Senha Gerente p/Alteração" />
              <Chk form={f.form} setField={f.setField} campo="AgrupaComandas_Cx" label="Agrupa Comandas no Caixa" />
              <Chk form={f.form} setField={f.setField} campo="Transf_Caixa_Contabil" label="Transf.Fluxo Caixa p/Contabilidade" />
              <Chk form={f.form} setField={f.setField} campo="Exclui_Recebimento_Automatico" label="Cancelar comandas com Vencimentos já recebidos" />
              <Chk form={f.form} setField={f.setField} campo="cancelamento_paf_exige_senha" label="Exigir senha cancelamento de vendas no PAF/NFCe" />
              <Chk form={f.form} setField={f.setField} campo="transf_ent_sai_caixa" label="Transfere Entrada/Saída de Caixa para o financeiro" />

              <SectionTitle>Contas a Pagar / Receber</SectionTitle>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="numero_dup" label="Número Duplicata" decimais={0} />
                <Txt form={f.form} setField={f.setField} campo="desmembramento_dup" label="Desm." />
                <Num form={f.form} setField={f.setField} campo="seq_recibo" label="Número Recibo" decimais={0} />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="ano_recibo" label="Ano" decimais={0} />
                <Num form={f.form} setField={f.setField} campo="Multa_Atraso_Pag" label="Multa" />
                <Num form={f.form} setField={f.setField} campo="Mora_Dia_Pag" label="Mora Diária" />
              </View>
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="Tarifa_Boleto" label="Boleto Bancário" />
                <Num form={f.form} setField={f.setField} campo="dias_protesto" label="Dias Protesto" decimais={0} />
                <Num form={f.form} setField={f.setField} campo="Minimo_Boleto" label="Mínimo boleto" />
              </View>
              <Txt form={f.form} setField={f.setField} campo="Msg_Padrao_Boleto_1" label="Mensagem Boleto (linha 1)" />
              <Txt form={f.form} setField={f.setField} campo="Msg_Padrao_Boleto_2" label="Mensagem Boleto (linha 2)" />
              <Txt form={f.form} setField={f.setField} campo="Msg_Padrao_Boleto_3" label="Mensagem Boleto (linha 3)" />
              <View style={styles.rowFields}>
                <Num form={f.form} setField={f.setField} campo="Dias_Ver_Cx" label="Dias Visualização Caixa Fechado" decimais={0} />
                <Num form={f.form} setField={f.setField} campo="dias_alt_cx" label="Dias alteração caixa" decimais={0} />
              </View>
            </View>
          ) : null}

          {tab === "contratos" ? (
            <View style={styles.card}>
              <SectionTitle>Contratos</SectionTitle>
              <View style={styles.switchRow}>
                <Pressable onPress={() => f.setField("fatura_os_contrato", true)} style={styles.radioOpt}>
                  <Ionicons name={f.form.fatura_os_contrato ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Faturar OS's no Contrato: Sim</Text>
                </Pressable>
                <Pressable onPress={() => f.setField("fatura_os_contrato", false)} style={styles.radioOpt}>
                  <Ionicons name={!f.form.fatura_os_contrato ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                  <Text style={styles.switchLabel}>Não</Text>
                </Pressable>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colThird}>
                  <Text style={styles.label}>Tipo de Movimentação (para peças)</Text>
                  <SelectField value={(f.form.tipo_mov_contrato_peca as string) || ""} onChange={(v) => f.setField("tipo_mov_contrato_peca", v ? String(v) : "")} options={tipoMovOpts} allowClear compactWeb testID="ctrl-tmov-peca" modalTitle="Tipo de Movimentação" />
                </View>
                <View style={styles.colThird}>
                  <Text style={styles.label}>Tipo de Movimentação (para serviços)</Text>
                  <SelectField value={(f.form.tipo_mov_contrato_servico as string) || ""} onChange={(v) => f.setField("tipo_mov_contrato_servico", v ? String(v) : "")} options={tipoMovOpts} allowClear compactWeb testID="ctrl-tmov-servico" modalTitle="Tipo de Movimentação" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="cod_servico_contrato" label="Código do Serviço" />
                <View style={styles.colThird}>
                  <Text style={styles.label}>Forma de Pagamento</Text>
                  <SelectField value={(f.form.forma_pag_contrato as string) || ""} onChange={(v) => f.setField("forma_pag_contrato", v ? String(v) : "")} options={formaPagOpts} allowClear compactWeb testID="ctrl-forma-pag-contrato" modalTitle="Forma de Pagamento" />
                </View>
              </View>
            </View>
          ) : null}

          {tab === "kontacto" && isMaster ? (
            <View style={styles.card}>
              <SectionTitle>Kontacto</SectionTitle>
              <Text style={styles.helperText}>
                Visível apenas para o usuário Master. Não replica a "Configuração de Clientes" (já coberta pela
                tela Módulos e Recursos) nem a "Integração TRAY" (integração externa própria, fora de escopo aqui).
              </Text>
              <View style={styles.rowFields}>
                <Txt form={f.form} setField={f.setField} campo="codigo_kontacto" label="Cód. Kontacto" />
                <Txt form={f.form} setField={f.setField} campo="controle" label="Controle (licença)" disabled />
                <View style={styles.colThird}>
                  <Text style={styles.label}>Situação (Banco de Dados)</Text>
                  <TextInput
                    value={String(f.form.situacao ?? "")}
                    onChangeText={(v) => f.setField("situacao", v.toUpperCase().slice(0, 1))}
                    maxLength={1} style={styles.input} testID="ctrl-situacao"
                  />
                </View>
              </View>

              <Chk form={f.form} setField={f.setField} campo="ESCOLHE_NFE_NFCE" label="Escolhe NFCe ou NFe" />
              <Chk form={f.form} setField={f.setField} campo="PERGUNTA_EMITE_NFCE" label="Permite venda sem nfce/nfse" />
              <Chk form={f.form} setField={f.setField} campo="USA_PRECO_BASE_NFCE" label="Usa preço base" />
              <Chk form={f.form} setField={f.setField} campo="IMPRIME_NFCE_NAO_FISCAL" label="Imprime NFCe/NFSe Não Fiscal" />
              <Chk form={f.form} setField={f.setField} campo="imprime_nfse" label="Usa Nfs-e" />

              <SubSectionTitle>Início de emissão</SubSectionTitle>
              <View style={styles.rowFields}>
                <DateField label="Início Nfe" value={(f.form.data_inicio_nfe as string) || null} onChange={(v) => f.setField("data_inicio_nfe", v || "")} />
                <DateField label="Início Nfse" value={(f.form.data_inicio_nfse as string) || null} onChange={(v) => f.setField("data_inicio_nfse", v || "")} />
                <DateField label="Início Paf" value={(f.form.data_inicio_paf as string) || null} onChange={(v) => f.setField("data_inicio_paf", v || "")} />
              </View>

              <Chk form={f.form} setField={f.setField} campo="exige_cpf_cliente" label="Exige CPF/CNPJ no Cadastro de Clientes" />
              <Chk form={f.form} setField={f.setField} campo="aceita_duplicar_cnpj" label="Aceita Duplicar CPF/CNPJ no Cadastro de Clientes" />
              <Chk form={f.form} setField={f.setField} campo="inc_prod_os" label="Inc Produto Os" />
              <Chk form={f.form} setField={f.setField} campo="consulta_por_descricao_paf" label="Consulta de produtos por descrição do PAF ECF" />

              <SectionTitle>Paths</SectionTitle>
              <Txt form={f.form} setField={f.setField} campo="path_padrao_xml" label="Importação XML" />
              <Txt form={f.form} setField={f.setField} campo="Path_importacao_venda_externa" label="Importação Venda Externa" />
              <Txt form={f.form} setField={f.setField} campo="Path_backup_sql" label="Path Backup Banco de Dados" />
              <Txt form={f.form} setField={f.setField} campo="path_gestor_documentos" label="Path Gestor de Documentos" />
              <Txt form={f.form} setField={f.setField} campo="PATH_LOGO_EMAIL_COBRANCA" label="Path Logo Assinatura Email Cobrança" />
              <Txt form={f.form} setField={f.setField} campo="TEXTO_CORPO_EMAIL_COBRANCA" label="Mensagem Corpo Email Cobrança" />
            </View>
          ) : null}
        </View>
      </ScrollView>

      <Modal visible={modal !== null} transparent animationType="slide" onRequestClose={() => setModal(null)}>
        <Pressable style={styles.modalBg} onPress={() => setModal(null)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              {modal === "email" ? <EmailModalContent f={f} canSave={canSave} onClose={() => setModal(null)} /> : null}
              {modal === "cep" ? <CepModalContent f={f} canSave={canSave} onClose={() => setModal(null)} /> : null}
              {modal === "tray" ? <TrayModalContent f={f} canSave={canSave} onClose={() => setModal(null)} /> : null}
              {modal === "impressora" ? <ImpressoraModalContent f={f} canSave={canSave} onClose={() => setModal(null)} /> : null}
              {modal === "remessa" ? <RemessaModalContent f={f} canSave={canSave} onClose={() => setModal(null)} /> : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  saveBtn: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.onBrandPrimary + "22", minWidth: 40, alignItems: "center" },
  saveBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 14 },
  tabBarScroll: { backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border, flexGrow: 0 },
  tabBar: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, gap: spacing.sm, paddingVertical: spacing.sm },
  tabBtn: { height: 36, alignItems: "center", justifyContent: "center", paddingVertical: 0, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  tabBtnActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface, lineHeight: 16, textAlignVertical: "center" },
  tabBtnTextActive: { color: colors.onBrandPrimary },
  // Sem isto, o ScrollView de conteúdo (irmão da barra de abas, não o único
  // filho flexível da tela) não fica restrito à área abaixo da barra — em
  // abas com conteúdo bem mais alto (ex.: Movimentações) ele passava a
  // sobrepor a barra de abas. `contentContainerStyle` sozinho não resolve
  // isso; precisa do `style={{flex:1}}` no ScrollView em si.
  contentScroll: { flex: 1 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  card: {
    backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, alignSelf: "stretch", width: "100%",
  },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.md, marginBottom: spacing.xs, textTransform: "uppercase" },
  subSectionTitle: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm, marginBottom: 2 },
  helperText: { fontSize: 12, color: colors.muted, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.xs, marginBottom: 3 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 0, height: 36, fontSize: 13, lineHeight: 16,
    color: colors.onSurface, textAlignVertical: "center",
  },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  colThird: { flex: 1 },
  switchRow: { flexDirection: "row", alignItems: "center", gap: spacing.lg, paddingVertical: 3, flexWrap: "wrap" },
  switchLabel: { fontSize: 13, color: colors.onSurface },
  radioOpt: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  // `alignSelf: "center"` — botões (Gravar Alterações NFE/NFCE/MDF-e, Gravar dos
  // mini-grids) não devem esticar full-width só porque o pai é uma coluna
  // flex; tamanho pelo conteúdo e centralizado, igual ao resto do app.
  secondaryBtn: {
    alignSelf: "center", minWidth: 200, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingVertical: 9, paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center",
    marginTop: spacing.sm, marginBottom: spacing.sm,
  },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13, lineHeight: 16, textAlignVertical: "center" },
  gridRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    paddingVertical: spacing.xs, paddingHorizontal: spacing.sm, marginBottom: spacing.xs,
  },
  gridRowText: { fontSize: 13, color: colors.onSurface, flex: 1 },
  modalBg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: Platform.OS === "web" ? "center" : "flex-end",
    paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0,
    paddingVertical: Platform.OS === "web" ? spacing.xl : 0,
  },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: Platform.OS === "web" ? radius.lg : 18,
    borderTopRightRadius: Platform.OS === "web" ? radius.lg : 18,
    borderBottomLeftRadius: Platform.OS === "web" ? radius.lg : 0,
    borderBottomRightRadius: Platform.OS === "web" ? radius.lg : 0,
    borderWidth: Platform.OS === "web" ? 1 : 0,
    borderColor: colors.border,
    width: "100%",
    maxWidth: Platform.OS === "web" ? 720 : undefined,
    maxHeight: "90%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: spacing.md,
  },
  modalTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
});
