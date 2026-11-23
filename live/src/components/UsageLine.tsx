import { PRICE_IN, PRICE_OUT } from "../lib/labels";

export default function UsageLine({ calls, input, output }: { calls: number; input: number; output: number }) {
  const usd = (input / 1e6) * PRICE_IN + (output / 1e6) * PRICE_OUT;
  return (
    <p className="usage">
      호출 <strong>{calls.toLocaleString("ko-KR")}</strong>회 · 입력 <strong>{input.toLocaleString("ko-KR")}</strong> 토큰 · 출력{" "}
      <strong>{output.toLocaleString("ko-KR")}</strong> 토큰 · 추정 <strong>${usd.toFixed(4)}</strong>
      <span className="muted small"> 추정 비용은 입력 100만 토큰 0.10달러, 출력 0.50달러 기준입니다.</span>
    </p>
  );
}
