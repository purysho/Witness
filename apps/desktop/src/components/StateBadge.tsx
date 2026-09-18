import type { SufficiencyState } from "../../../../contracts/generated/rpc";

export function StateBadge({state}:{state:SufficiencyState}) {
  return <span className={`state-badge state-${state.toLowerCase()}`}>{state}</span>;
}
