import { REPO_URL } from "../lib/labels";

export default function ClosedNotice() {
  return (
    <div className="notice" role="status">
      <strong>라이브 실행은 종료됐습니다. 아래는 기록된 결과입니다.</strong>
      <p>
        직접 돌려 보려면 저장소의 <a href={`${REPO_URL}/blob/main/evolve/README.md`}>evolve/README.md</a> 를 따라 Claude 구독 로그인이나 API
        키로 실행할 수 있습니다.
      </p>
    </div>
  );
}
