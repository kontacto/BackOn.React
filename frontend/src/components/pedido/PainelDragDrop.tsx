// Drag-and-drop nativo (HTML5) do Painel de Pedidos — arrastar um card
// entre colunas de Tipo (Mesa/Comanda/Balcão/Entrega/Fiado) troca o
// `pedido_venda.tipo` direto, sem abrir a tela cheia (ver
// `app/pedidos.tsx`, endpoint `POST /api/pedidos/{pedido}/tipo`). Web-only
// — o painel de colunas só existe no web (módulo Bar, ver CLAUDE.md >
// "Painel de Pedidos"). Usa a Drag and Drop API nativa do navegador via
// ref + addEventListener, não via props onDragStart/onDrop do React
// Native Web — RNW não repassa esses handlers pro elemento DOM (só
// reconhece a lista fixa de props que View já entende), então o único
// jeito confiável é pegar o node real pelo ref (RNW encaminha `ref` pro
// elemento host no web) e anexar os listeners manualmente. Pedido
// explícito do usuário, 2026-07-30.
import { ReactNode, useEffect, useRef, useState } from "react";
import { Platform, View, ViewStyle } from "react-native";

const isWeb = Platform.OS === "web";

export function DraggablePedidoCard({
  pedidoId,
  enabled = true,
  children,
  testID,
}: {
  pedidoId: number;
  enabled?: boolean;
  children: ReactNode;
  testID?: string;
}) {
  const ref = useRef<View>(null);

  useEffect(() => {
    if (!isWeb) return;
    const node = ref.current as unknown as HTMLElement | null;
    if (!node) return;
    // O card renderizado (`ps.card` em PainelPedidoCard.tsx) é o único
    // filho real deste wrapper `display:contents`. O atributo `draggable`
    // e os listeners de drag precisam ir NELE, nunca no wrapper — achado
    // ao vivo 2026-08-11 (drag-and-drop nunca iniciava em nenhum
    // navegador testado, sem erro nenhum no console): um elemento com
    // `display:contents` não gera caixa própria, e a HTML5 Drag and Drop
    // API exige uma caixa real pra servir de fonte do arrasto — setar
    // `draggable="true"` no wrapper simplesmente não tem efeito. O
    // wrapper em si continua existindo só pelo layout (ver comentário no
    // JSX abaixo), nunca participa da mecânica de drag.
    const card = node.firstElementChild as HTMLElement | null;
    if (!card) return;
    if (!enabled) {
      card.removeAttribute("draggable");
      card.style.cursor = "";
      return;
    }
    card.setAttribute("draggable", "true");
    card.style.cursor = "grab";
    const onDragStart = (e: DragEvent) => {
      e.dataTransfer?.setData("text/plain", String(pedidoId));
      if (e.dataTransfer) e.dataTransfer.effectAllowed = "move";
      card.style.opacity = "0.4";
    };
    const onDragEnd = () => {
      card.style.opacity = "";
    };
    card.addEventListener("dragstart", onDragStart);
    card.addEventListener("dragend", onDragEnd);
    return () => {
      card.removeEventListener("dragstart", onDragStart);
      card.removeEventListener("dragend", onDragEnd);
    };
  }, [pedidoId, enabled]);

  return (
    // `display:"contents"` — o wrapper some por completo do cálculo de
    // layout (não gera caixa própria), então o card interno volta a ser,
    // pra fins de flexbox, filho DIRETO de `colCardsGrid` (mesma situação
    // de antes deste componente existir). Isso evita qualquer
    // reinterpretação de `flexBasis`/`flexShrink`/`minWidth` do card
    // (pensados como LARGURA na linha do grid original) por um nível de
    // aninhamento extra — foi a causa de dois bugs visuais seguidos
    // (2026-07-30): primeiro o card inflando pra ~280px de altura, depois
    // — na tentativa de corrigir só a direção do eixo — o card
    // ultrapassando a largura da coluna (o wrapper, sem suas próprias
    // restrições de largura, não repassava corretamente o "encolhe até
    // 220px" do card quando a coluna fica estreita). `display:contents`
    // elimina o problema pela raiz: não há mais nó de layout entre o card
    // e o grid pra a matemática do flexbox atravessar.
    <View ref={ref} style={{ display: "contents" } as ViewStyle} testID={testID}>
      {children}
    </View>
  );
}

export function DroppableColuna({
  onDropPedido,
  children,
  style,
  testID,
}: {
  onDropPedido: (pedidoId: number) => void;
  children: ReactNode;
  style?: ViewStyle | ViewStyle[];
  testID?: string;
}) {
  const ref = useRef<View>(null);
  const [over, setOver] = useState(false);
  // Handler sempre atualizado sem precisar reanexar os listeners a cada
  // render (a coluna/lista muda a todo refresh) — mesmo padrão de "ref
  // espelhando o valor mais recente" já comum em hooks deste projeto.
  const onDropRef = useRef(onDropPedido);
  onDropRef.current = onDropPedido;

  useEffect(() => {
    if (!isWeb) return;
    const node = ref.current as unknown as HTMLElement | null;
    if (!node) return;
    let depth = 0;
    const onDragOver = (e: DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    };
    const onDragEnter = (e: DragEvent) => {
      e.preventDefault();
      depth++;
      setOver(true);
    };
    const onDragLeave = () => {
      depth = Math.max(0, depth - 1);
      if (depth === 0) setOver(false);
    };
    const onDrop = (e: DragEvent) => {
      e.preventDefault();
      depth = 0;
      setOver(false);
      const raw = e.dataTransfer?.getData("text/plain");
      const pedidoId = raw ? Number(raw) : NaN;
      if (!Number.isNaN(pedidoId)) onDropRef.current(pedidoId);
    };
    node.addEventListener("dragover", onDragOver);
    node.addEventListener("dragenter", onDragEnter);
    node.addEventListener("dragleave", onDragLeave);
    node.addEventListener("drop", onDrop);
    return () => {
      node.removeEventListener("dragover", onDragOver);
      node.removeEventListener("dragenter", onDragEnter);
      node.removeEventListener("dragleave", onDragLeave);
      node.removeEventListener("drop", onDrop);
    };
  }, []);

  return (
    <View ref={ref} style={[style, over ? dropOverStyle : null]} testID={testID}>
      {children}
    </View>
  );
}

const dropOverStyle: ViewStyle = {
  backgroundColor: "rgba(30, 136, 229, 0.08)",
  borderRadius: 8,
};
