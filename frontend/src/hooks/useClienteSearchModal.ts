// Hook compartilhado pro modal de busca de cliente (`ClientSearchModal`)
// usado como FILTRO de tela (relatórios/listas de gestão) — não o fluxo
// de Pedido/O.S. (ver "Padrão de Campo Cliente" no CLAUDE.md, que tem
// regras próprias de digitação+Enter). Aqui o campo de texto existente
// continua livre (substring/código, o que a tela já mandava pro backend)
// — este hook só adiciona o MECANISMO DE BUSCA que faltava (ícone que
// abre o modal, escolher preenche o campo com um valor confirmado real
// em vez de digitação às cegas) — regra `[GLOBAL]` "Campos provenientes
// de identidade precisam de mecanismo de busca".
//
// Extraído 2026-08-22 (varredura de design/UI) — 7 telas de filtro
// (`relatorio-descontos.tsx`, `relatorio-descontos-concedidos.tsx`,
// `relatorio-os-descontos.tsx`, `relatorio-resumo-atendimento.tsx`,
// `gestor-comandas.tsx`, `gestor-nfce.tsx`, `gestor-nfse.tsx`) tinham
// campo de Cliente sem nenhum mecanismo de busca — cada uma reimplementaria
// o mesmo boilerplate (open/term/loading/results + debounce) se não
// extraído aqui.
import { useEffect, useState } from "react";
import { apiGet, ConnLike } from "@/src/utils/api";
import { ClienteRow } from "@/src/components/pedido/types";

export function useClienteSearchModal(conn: ConnLike | null | undefined) {
  const [open, setOpen] = useState(false);
  const [term, setTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ClienteRow[]>([]);

  useEffect(() => {
    if (!open || !conn) return;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const j = await apiGet(conn, "/api/clientes/find/search", { term });
        setResults(j?.items || []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [term, open, conn]);

  const openModal = () => {
    setTerm("");
    setResults([]);
    setOpen(true);
  };
  const closeModal = () => setOpen(false);

  return { open, term, setTerm, loading, results, openModal, closeModal };
}
