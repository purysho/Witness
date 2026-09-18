import { useMemo, useState } from "react";
import type { GraphNode, GraphSnapshot } from "../../../../../contracts/generated/rpc";

interface PositionedNode extends GraphNode { x:number; y:number; }
const columns:Record<GraphNode["kind"],number>={source:80,entity:300,claim:540,evidence:800};

export function GraphView({graph,onRefresh,busy}:{graph:GraphSnapshot|null;onRefresh:()=>void;busy:boolean}) {
  const [selected,setSelected]=useState<GraphNode|null>(null);
  const positioned=useMemo(()=>{
    if (!graph) return [] as PositionedNode[];
    const counts:Record<string,number>={};
    return graph.nodes.map(node=>{
      const index=counts[node.kind]??0; counts[node.kind]=index+1;
      return {...node,x:columns[node.kind],y:55+index*74};
    });
  },[graph]);
  const byId=new Map(positioned.map(node=>[node.id,node]));
  const height=Math.max(420,...positioned.map(node=>node.y+55));
  return (
    <div className="view-grid graph-grid">
      <section className="panel graph-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">GRAPH</span><h2>Evidence relationships</h2></div>
          <button className="secondary" disabled={busy} onClick={onRefresh}>Refresh graph</button>
        </div>
        {!graph||graph.nodes.length===0 ? <div className="empty">Index evidence, then run queries to expose claims, support, contradictions, and supersession.</div> : (
          <div className="graph-scroll">
            <svg className="graph-canvas" viewBox={`0 0 900 ${height}`} role="img">
              <g className="graph-edges">{graph.edges.map(edge=>{
                const source=byId.get(edge.source), target=byId.get(edge.target);
                if (!source||!target) return null;
                return <g key={edge.id}>
                  <line x1={source.x} y1={source.y} x2={target.x} y2={target.y}/>
                  <text x={(source.x+target.x)/2} y={(source.y+target.y)/2-5}>{edge.relation}</text>
                </g>;
              })}</g>
              <g className="graph-nodes">{positioned.map(node=>(
                <g className={`graph-node graph-${node.kind}`} key={node.id} onClick={()=>setSelected(node)}>
                  <circle cx={node.x} cy={node.y} r="17"/>
                  <text x={node.x+26} y={node.y+4}>{node.label.length>34?node.label.slice(0,33)+"…":node.label}</text>
                </g>
              ))}</g>
            </svg>
          </div>
        )}
        <div className="graph-legend">{(["source","entity","claim","evidence"] as const).map(kind=><span className={`legend-${kind}`} key={kind}>{kind}</span>)}</div>
      </section>
      <section className="panel graph-inspector">
        <span className="eyebrow">INSPECTOR</span><h2>{selected?selected.label:"Select a node"}</h2>
        {selected ? <>
          <span className={`node-kind kind-${selected.kind}`}>{selected.kind}</span>
          <pre>{JSON.stringify(selected.metadata,null,2)}</pre>
          <h3>Connected edges</h3>
          <div className="edge-list">{graph?.edges.filter(e=>e.source===selected.id||e.target===selected.id).map(edge=>(
            <article key={edge.id}><strong>{edge.relation}</strong><code>{edge.source===selected.id?edge.target:edge.source}</code></article>
          ))}</div>
        </> : <div className="empty">Claims and graph assertions remain inspectable links to evidence rather than replacing it.</div>}
      </section>
    </div>
  );
}
