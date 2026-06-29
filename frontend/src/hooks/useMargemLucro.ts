import { useMutation } from "@tanstack/react-query";

import { MLConsolidado, MLEmpresa } from "@/src/utils/export-margem-lucro";

export type ConexaoEmpresa = { empresa: string; servidor: string; banco: string };

export type MargemLucroFiltros = {
  data_ini: string;
  data_fim: string;
  cod_cliente?: number | null;
  area_atuacao?: number | null;
  nivel?: string | null;
  cod_dav?: number | null;
  incluir_pedidos: boolean;
  incluir_os: boolean;
  incluir_comandas: boolean;
  davs_abertos: boolean;
  davs_fechados: boolean;
  davs_faturados: boolean;
  itens_os_nao_cobrados: boolean;
  retorna_produtos: boolean;
  retorna_servicos: boolean;
  somente_garantias: boolean;
  somente_venda_direta: boolean;
  resultado_operacional: boolean;
};

export type MargemLucroResponse = {
  success: boolean;
  message?: string;
  empresas: MLEmpresa[];
  consolidado: MLConsolidado;
};

type Vars = { api: string; conexoes: ConexaoEmpresa[]; filtros: MargemLucroFiltros };

async function postMargemLucro({ api, conexoes, filtros }: Vars): Promise<MargemLucroResponse> {
  const base = api.replace(/\/+$/, "");
  const res = await fetch(`${base}/api/relatorios/margem-lucro`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conexoes, ...filtros }),
  });
  const json = await res.json();
  if (!json?.success) {
    throw new Error(json?.message || "Falha ao gerar o relatório.");
  }
  return json as MargemLucroResponse;
}

/** Mutation para gerar o relatório de Margem de Lucro (acionado sob demanda). */
export function useMargemLucro() {
  return useMutation<MargemLucroResponse, Error, Vars>({ mutationFn: postMargemLucro });
}
